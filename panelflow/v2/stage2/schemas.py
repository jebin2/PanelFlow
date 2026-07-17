"""Response schema for the Stage 2 director. Declarative only, no logic.

The vocabularies are not ours to invent: they are what remotion-animation-kit
renders (`AnimationName`, `TransitionName`) plus PanelFlow's two additions in
remotion-comic/src/types.ts. A name outside these lists validates here and then
fails at render, so they are transcribed rather than remembered — check
`remotion-animation-kit/src/types.ts` before editing.
"""
from google import genai

T = genai.types.Type
S = genai.types.Schema

# AnimationName, grouped as the kit groups them — the grouping is what the
# prompt teaches the director to choose by.
CAMERA = ["ken_burns", "zoom_in", "zoom_out", "pan_up", "pan_down", "creep", "fade_in"]
IMPACT = ["burst", "snap", "punch_in", "recoil", "shockwave", "flash"]
TENSION = ["heartbeat", "tremble", "breathe", "rattle"]
DIRECTIONAL = ["slam_left", "slam_right", "whip_left", "whip_right",
               "slide_left", "slide_right", "slide_top", "slide_bottom",
               "tilt_in", "spin_in"]
PANELFLOW_OWN = ["assemble", "three_part_build_up"]
ANIMATIONS = CAMERA + IMPACT + TENSION + DIRECTIONAL + PANELFLOW_OWN

TRANSITIONS = ["none", "fade", "slide", "wipe", "flip", "toss",
               "clock_wipe", "iris", "zoom_through", "whip_pan",
               "halftone", "push", "barn_door"]

# PanelEvent.type — overlaps the animation names but is not the same thing: an
# event fires *during* a shot, an animation *is* the shot's movement. The last
# four are event-only, rendered by PanelWithEvents in remotion-comic.
EVENTS = ["tremble", "flash", "shockwave", "heartbeat", "rattle",
          "zoom_punch", "speed_lines", "vignette_pulse", "color_drain",
          "invert_flash", "black_flash", "blur_pulse", "zoom_pull"]

SOURCE_KINDS = ["panel", "full_page", "pan"]
ANIMATION_TARGETS = ["focal_point", "whole"]

_SOURCE = S(
    type=T.OBJECT,
    required=["kind", "page"],
    properties={
        "kind": S(type=T.STRING, enum=SOURCE_KINDS),
        "page": S(type=T.INTEGER),
        "panel": S(type=T.INTEGER, description="Required when kind=panel"),
        "from_panel": S(type=T.INTEGER, description="Required when kind=pan"),
        "to_panel": S(type=T.INTEGER, description="Required when kind=pan"),
    },
)

_EVENTS = S(
    type=T.ARRAY,
    items=S(
        type=T.OBJECT,
        required=["type", "at_fraction"],
        properties={
            "type": S(type=T.STRING, enum=EVENTS),
            "at_fraction": S(type=T.NUMBER, description="0..1 through the shot"),
        },
    ),
)

_SHOT = S(
    type=T.OBJECT,
    required=["source", "narration", "animation", "animation_target", "transition_in", "why"],
    properties={
        "source": _SOURCE,
        "narration": S(type=T.STRING, description='Spoken words only. "" for a silent beat shot.'),
        "animation": S(type=T.STRING, enum=ANIMATIONS),
        "animation_target": S(type=T.STRING, enum=ANIMATION_TARGETS),
        "transition_in": S(type=T.STRING, enum=TRANSITIONS),
        "silent_seconds": S(type=T.NUMBER, description="Only when narration is empty"),
        "events": _EVENTS,
        "why": S(type=T.STRING, description="One line of rationale, for debugging pacing"),
    },
)

_META = S(
    type=T.OBJECT,
    required=["youtube_title", "description", "twitter_post", "thumbnail"],
    properties={
        "youtube_title": S(type=T.STRING),
        "description": S(type=T.STRING),
        "twitter_post": S(type=T.STRING),
        "thumbnail": S(
            type=T.OBJECT,
            required=["page", "panel"],
            properties={"page": S(type=T.INTEGER), "panel": S(type=T.INTEGER)},
        ),
        "outro": S(
            type=T.OBJECT,
            required=["page", "panel"],
            properties={"page": S(type=T.INTEGER), "panel": S(type=T.INTEGER)},
            description="Longform only: the panel shown dimmed behind the end card",
        ),
    },
)

DIRECTION = S(
    type=T.OBJECT,
    required=["shots", "music", "meta"],
    properties={
        "shots": S(type=T.ARRAY, items=_SHOT),
        "music": S(
            type=T.OBJECT,
            required=["mood"],
            properties={"mood": S(type=T.STRING, description="One mood for the whole video")},
        ),
        "meta": _META,
    },
)
