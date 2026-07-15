"""Response schemas for the Stage 1 LLM calls. Declarative only, no logic."""
from google import genai

T = genai.types.Type
S = genai.types.Schema

PANEL_ROLES = ["establishing", "action", "reaction", "dialogue", "reveal", "transition"]
DIALOGUE_KINDS = ["speech", "thought", "caption", "sfx"]
CONFIDENCE = ["high", "medium", "low"]
BEATS = ["setup", "inciting", "rising", "climax", "resolution"]

_DIALOGUE = S(
    type=T.ARRAY,
    items=S(
        type=T.OBJECT,
        required=["speaker", "text", "kind"],
        properties={
            "speaker": S(type=T.STRING, description="Character name if visible, else empty string"),
            "text": S(type=T.STRING),
            "kind": S(type=T.STRING, enum=DIALOGUE_KINDS),
        },
    ),
)

_BBOX = S(type=T.ARRAY, items=S(type=T.INTEGER), min_items=4, max_items=4)

PAGE_ANALYSIS = S(
    type=T.OBJECT,
    required=["scene_summary", "mood", "page_type", "panels"],
    properties={
        "scene_summary": S(type=T.STRING, description="What happens on this page, one or two sentences"),
        "mood": S(type=T.STRING),
        "page_type": S(type=T.STRING, enum=["cover", "story", "splash", "credits", "ad", "recap"]),
        "continuity_note": S(type=T.STRING),
        "reading_order_suspect": S(type=T.BOOLEAN),
        "content_warnings": S(type=T.ARRAY, items=S(type=T.STRING)),
        "unassigned_dialogue": _DIALOGUE,
        "new_characters": S(
            type=T.ARRAY,
            description="Characters seen on this page that are not already in the roster",
            items=S(
                type=T.OBJECT,
                required=["id", "visual", "first_panel"],
                properties={
                    "id": S(type=T.STRING, description="snake_case slug; a real name ONLY if grounded on-page"),
                    "name": S(type=T.STRING, description="Empty unless the name appears in on-page text"),
                    "visual": S(type=T.STRING),
                    "first_panel": S(type=T.INTEGER),
                    "named_by_panel": S(type=T.INTEGER, description="Panel whose text names them, 0 if none"),
                    "inferred_identity": S(type=T.STRING, description="World-knowledge guess, empty if none"),
                },
            ),
        ),
        "panels": S(
            type=T.ARRAY,
            items=S(
                type=T.OBJECT,
                required=["id", "role", "description", "intensity", "skippable", "characters", "dialogue"],
                properties={
                    "id": S(type=T.INTEGER, description="Panel id as given in the prompt"),
                    "role": S(type=T.STRING, enum=PANEL_ROLES),
                    "description": S(type=T.STRING),
                    "intensity": S(type=T.INTEGER, description="1 calm to 5 peak action"),
                    "skippable": S(type=T.BOOLEAN),
                    "focal_point": S(
                        type=T.ARRAY, items=S(type=T.NUMBER), min_items=2, max_items=2,
                        description="Subject position normalised to the panel, [x, y] in 0..1",
                    ),
                    "text_regions": S(type=T.ARRAY, items=_BBOX,
                                      description="Speech bubble boxes in PAGE pixel coords"),
                    "characters": S(
                        type=T.ARRAY,
                        items=S(
                            type=T.OBJECT,
                            required=["ref", "confidence", "evidence"],
                            properties={
                                "ref": S(type=T.STRING, description="Roster id, or a new_characters id"),
                                "confidence": S(type=T.STRING, enum=CONFIDENCE),
                                "evidence": S(type=T.STRING, description="What is visibly true"),
                            },
                        ),
                    ),
                    "dialogue": _DIALOGUE,
                },
            ),
        ),
    },
)

RECONCILE = S(
    type=T.OBJECT,
    required=["merges", "updates"],
    properties={
        "merges": S(
            type=T.ARRAY,
            items=S(
                type=T.OBJECT,
                required=["from_id", "into_id", "evidence"],
                properties={
                    "from_id": S(type=T.STRING),
                    "into_id": S(type=T.STRING),
                    "evidence": S(type=T.STRING),
                },
            ),
        ),
        "updates": S(
            type=T.ARRAY,
            items=S(
                type=T.OBJECT,
                required=["id"],
                properties={
                    "id": S(type=T.STRING),
                    "name": S(type=T.STRING, description="Only if grounded in on-page text"),
                    "named_by_page": S(type=T.INTEGER),
                    "named_by_panel": S(type=T.INTEGER),
                    "aliases": S(type=T.ARRAY, items=S(type=T.STRING)),
                    "role_in_story": S(type=T.STRING, enum=["protagonist", "antagonist", "supporting", "background"]),
                    "inferred_identity": S(type=T.STRING, description="Single consistent value, empty to clear"),
                },
            ),
        ),
    },
)

STORY = S(
    type=T.OBJECT,
    required=["synopsis", "main_characters", "beats"],
    properties={
        "synopsis": S(type=T.STRING),
        "main_characters": S(type=T.ARRAY, items=S(type=T.STRING, description="Roster ids")),
        "beats": S(
            type=T.ARRAY,
            items=S(
                type=T.OBJECT,
                required=["beat", "pages"],
                properties={
                    "beat": S(type=T.STRING, enum=BEATS),
                    "pages": S(type=T.ARRAY, items=S(type=T.INTEGER)),
                },
            ),
        ),
        "skip_overrides": S(
            type=T.ARRAY,
            items=S(
                type=T.OBJECT,
                required=["page", "panel", "skippable", "reason"],
                properties={
                    "page": S(type=T.INTEGER),
                    "panel": S(type=T.INTEGER),
                    "skippable": S(type=T.BOOLEAN),
                    "reason": S(type=T.STRING),
                },
            ),
        ),
    },
)
