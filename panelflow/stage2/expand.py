"""Sub-stage 2.4 — Expand (longform only).

Longform narration is coarse by design: one beat per shot, several panels'
worth of action synthesized into a friend's retelling. That is what makes the
voice good (see the direct prompts), but it leaves the *picture* behind the
*words* — a single held image runs ten seconds while three sentences play over
it, each describing a different panel the page already drew.

So this pass keeps the words exactly and moves the image to follow them: a shot
whose narration walks across several panels becomes several shots, each a
verbatim slice of the line over the panel that depicts it. Nothing is rewritten
— the narration the director wrote and 2.3 validated is untouched — only cut.

The split of labour is the usual one. Which panel depicts which sentence is a
language-against-picture judgement, so a model decides it; the words stay
verbatim (code owns the text and rejects any split that does not reproduce the
line), no slice runs shorter than the floor (code), and a shot with no honest
picture change is left whole (the model's common, expected answer).
"""
import hashlib
import math

from custom_logger import logger_config

from .. import jsonio, llm, prompts
from . import normalize

# The whole point is longform's long single-image holds; shorts already cut fast.
TARGET = "longform"
# A slice on screen for less than this reads as a flash, worse than holding the
# image — so no segment may be shorter, and code merges any that would be.
FLOOR_SECONDS = 2.5
# The same measured rate 2.3 uses to budget the shorts. Post-trim speech.
WORDS_PER_SECOND = 3.5
FLOOR_WORDS = math.ceil(FLOOR_SECONDS * WORDS_PER_SECOND)


def is_done(assets, target):
    """Only longform expands; a direction carries a flag once it has."""
    if target != TARGET:
        return True
    return bool(assets.load_direction(target).get("expanded"))


def run(assets, target, model=None):
    if is_done(assets, target):
        return []

    direction = assets.load_direction(target)
    if not direction.get("validated"):
        raise ValueError(
            f"2.4 {target}: direction is not validated — run 2.3 first. Expansion "
            f"only moves the picture; it must start from words 2.3 has passed.")

    pages = {i: p for i, p in assets.pages()}
    used = _panels_by_page(direction["shots"])

    # Each shot's segmentation is cached by its narration hash the moment it
    # comes back, so a run killed at shot 20 keeps the first 19 model calls and
    # a retry only asks for what is missing. ~22 opencode calls is too much work
    # to throw away to one hiccup.
    cache_path = assets.expand_cache_path(target)
    cache = jsonio.read(cache_path, {})

    def remember(narration, segments):
        cache[_key(narration)] = segments or []
        jsonio.write(cache_path, cache)

    before = len(direction["shots"])
    expanded = []
    for shot in direction["shots"]:
        children = _expand_shot(shot, pages, used, model, cache, remember)
        # A permanent line whenever a shot actually splits — otherwise the only
        # trace of this pass is the overwriting heartbeat, so a 20-call run
        # shows one flickering line and no sense of progress. A no-op stays
        # quiet: 22 "left whole" lines would bury the ones that matter.
        if len(children) > 1:
            panels = ", ".join(str(c["source"]["panel"]) for c in children)
            logger_config.info(
                f'2.4 {target}: shot {shot["id"]} → {len(children)} panels ({panels})')
        expanded.extend(children)
    direction["shots"] = normalize.normalize_shots(expanded)
    direction["expanded"] = True
    assets.save_direction(target, direction)

    after = len(direction["shots"])
    logger_config.info(
        f"2.4 {target}: {after - before} panel(s) of movement added "
        f"({before} shots → {after})")
    return []


def _panels_by_page(shots):
    """(page -> set of panel ids already shown by some shot), for the "prefer a
    panel no other shot uses" rule. A pan shows both of its panels."""
    used = {}
    for shot in shots:
        source = shot.get("source", {})
        page = source.get("page")
        for field in ("panel", "from_panel", "to_panel"):
            if source.get(field):
                used.setdefault(page, set()).add(source[field])
    return used


def _expand_shot(shot, pages, used, model, cache, remember):
    """One shot as the shots it becomes — a list of one (unchanged) or more."""
    if not _is_candidate(shot):
        return [shot]

    page = shot["source"]["page"]
    panels = pages.get(page, {}).get("panels", [])
    taken = used.get(page, set()) - {shot["source"]["panel"]}
    segments = _ask(shot, panels, taken, model, cache, remember)
    if not segments:
        return [shot]

    ids = {p["id"] for p in panels}
    segments = _settle(segments, shot["narration"], ids)
    if len(segments) < 2:
        return [shot]
    return _to_shots(shot, segments)


def _is_candidate(shot):
    """A shot worth asking the model about.

    Only a narrator's single-panel shot: a pan already moves, a full page is
    whole on purpose, a direct quote is one utterance not to be cut across
    images, and a line too short to hold two floor-length slices cannot split —
    that last is arithmetic, not taste, so it is settled here without a call.
    """
    source = shot.get("source", {})
    if source.get("kind") != "panel":
        return False
    if shot.get("speaker"):
        return False
    narration = (shot.get("narration") or "").strip()
    return len(narration.split()) >= 2 * FLOOR_WORDS


