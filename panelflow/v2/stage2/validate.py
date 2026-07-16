"""Sub-stage 2.3 — Validate & repair.

Checks a direction file, then up to two repair calls. This is what sets
`validated: true`, which is Stage 3's gate — a file with a dangling panel ref,
an animation the renderer has never heard of, or a name the book never says
must not reach a render.

Almost every check here is a fact: does the panel exist, is the animation in the
renderer's vocabulary, does every beat have a shot. Taste belongs to 2.1/2.2.

The exception is naming, which is asked of a model rather than ruled on, because
it is a question about language and not about the data — see _check_names. The
first cut of it was a regex, and it was worse than nothing: it passed
"Wolverine catches it." while flagging "Beneath".
"""
import re

from custom_logger import logger_config

from .. import llm, prompts
from ..paths import ANALYZED
from . import schemas

MAX_REPAIRS = 2
# Post-trim, post-speedup speech runs faster than read-aloud prose; measured on
# a real render, not assumed. Only a ceiling hangs on this estimate — a short
# that runs long gets rejected by the platform, a short that runs short is just
# a shorter short — so a rough number is enough.
WORDS_PER_SECOND = 3.5
SHORTS_MAX_SECONDS = 120
ENDING_ANIMATIONS = ["zoom_out", "fade_in", "ken_burns", "breathe"]

# Markup is syntax — a bracket is a bracket in every book, so a rule can own it.
# Naming is not, and is asked of a model below.
_MARKUP = re.compile(r'[*_#<>\[\]{}|]|\([^)]*\)')


def is_done(assets, target):
    return bool(assets.load_direction(target).get("validated"))


def run(assets, target, model=None):
    if is_done(assets, target):
        return []

    direction = assets.load_direction(target)
    if not direction.get("shots"):
        raise ValueError(f"2.3: no direction to validate for {target!r}; run 2.1/2.2 first")

    for attempt in range(MAX_REPAIRS + 1):
        problems = check(assets, direction, model)
        if not problems:
            direction["validated"] = True
            assets.save_direction(target, direction)
            logger_config.info(f"2.3 {target}: validated ({len(direction['shots'])} shots)")
            return []

        if attempt == MAX_REPAIRS:
            break
        logger_config.warning(
            f"2.3 {target}: {len(problems)} problem(s), repair {attempt + 1}/{MAX_REPAIRS}")
        direction = _repair(assets, direction, problems, model)
        assets.save_direction(target, direction)

    # Hard-fail rather than ship: a broken direction file renders a broken video.
    return [f"{target}: {p}" for p in check(assets, direction, model)]


def check(assets, direction, model=None):
    """Every violation as one string. Empty list == valid."""
    problems = []
    shots = direction.get("shots", [])
    if not shots:
        return ["no shots"]

    problems += _check_ids(shots)
    problems += _check_sources(assets, shots)
    problems += _check_vocabulary(shots)
    problems += _check_narration(assets, shots, model)
    problems += _check_meta(assets, direction)
    if direction.get("target") == "longform":
        problems += _check_beats_covered(assets, shots)
    else:
        problems += _check_shorts(shots, assets)
    return problems


def _check_ids(shots):
    expected = list(range(1, len(shots) + 1))
    if [s.get("id") for s in shots] != expected:
        return ["shot ids are not sequential from 1"]
    return []


def _check_sources(assets, shots):
    problems = []
    pages = {i: p for i, p in assets.pages()}
    for shot in shots:
        source = shot.get("source", {})
        page = pages.get(source.get("page"))
        where = f'shot {shot.get("id")}'
        if page is None:
            problems.append(f'{where}: page {source.get("page")} does not exist')
            continue
        if page.get("status") != ANALYZED:
            problems.append(f'{where}: page {source.get("page")} is not analyzed')
        ids = {p["id"] for p in page.get("panels", [])}
        for field in ("panel", "from_panel", "to_panel"):
            if field in source and source[field] not in ids:
                problems.append(
                    f'{where}: {field} {source[field]} is not on page {source.get("page")}')
        kind = source.get("kind")
        if kind == "panel" and "panel" not in source:
            problems.append(f"{where}: kind=panel needs a panel")
        if kind == "pan":
            if "from_panel" not in source or "to_panel" not in source:
                problems.append(f"{where}: kind=pan needs from_panel and to_panel")
            elif source["from_panel"] == source["to_panel"]:
                problems.append(f"{where}: pan starts and ends on the same panel")
            if page.get("analysis", {}).get("reading_order_suspect"):
                problems.append(
                    f'{where}: pan across page {source.get("page")}, whose panel order is suspect')
    return problems


