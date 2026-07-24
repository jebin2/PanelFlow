"""Sub-stage 3.3 — music.

The director set one mood for the whole video; this turns it, plus the video's
shape, into a single synth track the video plays under its narration. The shape
is the arithmetic part — how long each stretch runs, how intense it is, how
densely it is narrated — and it is measured here, in code. Turning that shape
into music is judgement, so a model writes the pattern; a tool (strudel-render)
renders the pattern to audio.

The track also carries the video's punctuation: the director's events and
transitions become percussive hits stacked over the model's bed (see hits.py).
Placement is arithmetic and the palette is fixed, so that layer is code too.

Music is an enhancement, never a gate: if the model writes a pattern that will
not render, or renders silent, the video ships without music rather than not at
all. A broken score must not cost a video.
"""
import glob
import hashlib
import json
import os
import subprocess

from custom_logger import logger_config

from .. import jsonio, llm, prompts
from . import hits
from .render import REMOTION_DIR

# The track's clock. One cycle = 2s at 0.5; section lengths are cycles rounded
# from seconds, so the music lands where the video's sections do.
CPS = 0.5
# Under the narration, which is normalised loud; tune by ear, not by theory.
# Together these put the bed ~12 dB under the voice — present, never competing.
# The first cut (-20 LUFS x 0.28) landed ~15 dB under and was inaudible; 0.5
# (~8 dB under) was too loud once every layer actually rendered.
BED_VOLUME = 0.3
MUSIC_LUFS = -18
# Salted into the cache fingerprint: bump when the composer prompt or palette
# changes enough that cached tracks should be rewritten.
COMPOSER_VERSION = 7
MIN_SECTION_CYCLES = 1
# A musical phrase, not a shot: a section shorter than this cannot state a
# progression, and stitching short sections is what made the score stutter.
MIN_SECTION_SECONDS = 16
# A silent render is a failed score, not a valid quiet one.
SILENCE_DB = -60.0
# Three, not two: the syntax pre-flight makes a bad pattern cost milliseconds
# instead of a browser launch, so a retry is cheap enough to afford one more.
COMPOSE_ATTEMPTS = 3
# The renderer's bookends (Root.tsx): the music plays from frame 0 and under
# the end card, so the score must cover intro + shots + outro. Seconds, per
# target — longform's CinematicIntro/EndCard, shorts' TitleCard.
BOOKEND_SECONDS = {"longform": (4.0, 5.0), "shorts": (1.6, 0.0)}

_CLI = os.path.join(REMOTION_DIR, "node_modules", "strudel-render", "src", "cli.mjs")


def run(assets, target, direction, manifest, model=None):
    """Compose and render one music track. Returns the manifest's `music` block
    ({"src", "volume"}), or {} when there is nothing to score or scoring failed.
    """
    mood = ((direction.get("music") or {}).get("mood") or "").strip()
    bookends = BOOKEND_SECONDS.get(target, (0.0, 0.0))
    sections = _sections(assets, direction, manifest, bookends=bookends)
    total_cycles = sum(s["cycles"] for s in sections)
    if not mood or not total_cycles:
        return {}

    punctuation = hits.timeline(manifest, lead_seconds=bookends[0])
    out = assets.music_path(target)
    fingerprint = _fingerprint(mood, sections, punctuation)
    if os.path.exists(out) and _meta(assets, target).get("fingerprint") == fingerprint:
        logger_config.info(f"3.3 {target}: music unchanged, keeping {os.path.basename(out)}")
        return _ref(assets, out)

    for attempt in range(1, COMPOSE_ATTEMPTS + 1):
        try:
            pattern = _score(mood, sections, total_cycles, punctuation, model)
            _check_syntax(pattern, out)
            _render(pattern, out, total_cycles)
            _write_meta(assets, target, fingerprint, pattern)
            logger_config.info(
                f"3.3 {target}: scored {total_cycles} cycles "
                f"({total_cycles / CPS:.0f}s) over {len(sections)} section(s)")
            return _ref(assets, out)
        except Exception as e:
            logger_config.warning(
                f"3.3 {target}: music attempt {attempt}/{COMPOSE_ATTEMPTS} failed: {e}")

    logger_config.warning(f"3.3 {target}: no music — the video renders without a score")
    return {}


