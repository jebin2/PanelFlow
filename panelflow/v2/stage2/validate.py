"""Sub-stage 2.3 — Validate & repair.

Deterministic checks over a direction file, then up to two repair calls. This
is what sets `validated: true`, which is Stage 3's gate — a file with a dangling
panel ref, an animation the renderer has never heard of, or a name the book
never says must not reach a render.

Every check here is a fact, not a judgement. Taste belongs to 2.1/2.2.
"""
import re

from custom_logger import logger_config

from .. import llm, prompts
from ..paths import ANALYZED
from . import schemas

MAX_REPAIRS = 2
WORDS_PER_SECOND = 2.5
SHORTS_SECONDS = (60, 120)
ENDING_ANIMATIONS = ["zoom_out", "fade_in", "ken_burns", "breathe"]

# One tokenizer for both the narration and the book, so "Vee-Shanti" is the same
# token on both sides. Two regexes with different ideas about hyphens is how the
# first cut of this decided the book never says a word it says on page 6.
_WORD = re.compile(r"[A-Za-z][A-Za-z'’\-]*")
_SPLIT_PARTS = re.compile(r"['’\-]")
_ENDS_SENTENCE = '.!?:;"“”—-'
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
        problems = check(assets, direction)
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
    return [f"{target}: {p}" for p in check(assets, direction)]


def check(assets, direction):
    """Every violation as one string. Empty list == valid."""
    problems = []
    shots = direction.get("shots", [])
    if not shots:
        return ["no shots"]

    problems += _check_ids(shots)
    problems += _check_sources(assets, shots)
    problems += _check_vocabulary(shots)
    problems += _check_narration(assets, shots)
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


def _check_narration(assets, shots):
    """Narration must be sayable, and must not name anyone the book does not.

    The naming check is grounded rather than guessed: a capitalised word is
    allowed if the roster lets us say it, or if the book's own text contains it
    — that is what makes "Citadel" and "Wongburg" fine and "Wolverine" a
    violation. Sentence-initial capitals are grammar and are ignored.
    """
    allowed = _sayable(assets) | _words_in_book(assets)
    problems = []
    for shot in shots:
        text = shot.get("narration") or ""
        where = f'shot {shot.get("id")}'
        if _MARKUP.search(text):
            problems.append(f"{where}: narration has markup or a stage direction — TTS reads it")
        for token in _unexplained_names(text, allowed):
            problems.append(
                f"{where}: narration says {token!r}, which the book never says and the "
                f"roster does not allow")
    return problems


def _unexplained_names(text, allowed):
    """Capitalised words that are neither grammar nor grounded.

    A word earns its capital three ways: it opens a sentence, the roster lets us
    say it, or the book puts it on the page. "Wongburg" and "Vee-Shanti" pass on
    the third — invented nonsense is still the book's nonsense. Only a name from
    nowhere is left, which is the one thing this is looking for.
    """
    found = []
    for match in _WORD.finditer(text):
        token = match.group()
        if not token[0].isupper() or _opens_a_sentence(text, match.start()):
            continue
        if all(part in allowed for part in _parts(token)):
            continue
        found.append(token)
    return found


def _parts(token):
    """"Vee-Shanti" -> ["vee", "shanti"] — the book is indexed by plain words."""
    return [p for p in _SPLIT_PARTS.split(token.lower()) if p]


def _opens_a_sentence(text, position):
    before = text[:position].rstrip()
    return not before or before[-1] in _ENDS_SENTENCE


def _sayable(assets):
    out = set()
    for c in assets.load_characters().get("characters", []):
        for value in [c.get("name"), c.get("inferred_identity")] + (c.get("aliases") or []):
            if value:
                out.update(value.lower().split())
    return out


def _words_in_book(assets):
    """Every word the book itself puts on the page — dialogue, captions, title.

    Place names, inventions and shouted nonsense all live here, and narration is
    entitled to any of them: they are grounded by definition.
    """
    out = set()
    book = assets.load_book()
    texts = [book.get("title", ""), (book.get("story") or {}).get("synopsis", "")]
    for _, page in assets.pages():
        entries = [d for panel in page.get("panels", []) for d in panel.get("dialogue", [])]
        entries += page.get("analysis", {}).get("unassigned_dialogue", [])
        texts += [e.get("text") or "" for e in entries]
        texts.append(page.get("analysis", {}).get("scene_summary") or "")
    for text in texts:
        for token in _WORD.findall(text or ""):
            out.update(_parts(token))
    return out


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
    if not SHORTS_SECONDS[0] <= seconds <= SHORTS_SECONDS[1]:
        problems.append(
            f"narration is {words} words ≈ {seconds:.0f}s, outside the hard "
            f"{SHORTS_SECONDS[0]}-{SHORTS_SECONDS[1]}s window")
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