def _check_vocabulary(shots):
    problems = []
    for shot in shots:
        where = f'shot {shot.get("id")}'
        if shot.get("animation") not in schemas.ANIMATIONS:
            problems.append(f'{where}: unknown animation {shot.get("animation")!r}')
        if shot.get("transition_in") not in schemas.TRANSITIONS:
            problems.append(f'{where}: unknown transition {shot.get("transition_in")!r}')
        if shot.get("animation_target") not in schemas.ANIMATION_TARGETS:
            problems.append(f'{where}: unknown animation_target {shot.get("animation_target")!r}')
        for event in shot.get("events") or []:
            if event.get("type") not in schemas.EVENTS:
                problems.append(f'{where}: unknown event {event.get("type")!r}')
            if not 0 <= (event.get("at_fraction") or 0) <= 1:
                problems.append(f'{where}: event at_fraction outside 0..1')
        silent = shot.get("silent_seconds")
        if (shot.get("narration") or "").strip():
            if silent:
                problems.append(f"{where}: has narration and silent_seconds")
        elif not silent:
            problems.append(f"{where}: silent shot without silent_seconds")
    if shots and shots[0].get("transition_in") != "none":
        problems.append("shot 1: must open with transition_in 'none'")
    return problems


def _check_narration(assets, shots, model=None):
    problems = []
    for shot in shots:
        if _MARKUP.search(shot.get("narration") or ""):
            problems.append(
                f'shot {shot.get("id")}: narration has markup or a stage direction — '
                f"TTS reads it aloud")
    return problems + _check_names(assets, shots, model)


def _check_names(assets, shots, model):
    """Ask whether the narration names anyone the book never named.

    This is the one check here that is not a fact, and it is asked rather than
    ruled on. A rule cannot do it: the question is whether a capitalised word is
    a person's name, and no amount of matching separates "Gambit" from
    "Beneath" — both are simply words this comic never writes. Nor does the
    book's own vocabulary settle it, since "Strange" is in this very book's
    title and "Doctor Strange" is exactly the name that must not appear.

    So the whole narration goes over, unfiltered. Filtering the candidates first
    would decide, with a rule, the very thing being asked.
    """
    speaking = [s for s in shots if (s.get("narration") or "").strip()]
    if not speaking:
        return []

    try:
        result = llm.ask_json(
            system_prompt=prompts.load("check_narration_names"),
            user_prompt=_names_prompt(assets, speaking),
            model=model,
        )
    except Exception as e:
        # Loud, and fatal to validation: silently skipping the anti-hallucination
        # check would ship the video it exists to stop.
        raise RuntimeError(f"2.3: could not check narration names: {e}") from e

    problems = []
    for violation in result.get("violations", []):
        problems.append(
            f'shot {violation.get("shot")}: narration names {violation.get("name")!r}, '
            f"whom this book never names — describe them instead")
    return problems


def _names_prompt(assets, shots):
    allowed, unnamed = [], []
    for c in assets.load_characters().get("characters", []):
        name = c.get("name") or c.get("inferred_identity")
        if name:
            allowed.append(f'- "{name}" — {c["id"]}'
                           + (f' (also: {", ".join(c["aliases"])})' if c.get("aliases") else ""))
        else:
            unnamed.append(f'- {c["id"]} — {c.get("visual") or "no description"}')
    lines = "\n".join(f'{s["id"]}: {s.get("narration")}' for s in shots)
    return (
        f'ALLOWED — characters the roster names\n{"=" * 40}\n'
        + ("\n".join(allowed) or "(no character in the roster is named)")
        + f'\n\nUNNAMED — describe, never name\n{"=" * 40}\n' + ("\n".join(unnamed) or "(none)")
        + f'\n\nTHE BOOK\'S OWN WORDS — every caption and line of dialogue\n{"=" * 40}\n'
        + (_book_words(assets) or "(the book has no lettering)")
        + f'\n\nNARRATION\n{"=" * 40}\n{lines}'
    )


