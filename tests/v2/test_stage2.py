"""Stage 2: the director's digest, and the checks that gate a render.

2.3 is the interesting half. Every check here is what stands between a model's
enthusiasm and a broken video, so they are tested against the shapes real output
actually took.
"""
import copy

import pytest

from panelflow.v2 import llm
from panelflow.v2.paths import Assets
from panelflow.v2.stage1 import extract, split
from panelflow.v2.stage2 import digest, longform, validate

DIRECTION = {
    "music": {"mood": "tense"},
    "meta": {"youtube_title": "T", "description": "D", "twitter_post": "P",
             "thumbnail": {"page": 1, "panel": 1}},
    "shots": [
        {"source": {"kind": "panel", "page": 1, "panel": 1},
         "narration": "A figure waits.", "animation": "ken_burns",
         "animation_target": "whole", "transition_in": "none",
         "silent_seconds": None, "events": [], "why": "establishing"},
        {"source": {"kind": "panel", "page": 2, "panel": 1},
         "narration": "Then it moves.", "animation": "zoom_out",
         "animation_target": "focal_point", "transition_in": "fade",
         "silent_seconds": None, "events": [], "why": "close"},
    ],
}


@pytest.fixture
def directed(ready_book):
    """A validated-shaped direction over the stubbed 2-page book."""
    def build(**overrides):
        direction = copy.deepcopy(DIRECTION)
        direction.update(overrides)
        direction["target"] = "longform"
        for shot_id, shot in enumerate(direction["shots"], start=1):
            shot["id"] = shot_id
        return direction
    return build


@pytest.fixture
def ready_book(comic_folder, fake_extractor):
    """A book as Stage 1 leaves it: 2 pages, 2 panels each, 1.6 passed.

    Written directly rather than by running 1.3–1.5 against a stubbed model.
    Stage 2 consumes Stage 1's *output*, so that output is the fixture — no
    reason to drag the analyse/reconcile stubs in here and couple the two.
    """
    fake_extractor()
    assets = Assets(comic_folder())
    extract.run(assets)          # deterministic, no LLM
    split.run(assets)

    for index in assets.page_indices():
        page = assets.load_page(index)
        page["status"] = "analyzed"
        page["analysis"] = {
            "prompt_version": "v2", "scene_summary": "A figure waits in the rain.",
            "mood": "tense", "continuity_note": "", "reading_order_suspect": False,
            "content_warnings": [], "unassigned_dialogue": [],
        }
        for panel_id, panel in enumerate(page["panels"], start=1):
            panel.update({
                "role": "establishing" if panel_id == 1 else "reaction",
                "description": "A figure stands in the rain.",
                "intensity": 2 if panel_id == 1 else 3,
                "skippable": panel_id == 2,
                "focal_point": [0.5, 0.5],
                "characters": [{"ref": "wolverine", "confidence": "high", "evidence": "claws"}],
                "dialogue": [],
            })
        assets.save_page(index, page)

    characters = assets.load_characters()
    for character in characters.get("characters", []):
        character.setdefault("visual", "a figure in a coat")
        character.setdefault("role_in_story", "supporting")
    characters["reconciled"] = True
    assets.save_characters(characters)

    book = assets.load_book()
    book["story"] = {"synopsis": "A figure waits.", "main_characters": ["wolverine"],
                     "beats": [{"beat": "setup", "pages": [1]}], "skip_overrides": []}
    book.setdefault("analysis", {})["completed_at"] = "2026-01-01T00:00:00Z"
    assets.save_book(book)
    assets.rebuild_index()
    return assets


# ---------------------------------------------------------------- the digest

def test_the_director_is_told_the_effective_skippability(ready_book):
    """1.3 marks a panel skippable from the pages before it; 1.5 overturns that
    with the whole book. The director is handed the answer, not both lists."""
    book = ready_book.load_book()
    book["story"] = {"skip_overrides": [
        {"page": 1, "panel": 2, "skippable": False, "reason": "sets up the ending"}]}
    ready_book.save_book(book)

    text = digest.book_text(ready_book)

    assert "sets up the ending" in text
    # panel 2 is skippable:true in the stub; the override must win
    page_1 = text.split("## Page 2")[0]
    assert "panel 2 [reaction, intensity 3]" in page_1
    assert "panel 2 [reaction, intensity 3, SKIPPABLE]" not in page_1


def test_a_named_character_is_sayable_and_an_unnamed_one_is_described(ready_book):
    """The director never sees pixels, so appearance is noise — except for
    someone the book never names, where it is the only thing to call them."""
    characters = ready_book.load_characters()
    characters["characters"].append({
        "id": "winding_creature", "name": None, "visual": "long, ribbon-like, tan",
        "role_in_story": "supporting", "inferred_identity": None,
    })
    ready_book.save_characters(characters)

    lines = {line.split(" |")[0].lstrip("- "): line
             for line in digest.roster_text(characters).splitlines()}

    assert 'say "Wolverine"' in lines["wolverine"]
    assert "looks like" not in lines["wolverine"]        # pointless without eyes
    assert "NOT named in this book" in lines["winding_creature"]
    assert "looks like: long, ribbon-like, tan" in lines["winding_creature"]


def test_spreads_and_suspect_ordering_reach_the_director(ready_book):
    page = ready_book.load_page(1)
    page["is_spread"] = True
    page["analysis"]["reading_order_suspect"] = True
    page["analysis"]["content_warnings"] = ["blood"]
    ready_book.save_page(1, page)

    text = digest.book_text(ready_book)

    assert "SPREAD" in text
    assert "READING ORDER SUSPECT" in text
    assert "CONTENT WARNING: blood" in text


# ---------------------------------------------------------------- 2.3 validate