# ----------------------------------------------------------------- the shape

def _sections(assets, direction, manifest, bookends=(0.0, 0.0)):
    """The video merged into a few long sections the composer can score.

    Music breathes in phrases, not in shots: scoring every intensity flicker
    gave two-second fragments that stuttered ("rrrr"), because each section
    restarts the pattern. So shots fold into their running section until it has
    a phrase's worth of length, and only then may a *change* of band open a new
    one. A 30-second short becomes two or three sections; only the arc survives,
    which is exactly what a score should follow.
    """
    shots = []
    for shot, panel in zip(direction["shots"], manifest["panels"]):
        seconds = panel.get("durationInSeconds") or 0
        shots.append({
            "band": _band(_intensity(assets, shot)),
            "seconds": seconds,
            "spoken": seconds if (panel.get("narrationText") or "").strip() else 0,
        })

    sections = []
    for shot in shots:
        grown = sections[-1]["seconds"] >= MIN_SECTION_SECONDS if sections else False
        if sections and not (grown and shot["band"] != _dominant(sections[-1])):
            _fold(sections[-1], shot)
        else:
            sections.append({"seconds": shot["seconds"], "spoken": shot["spoken"],
                             "bands": {shot["band"]: shot["seconds"]}})

    # A trailing sliver is a coda, not a section — fold it back.
    if len(sections) > 1 and sections[-1]["seconds"] < MIN_SECTION_SECONDS / 2:
        _fold(sections[-2], sections.pop())

    # The bookends breathe with the score's edges: the intro extends the
    # opening section, the end card extends the closing one.
    if sections:
        lead, tail = bookends
        sections[0]["seconds"] += lead
        sections[-1]["seconds"] += tail

    for section in sections:
        section["band"] = _dominant(section)
        section["cycles"] = max(MIN_SECTION_CYCLES, round(section["seconds"] * CPS))
        section["narration"] = "heavy" if section["spoken"] > 0.6 * section["seconds"] else "sparse"
    return sections


def _fold(section, piece):
    section["seconds"] += piece["seconds"]
    section["spoken"] += piece["spoken"]
    for band, seconds in piece.get("bands", {piece.get("band"): piece["seconds"]}).items():
        section["bands"][band] = section["bands"].get(band, 0) + seconds


def _dominant(section):
    """The band the section mostly spends its time in."""
    return max(section["bands"].items(), key=lambda kv: kv[1])[0]


def _intensity(assets, shot):
    """A shot's intensity from its source panel(s). A pan takes the louder of
    its two panels; a full page, the loudest on it."""
    source = shot["source"]
    panels = {p["id"]: p for p in assets.load_page(source["page"]).get("panels", [])}
    if source["kind"] == "panel":
        ids = [source.get("panel")]
    elif source["kind"] == "pan":
        ids = [source.get("from_panel"), source.get("to_panel")]
    else:
        ids = list(panels)
    values = [panels[i].get("intensity") or 0 for i in ids if i in panels]
    return max(values) if values else 0


def _band(intensity):
    if intensity >= 4:
        return "intense"
    if intensity == 3:
        return "rising"
    return "calm"


# --------------------------------------------------------------- composition

def _score(mood, sections, total_cycles, punctuation, model):
    """The model's bed with the code-built hit layers stacked over it."""
    bed = _compose(mood, sections, total_cycles, model)
    layers = hits.layers(punctuation, total_cycles, CPS)
    if not layers:
        return bed
    return "stack(" + ", ".join([bed] + layers) + ")"


def _compose(mood, sections, total_cycles, model):
    result = llm.ask_json(
        system_prompt=prompts.load("compose_music"),
        user_prompt=_prompt(mood, sections, total_cycles),
        model=model,
    )
    pattern = (result.get("pattern") or "").strip()
    if not pattern:
        raise ValueError("composer returned no pattern")
    return pattern