def _book_words(assets):
    """Every caption and spoken line the book contains, verbatim.

    The roster is not the whole of what the book names. A caption can call the
    vampire "The Count" without any character entry ever carrying that as a
    name, and the narration is right to use it — the reader was told it. So the
    checker is given the book's actual text as the ground truth for what the
    book established, not just the roster's tidy list. SFX is dropped: it is
    noise ("FLAP FLAP"), never a name.
    """
    lines = []
    for index in assets.page_indices():
        page = assets.load_page(index)
        entries = [d for panel in page.get("panels", []) for d in panel.get("dialogue", [])]
        entries += page.get("analysis", {}).get("unassigned_dialogue", [])
        for entry in entries:
            text = (entry.get("text") or "").strip()
            if text and entry.get("kind") != "sfx":
                lines.append(text)
    return "\n".join(lines)


def _check_meta(assets, direction):
    problems = []
    meta = direction.get("meta") or {}
    for field in ("youtube_title", "description", "twitter_post"):
        if not (meta.get(field) or "").strip():
            problems.append(f"meta.{field} is empty")
    thumbnail = meta.get("thumbnail") or {}
    page = dict(assets.pages()).get(thumbnail.get("page"))
    if page is None:
        problems.append(f'meta.thumbnail: page {thumbnail.get("page")} does not exist')
    elif thumbnail.get("panel") not in {p["id"] for p in page.get("panels", [])}:
        problems.append(f'meta.thumbnail: panel {thumbnail.get("panel")} is not on that page')
    if not ((direction.get("music") or {}).get("mood") or "").strip():
        problems.append("music.mood is empty")
    return problems


def _check_beats_covered(assets, shots):
    """Longform may skip anything except the plot."""
    shown = {s.get("source", {}).get("page") for s in shots}
    problems = []
    for beat in (assets.load_book().get("story") or {}).get("beats", []):
        pages = set(beat.get("pages") or [])
        if pages and not (pages & shown):
            problems.append(
                f'beat {beat.get("beat")!r} (pages {sorted(pages)}) has no shot — '
                f"longform may skip pages, never beats")
    return problems


def _check_shorts(shots, assets):
    problems = []
    words = sum(len((s.get("narration") or "").split()) for s in shots)
    seconds = words / WORDS_PER_SECOND
    if seconds > SHORTS_MAX_SECONDS:
        problems.append(
            f"narration is {words} words ≈ {seconds:.0f}s, over the "
            f"{SHORTS_MAX_SECONDS}s ceiling")
    first = shots[0].get("source", {})
    page = dict(assets.pages()).get(first.get("page")) or {}
    panel = next((p for p in page.get("panels", []) if p["id"] == first.get("panel")), {})
    if panel and (panel.get("intensity") or 0) < 4:
        problems.append(
            f'shot 1: opens on intensity {panel.get("intensity")}; a short must hook on 4 or 5')
    if shots[-1].get("animation") not in ENDING_ANIMATIONS:
        problems.append(
            f'shot {shots[-1].get("id")}: last shot should end on one of {ENDING_ANIMATIONS}')
    return problems


def _repair(assets, direction, problems, model):
    result = llm.ask_json(
        system_prompt=prompts.load("repair_direction"),
        user_prompt=(
            f'PROBLEMS\n{"=" * 40}\n' + "\n".join(f"- {p}" for p in problems)
            + f'\n\nTHE DIRECTION FILE\n{"=" * 40}\n{_shots_json(direction)}'
        ),
        schema=schemas.DIRECTION,
        model=model,
    )
    if result.get("shots"):
        direction["shots"] = _renumber(result["shots"])
    for key in ("meta", "music"):
        if result.get(key):
            direction[key] = result[key]
    return direction


def _renumber(shots):
    for shot_id, shot in enumerate(shots, start=1):
        shot["id"] = shot_id
    return shots


def _shots_json(direction):
    import json
    return json.dumps({k: direction[k] for k in ("meta", "music", "shots") if k in direction},
                      indent=1)