def test_a_clean_direction_passes(ready_book, directed):
    assert validate.check(ready_book, directed()) == []


def test_a_shot_pointing_at_a_missing_page_is_caught(ready_book, directed):
    direction = directed()
    direction["shots"][0]["source"] = {"kind": "panel", "page": 99, "panel": 1}

    problems = validate.check(ready_book, direction)

    assert any("page 99 does not exist" in p for p in problems)


def test_a_shot_pointing_at_a_missing_panel_is_caught(ready_book, directed):
    direction = directed()
    direction["shots"][0]["source"] = {"kind": "panel", "page": 1, "panel": 99}

    problems = validate.check(ready_book, direction)

    assert any("panel 99 is not on page 1" in p for p in problems)


def test_an_animation_the_renderer_cannot_play_is_caught(ready_book, directed):
    """The enum is remotion-animation-kit's, not ours — a name outside it
    validates here and then dies at render."""
    direction = directed()
    direction["shots"][0]["animation"] = "matrix_bullet_time"

    assert any("unknown animation" in p for p in validate.check(ready_book, direction))


def test_an_event_with_the_wrong_key_is_caught(ready_book, directed):
    """Verbatim from the first real run: the model wrote {"name": "tremble"}."""
    direction = directed()
    direction["shots"][0]["events"] = [{"name": "tremble", "at_fraction": 0.6}]

    assert any("unknown event" in p for p in validate.check(ready_book, direction))


def test_silent_seconds_on_a_speaking_shot_is_caught(ready_book, directed):
    """Also from the real run: silent_seconds used as a hold after narration."""
    direction = directed()
    direction["shots"][0]["silent_seconds"] = 3

    assert any("has narration and silent_seconds" in p
               for p in validate.check(ready_book, direction))


def test_a_silent_shot_needs_a_duration(ready_book, directed):
    direction = directed()
    direction["shots"][0]["narration"] = ""
    direction["shots"][0]["silent_seconds"] = None

    assert any("silent shot without silent_seconds" in p
               for p in validate.check(ready_book, direction))


def test_a_pan_across_a_suspect_page_is_caught(ready_book, directed):
    page = ready_book.load_page(1)
    page["analysis"]["reading_order_suspect"] = True
    ready_book.save_page(1, page)
    direction = directed()
    direction["shots"][0]["source"] = {"kind": "pan", "page": 1, "from_panel": 1, "to_panel": 2}

    assert any("panel order is suspect" in p for p in validate.check(ready_book, direction))


def test_longform_may_skip_pages_but_not_beats(ready_book, directed):
    book = ready_book.load_book()
    book["story"] = {"beats": [{"beat": "climax", "pages": [2]}]}
    ready_book.save_book(book)
    direction = directed()
    direction["shots"] = direction["shots"][:1]      # drops the only page-2 shot
    direction["shots"][0]["id"] = 1

    problems = validate.check(ready_book, direction)

    assert any("has no shot" in p and "climax" in p for p in problems)


def test_the_first_shot_must_not_transition_in(ready_book, directed):
    direction = directed()
    direction["shots"][0]["transition_in"] = "fade"

    assert any("must open with transition_in 'none'" in p
               for p in validate.check(ready_book, direction))


# ------------------------------------------------- the naming rule, grounded

def test_a_name_from_nowhere_is_caught(ready_book, directed):
    """The whole point: the director may not name someone the book never names."""
    direction = directed()
    direction["shots"][0]["narration"] = "Deep in the night, Gambit makes his move."

    problems = validate.check(ready_book, direction)

    assert any("'Gambit'" in p and "never says" in p for p in problems)


def test_words_the_book_itself_says_are_allowed(ready_book, directed):
    """Real false positive: 'Vee-Shanti' was flagged as invented, though page 6
    shouts it. Place names and coined nonsense are the book's to coin."""
    page = ready_book.load_page(1)
    page["panels"][0]["dialogue"] = [
        {"text": "WHERE IS THE VEE-SHANTI AFFORDANCE?!", "kind": "speech", "speaker": ""}]
    ready_book.save_page(1, page)
    direction = directed()
    direction["shots"][0]["narration"] = "She finds the Vee-Shanti Affordance in a box."

    assert validate.check(ready_book, direction) == []


def test_a_capital_that_opens_a_sentence_is_grammar_not_a_name(ready_book, directed):
    """Real false positive: "…Afanaf. He's been here since dawn." flagged He's."""
    direction = directed()
    direction["shots"][0]["narration"] = "A figure waits. He's been here since dawn."

    assert validate.check(ready_book, direction) == []


def test_narration_with_markup_is_caught(ready_book, directed):
    """TTS reads brackets aloud."""
    direction = directed()
    direction["shots"][0]["narration"] = "A figure waits. [dramatic pause] Then nothing."

    assert any("markup or a stage direction" in p
               for p in validate.check(ready_book, direction))


# ---------------------------------------------------------------- 2.1 gate

def test_the_director_refuses_assets_stage_1_never_validated(ready_book, monkeypatch):
    book = ready_book.load_book()
    book["analysis"].pop("completed_at")
    ready_book.save_book(book)

    with pytest.raises(ValueError, match="Stage 1 is not complete"):
        longform.run(ready_book)


def test_shot_ids_are_assigned_here_not_asked_for(ready_book, monkeypatch):
    monkeypatch.setattr(llm, "ask_json", lambda **kw: copy.deepcopy(DIRECTION))
    monkeypatch.setattr(longform.llm, "ask_json", lambda **kw: copy.deepcopy(DIRECTION))

    longform.run(ready_book)

    direction = ready_book.load_direction("longform")
    assert [s["id"] for s in direction["shots"]] == [1, 2]
    assert direction["validated"] is False      # 2.3 owns that flag