def _ask(shot, panels, taken, model, cache, remember):
    """The model's segmentation, from cache when we already have it.

    A cached answer — including a legitimate "no split" — is reused without a
    call, so a resumed run only pays for shots that never completed. A failure
    is *not* cached (opencode returns empty under load), so it retries next run.
    """
    key = _key(shot["narration"])
    if key in cache:
        return cache[key] or None

    try:
        result = llm.ask_json(
            system_prompt=prompts.load("expand_shot"),
            user_prompt=_prompt(shot, panels, taken),
            model=model,
            label=f'finding coverage for shot {shot.get("id")}')
    except Exception as e:
        logger_config.warning(f'2.4: shot {shot.get("id")} left whole — {e}')
        return None

    segments = result.get("segments")
    segments = segments if isinstance(segments, list) else []
    remember(shot["narration"], segments)
    return segments or None


def _key(narration):
    return hashlib.md5(narration.encode("utf-8")).hexdigest()


def _prompt(shot, panels, taken):
    lines = []
    for panel in panels:
        mark = " (already used elsewhere — avoid)" if panel["id"] in taken else ""
        lines.append(f'- panel {panel["id"]} [intensity {panel.get("intensity", "?")}]: '
                     f'{panel.get("description", "")}{mark}')
    return (
        f'NARRATION (do not change a word)\n{"=" * 40}\n{shot["narration"]}\n\n'
        f'PANELS ON PAGE {shot["source"]["page"]}\n{"=" * 40}\n' + "\n".join(lines))


def _settle(segments, narration, panel_ids):
    """The model proposed; code makes it safe or gives up.

    Collapse a repeated panel, then require the pieces to reproduce the line
    verbatim — a paraphrase means the split is untrustworthy and the shot stays
    whole — then merge away any slice below the floor. What survives is a
    faithful, floor-clearing segmentation, or a single segment (== no split).
    """
    clean = []
    for segment in segments:
        panel, text = segment.get("panel"), (segment.get("text") or "").strip()
        if panel not in panel_ids or not text:
            return []                      # a made-up panel or empty piece: abandon
        if clean and clean[-1]["panel"] == panel:
            clean[-1]["text"] += " " + text
        else:
            clean.append({"panel": panel, "text": text})

    if _words(s["text"] for s in clean) != _words([narration]):
        return []                          # not the line back, verbatim: abandon
    return _merge_short(clean)


def _merge_short(segments):
    """Fold any below-floor slice into its larger neighbour, keeping order."""
    while len(segments) > 1:
        i = min(range(len(segments)), key=lambda k: _count(segments[k]["text"]))
        if _count(segments[i]["text"]) >= FLOOR_WORDS:
            break
        prev = segments[i - 1] if i > 0 else None
        nxt = segments[i + 1] if i < len(segments) - 1 else None
        into_prev = prev and (not nxt or _count(prev["text"]) >= _count(nxt["text"]))
        if into_prev:
            prev["text"] += " " + segments[i]["text"]
        else:
            nxt["text"] = segments[i]["text"] + " " + nxt["text"]
        segments.pop(i)
    return segments


def _to_shots(shot, segments):
    """The segments as shots: the first keeps the parent's opening, the rest are
    hard cuts inside the same scene, all on the parent's animation."""
    total = _count(shot["narration"])
    shots, spoken = [], 0
    for index, segment in enumerate(segments):
        words = _count(segment["text"])
        child = {
            "source": {"kind": "panel", "page": shot["source"]["page"],
                       "panel": segment["panel"]},
            "narration": segment["text"],
            "animation": shot["animation"],
            "animation_target": shot["animation_target"],
            "transition_in": shot["transition_in"] if index == 0 else "none",
            "silent_seconds": None,
            "speaker": None,
            "events": _events_in(shot.get("events") or [], spoken, words, total),
            "why": f'{shot.get("why", "")} (coverage {index + 1}/{len(segments)})',
        }
        shots.append(child)
        spoken += words
    return shots


def _events_in(events, start_words, words, total):
    """The parent's events, each kept on the slice whose stretch of the line
    contains it, its fraction rescaled to that slice."""
    lo, hi = start_words / total, (start_words + words) / total
    kept = []
    for event in events:
        fraction = event.get("at_fraction") or 0
        if lo <= fraction < hi or (hi == 1.0 and fraction == 1.0):
            local = (fraction - lo) / (hi - lo) if hi > lo else 0.5
            kept.append({**event, "at_fraction": round(local, 3)})
    return kept


def _words(texts):
    return " ".join(" ".join(t.split()) for t in texts)


def _count(text):
    return len(text.split())