def _prompt(mood, sections, total_cycles):
    lines = "\n".join(
        f'{i}. {s["cycles"]} cycles — intensity {s["band"]} — narration: {s["narration"]}'
        for i, s in enumerate(sections, start=1))
    return (
        f'MOOD\n{"=" * 40}\n{mood}\n\n'
        f'TEMPO\n{"=" * 40}\n{CPS} cycles per second (one cycle = {1 / CPS:.0f} seconds)\n\n'
        f'TOTAL\n{"=" * 40}\n{total_cycles} cycles ({total_cycles / CPS:.0f} seconds)\n\n'
        f'SECTIONS — in order, lengths in cycles\n{"=" * 40}\n{lines}'
    )


def _check_syntax(pattern, out):
    """Parse the composer's pattern with Node before paying for a render.

    The composer's most common failure is a dropped bracket in arrange(), and
    strudel-render only reports it after a full browser launch. The same parser
    that will judge the pattern later judges it here, in milliseconds, so a
    broken attempt retries immediately instead of burning the render budget.
    """
    result = subprocess.run(
        ["node", "-e", "new Function(require('fs').readFileSync(0, 'utf8'))"],
        input=pattern, text=True, capture_output=True)
    if result.returncode != 0:
        _dump_failed(pattern, out)
        error = next((line for line in result.stderr.splitlines()
                      if "SyntaxError" in line), result.stderr.strip())
        raise ValueError(f"composer wrote a pattern that does not parse: {error}")


def _render(pattern, out, total_cycles):
    os.makedirs(os.path.dirname(out), exist_ok=True)
    options = {
        "code": pattern, "out": out,
        "cycles": total_cycles, "cps": CPS,
        # The palette is GM instruments (fetched on demand), not raw oscillators
        # — raw synth beds sounded like a chiptune under the narration.
        "soundfonts": True,
        "loudnessDb": MUSIC_LUFS,
        "executablePath": _chromium(),
    }
    result = subprocess.run(
        ["node", _CLI], input=json.dumps(options),
        text=True, capture_output=True, cwd=REMOTION_DIR)
    if result.returncode != 0:
        _dump_failed(pattern, out)
        raise RuntimeError(f"strudel-render failed: {result.stderr.strip() or result.stdout.strip()}")
    if _mean_volume(out) <= SILENCE_DB:
        _dump_failed(pattern, out)
        raise ValueError("rendered track is silent")


def _dump_failed(pattern, out):
    """A pattern that would not render is the whole postmortem — keep it.

    Without this, a composer SyntaxError points at a character offset in a
    string nobody ever saw.
    """
    path = out + ".failed.js"
    with open(path, "w") as f:
        f.write(pattern)
    logger_config.warning(f"3.3: failing pattern kept at {path}")


def _chromium():
    """Reuse the browser Remotion already downloaded; fall back to the system."""
    hits = glob.glob(os.path.join(
        REMOTION_DIR, "node_modules", ".remotion", "chrome-headless-shell",
        "*", "*", "chrome-headless-shell"))
    return hits[0] if hits else os.environ.get("STRUDEL_RENDER_CHROMIUM", "/usr/bin/chromium")


def _mean_volume(path):
    result = subprocess.run(
        ["ffmpeg", "-i", path, "-af", "volumedetect", "-f", "null", "-"],
        capture_output=True, text=True)
    for line in result.stderr.splitlines():
        if "mean_volume:" in line:
            return float(line.split("mean_volume:")[1].split("dB")[0])
    return SILENCE_DB - 1  # unreadable == treat as silent


# ------------------------------------------------------------------- caching

def _ref(assets, out):
    return {"src": assets.rel_to_book(out), "volume": BED_VOLUME}


def _fingerprint(mood, sections, punctuation):
    payload = json.dumps([COMPOSER_VERSION, mood,
                          [(s["cycles"], s["band"], s["narration"]) for s in sections],
                          [(round(seconds, 2), kind) for seconds, kind in punctuation]],
                         sort_keys=True)
    return hashlib.md5(payload.encode("utf-8")).hexdigest()


def _meta_path(assets, target):
    return os.path.join(assets.target_dir(target), "music.json")


def _meta(assets, target):
    return jsonio.read(_meta_path(assets, target), {})


def _write_meta(assets, target, fingerprint, pattern):
    jsonio.write(_meta_path(assets, target), {"fingerprint": fingerprint, "pattern": pattern})
