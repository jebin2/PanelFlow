"""The video's punctuation — event and transition hits — baked into the score.

The renderer used to play static MP3 one-shots for these: a whoosh under a
slide, a rumble under a tremble. Phase 2 moves them into the music track, where
they share the score's loudness, its room, and its ducking under narration.

Everything here is code, deliberately. *Where* a hit lands is arithmetic over
the manifest — the same cursor the renderer lays panels out with — and a
longform has far too many hits for a model to place reliably. *What* a hit
sounds like is a fixed palette of pitch-stable percussion, so the layer cannot
clash with whatever key the composer chose for the bed. The model composes
only the bed, as before.

The static files stay in the renderer as the fallback: a video whose score
failed plays them exactly as it always did.
"""
import math

from .. import motion
from .compile import TRANSITION_FRAMES

# Which director vocabulary earns a hit — mirrors the renderer's old SFX maps
# (shockwave stays silent there too; it decorates too many panels to score).
EVENT_KINDS = {"tremble": "rumble", "rattle": "rumble",
               "flash": "strike", "heartbeat": "heartbeat"}
TRANSITION_KINDS = {"slide": "whoosh", "wipe": "whoosh",
                    "whip_pan": "whoosh", "push": "whoosh"}

# Each hit is a short figure on consecutive quarter-cycles: the pitches, the
# GM voice, the level under the bed. `early` starts a hit ahead of its mark —
# the reverse cymbal is a riser, and a riser crests on the cut, not after it.
PALETTE = {
    "rumble":    {"steps": ["c1"],       "voice": "gm_timpani",        "gain": 0.5},
    "strike":    {"steps": ["c6"],       "voice": "gm_glockenspiel",   "gain": 0.35},
    "heartbeat": {"steps": ["c1", "c1"], "voice": "gm_taiko_drum",     "gain": 0.45},
    # The GM reverse cymbal rises for ~1.3s from its onset (measured), so three
    # quarters of anticipation put the crest just ahead of the cut it scores.
    "whoosh":    {"steps": ["c4"],       "voice": "gm_reverse_cymbal", "gain": 0.45,
                  "early": 3},
}

# A quarter-cycle is the hit grid: at 0.5 cps that is half a second, so a hit
# lands within a quarter second of its frame — punctuation, not lip-sync.
QUARTERS_PER_CYCLE = 4


def timeline(manifest, lead_seconds):
    """Every hit as (seconds on the music clock, kind).

    The clock starts at frame 0 of the video, so panel time is offset by the
    intro bookend. The cursor is the renderer's: ceil-frames per panel, pulled
    back by the transition overlap wherever a transition actually plays.
    """
    fps = manifest["fps"]
    panels = manifest["panels"]
    hits = []
    cursor = 0
    for i, panel in enumerate(panels):
        transition = _transition(panels, i, fps)
        if transition != "none":
            cursor -= TRANSITION_FRAMES
        kind = TRANSITION_KINDS.get(transition)
        if kind:
            hits.append((lead_seconds + cursor / fps, kind))
        for event in panel.get("events") or []:
            kind = EVENT_KINDS.get(event["type"])
            if kind:
                hits.append((lead_seconds + cursor / fps + event["startSeconds"], kind))
        cursor += math.ceil(panel["durationInSeconds"] * fps)
    return hits


def _transition(panels, i, fps):
    """The transition that actually plays into panel i — PanelSequences.tsx's
    effectiveTransition/resolveTransition, replicated so a hit sounds exactly
    where a whoosh used to."""
    if i == 0:
        return "none"
    raw = panels[i].get("transitionIn") or "none"
    if raw == "none":
        return "none"
    frames = math.ceil(panels[i]["durationInSeconds"] * fps)
    previous = math.ceil(panels[i - 1]["durationInSeconds"] * fps)
    if frames < TRANSITION_FRAMES or previous < TRANSITION_FRAMES:
        return "none"
    # A fade makes no sound, so a downgraded transition earns no whoosh.
    return motion.resolve(raw, panels[i].get("animation"))


def layers(hits, total_cycles, cps):
    """The hits as Strudel layers to stack over the bed — one per kind used.

    Each layer is one angle-bracket sequence with a slot per cycle, so it
    advances with the track and every hit fires exactly once; a cycle with a
    hit opens into its four quarters. `.clip(4)` lets each strike ring past
    its quarter instead of being choked at the grid.
    """
    out = []
    quarters = total_cycles * QUARTERS_PER_CYCLE
    for kind, spec in PALETTE.items():
        slots = [None] * quarters
        for seconds, hit_kind in (h for h in hits if h[1] == kind):
            at = round(seconds * cps * QUARTERS_PER_CYCLE) - spec.get("early", 0)
            at = max(0, min(quarters - len(spec["steps"]), at))
            for j, step in enumerate(spec["steps"]):
                slots[at + j] = step
        if any(slots):
            out.append(f'note("<{_pattern(slots)}>")'
                       f'.s("{spec["voice"]}").gain({spec["gain"]}).clip(4)')
    return out


def _pattern(slots):
    cycles = [slots[i:i + QUARTERS_PER_CYCLE]
              for i in range(0, len(slots), QUARTERS_PER_CYCLE)]
    return " ".join(
        "~" if not any(cycle) else "[" + " ".join(s or "~" for s in cycle) + "]"
        for cycle in cycles)
