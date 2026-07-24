"""Stage 2: the director's digest, and the checks that gate a render.

2.3 is the interesting half. Every check here is what stands between a model's
enthusiasm and a broken video, so they are tested against the shapes real output
actually took.
"""
import copy

import pytest

from panelflow import llm
from panelflow.paths import Assets
from panelflow.stage1 import extract, split
from panelflow.stage2 import digest, direct, validate

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


@pytest.fixture(autouse=True)
def clean_names(monkeypatch):
    """2.3 asks a model whether the narration names anyone it should not.

    Default it to "nobody", so every other check is tested on its own; the tests
    that care about naming install their own answer.
    """
    monkeypatch.setattr(validate.llm, "ask_json", lambda **kw: {"violations": []})


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


def test_a_transition_the_renderer_would_downgrade_is_caught(ready_book, directed):
    """Batwoman #5's shorts asked for whip_pan over whip_right and would have
    played a fade, with the file on disk still claiming whip_pan."""
    direction = directed(shots=[
        {"source": {"kind": "panel", "page": 1, "panel": 1}, "narration": "One.",
         "animation": "ken_burns", "animation_target": "whole", "transition_in": "none",
         "silent_seconds": None, "speaker": None, "events": []},
        {"source": {"kind": "panel", "page": 1, "panel": 1}, "narration": "Two.",
         "animation": "whip_right", "animation_target": "whole", "transition_in": "whip_pan",
         "silent_seconds": None, "speaker": None, "events": []},
    ])

    problems = validate.check(ready_book, direction)

    assert any("fights animation" in p and "shot 2" in p for p in problems)


def test_a_transition_that_survives_is_left_alone(ready_book, directed):
    """toss is neutral, so it plays over a directional animation untouched."""
    direction = directed(shots=[
        {"source": {"kind": "panel", "page": 1, "panel": 1}, "narration": "One.",
         "animation": "ken_burns", "animation_target": "whole", "transition_in": "none",
         "silent_seconds": None, "speaker": None, "events": []},
        {"source": {"kind": "panel", "page": 1, "panel": 1}, "narration": "Two.",
         "animation": "whip_right", "animation_target": "whole", "transition_in": "toss",
         "silent_seconds": None, "speaker": None, "events": []},
    ])

    assert not any("fights animation" in p for p in validate.check(ready_book, direction))


def test_the_first_shot_must_not_transition_in(ready_book, directed):
    direction = directed()
    direction["shots"][0]["transition_in"] = "fade"

    assert any("must open with transition_in 'none'" in p
               for p in validate.check(ready_book, direction))


# ---------------------------------------------------------------- 2.2 shorts

def _shorts(ready_book, words, first_panel=2, last_animation="zoom_out"):
    """A short whose narration runs to `words`, over the 2-page fixture."""
    direction = copy.deepcopy(DIRECTION)
    direction["target"] = "shorts"
    direction["shots"][0]["source"] = {"kind": "panel", "page": 1, "panel": first_panel}
    direction["shots"][0]["narration"] = " ".join(["word"] * words)
    direction["shots"][1]["narration"] = ""
    direction["shots"][1]["silent_seconds"] = 2
    direction["shots"][1]["animation"] = last_animation
    for shot_id, shot in enumerate(direction["shots"], start=1):
        shot["id"] = shot_id
    return direction


def test_a_brief_short_is_fine(ready_book):
    """Only the ceiling is hard. A short that runs shorter is a shorter short,
    not a defect — the first real render came out at 47s and was right to."""
    problems = validate.check(ready_book, _shorts(ready_book, words=100))

    assert not any("ceiling" in p for p in problems)


def test_a_short_over_two_minutes_is_caught(ready_book):
    """3.5 words/second, so 500 words ≈ 143s — over the 120s ceiling."""
    problems = validate.check(ready_book, _shorts(ready_book, words=500))

    assert any("over the 120s ceiling" in p for p in problems)


def test_a_short_under_the_ceiling_passes(ready_book):
    """200 words ≈ 57s. Panel 2 of the fixture is intensity 3 — bump it so the
    hook rule is satisfied and only the length is under test."""
    page = ready_book.load_page(1)
    page["panels"][1]["intensity"] = 5
    ready_book.save_page(1, page)

    assert validate.check(ready_book, _shorts(ready_book, words=200)) == []


def test_a_short_that_opens_quietly_is_caught(ready_book):
    """The first two seconds decide whether anyone sees the third."""
    direction = _shorts(ready_book, words=200, first_panel=1)   # panel 1 is intensity 2

    problems = validate.check(ready_book, direction)

    assert any("must hook on 4 or 5" in p for p in problems)


def test_a_short_ending_on_an_impact_animation_is_caught(ready_book):
    page = ready_book.load_page(1)
    page["panels"][1]["intensity"] = 5
    ready_book.save_page(1, page)

    direction = _shorts(ready_book, words=200, last_animation="burst")

    assert any("last shot should end on" in p for p in validate.check(ready_book, direction))


def test_longform_is_not_held_to_the_shorts_window(ready_book, directed):
    """Longform is unbudgeted by design — the story decides its length."""
    direction = directed()
    direction["shots"][0]["narration"] = " ".join(["word"] * 5000)

    assert not any("window" in p for p in validate.check(ready_book, direction))


# ------------------------------------------------- the naming rule, grounded

def test_a_reported_name_becomes_a_violation(ready_book, directed, monkeypatch):
    """The whole point: the director may not name someone the book never names."""
    monkeypatch.setattr(validate.llm, "ask_json",
                        lambda **kw: {"violations": [{"shot": 1, "name": "Gambit"}]})
    direction = directed()

    problems = validate.check(ready_book, direction)

    assert any("'Gambit'" in p and "never names" in p for p in problems)


def test_the_whole_narration_is_sent_unfiltered(ready_book, directed, monkeypatch):
    """No rule may pre-filter which words are worth asking about — deciding that
    is the question itself. "Strange" is in this book's own title, so a filter
    would never ask about "Doctor Strange", which is the one name that matters."""
    seen = {}

    def fake(system_prompt, user_prompt, **kw):
        seen.setdefault(kw.get("label"), user_prompt)
        return {"violations": []}
    monkeypatch.setattr(validate.llm, "ask_json", fake)

    direction = directed()
    direction["shots"][0]["narration"] = "The sorcerer Doctor Strange watches."
    validate.check(ready_book, direction)

    prompt = seen["checking narration for invented names"]
    assert "Doctor Strange" in prompt                  # not filtered out
    assert "Then it moves." in prompt                  # every speaking shot
    assert '"Wolverine"' in prompt                     # who may be named


def test_unnamed_characters_are_listed_for_the_name_check(ready_book, directed, monkeypatch):
    characters = ready_book.load_characters()
    characters["characters"].append(
        {"id": "winding_creature", "name": None, "visual": "long, ribbon-like, tan"})
    ready_book.save_characters(characters)
    seen = {}
    monkeypatch.setattr(validate.llm, "ask_json",
                        lambda **kw: seen.setdefault(kw.get("label"), kw["user_prompt"])
                        and {"violations": []} or {"violations": []})

    validate.check(ready_book, directed())

    assert ("winding_creature — long, ribbon-like, tan"
            in seen["checking narration for invented names"])


def test_the_books_own_words_are_given_to_the_name_check(ready_book, directed, monkeypatch):
    """A caption can name someone the roster never records — "The Count" for a
    vampire nobody entered by that name. The checker must see the book's words,
    or it flags a name the book plainly uses as if it were invented."""
    page = ready_book.load_page(1)
    page["panels"][0]["dialogue"] = [
        {"text": "THE COUNT saved my brain.", "kind": "caption"}]
    ready_book.save_page(1, page)
    seen = {}
    monkeypatch.setattr(validate.llm, "ask_json",
                        lambda **kw: seen.setdefault(kw.get("label"), kw["user_prompt"])
                        and {"violations": []} or {"violations": []})

    validate.check(ready_book, directed())

    prompt = seen["checking narration for invented names"]
    assert "THE BOOK'S OWN WORDS" in prompt
    assert "THE COUNT saved my brain." in prompt


def test_a_silent_book_asks_nobody(ready_book, directed, monkeypatch):
    """No narration, no question — do not spend a call to hear 'nothing'."""
    def boom(**kw):
        raise AssertionError("should not have asked")
    monkeypatch.setattr(validate.llm, "ask_json", boom)

    direction = directed()
    for shot in direction["shots"]:
        shot["narration"] = ""
        shot["silent_seconds"] = 2

    validate.check(ready_book, direction)      # must not raise


def test_a_failed_name_check_is_fatal_not_skipped(ready_book, directed, monkeypatch):
    """Swallowing this would ship the video it exists to stop."""
    def boom(**kw):
        raise RuntimeError("TTT down")
    monkeypatch.setattr(validate.llm, "ask_json", boom)

    with pytest.raises(RuntimeError, match="could not check narration names"):
        validate.check(ready_book, directed())


def test_narration_with_markup_is_caught(ready_book, directed):
    """TTS reads brackets aloud."""
    direction = directed()
    direction["shots"][0]["narration"] = "A figure waits. [dramatic pause] Then nothing."

    assert any("markup or a stage direction" in p
               for p in validate.check(ready_book, direction))


# ---------------------------------------------------------------- 2.1 gate

def test_the_director_refuses_assets_stage_1_never_validated(ready_book):
    book = ready_book.load_book()
    book["analysis"].pop("completed_at")
    ready_book.save_book(book)

    with pytest.raises(ValueError, match="Stage 1 is not complete"):
        direct.run(ready_book, "longform")


def test_shot_ids_are_assigned_here_not_asked_for(ready_book, monkeypatch):
    monkeypatch.setattr(direct.llm, "ask_json", lambda **kw: copy.deepcopy(DIRECTION))

    direct.run(ready_book, "longform")

    direction = ready_book.load_direction("longform")
    assert [s["id"] for s in direction["shots"]] == [1, 2]
    assert direction["validated"] is False      # 2.3 owns that flag


def test_a_director_that_named_no_shots_saves_nothing(ready_book, monkeypatch):
    """Batwoman #5: the call came back without shots, an empty direction was
    saved as if it were real, and the run only died in 2.3 — after paying for
    the other target — complaining that 2.1 had never run. A failed call fails
    here, and leaves no file behind to lie about it."""
    monkeypatch.setattr(direct.llm, "ask_json", lambda **kw: {"meta": {"title": "x"}})

    with pytest.raises(ValueError, match="returned no shots"):
        direct.run(ready_book, "longform")

    assert ready_book.load_direction("longform") == {}
    assert not direct.is_done(ready_book, "longform")


def test_both_targets_read_the_same_book_and_differ_only_in_prompt(ready_book, monkeypatch):
    """The philosophies are opposed, and all of that lives in the system prompt:
    one call cannot cover a story evenly and cut it to the bone at once."""
    seen = {}

    def fake(system_prompt, user_prompt, **kw):
        seen.setdefault("prompts", []).append(system_prompt)
        seen.setdefault("books", []).append(user_prompt)
        return copy.deepcopy(DIRECTION)
    monkeypatch.setattr(direct.llm, "ask_json", fake)

    direct.run(ready_book, "longform")
    direct.run(ready_book, "shorts")

    assert seen["books"][0] == seen["books"][1]          # same book
    assert seen["prompts"][0] != seen["prompts"][1]      # different job
    assert ready_book.load_direction("shorts")["target"] == "shorts"
    assert "120 seconds" in seen["prompts"][1]           # the hard ceiling


def test_a_grounded_relationship_reaches_the_director(ready_book):
    """1.4's grounded relationships ride the roster line, resolved to sayable
    names, so the narration can retell "her mother" instead of two bare names."""
    characters = ready_book.load_characters()
    characters["characters"].append({
        "id": "kayla", "name": "Kayla", "named_in_story": True,
        "role_in_story": "supporting",
        "relationships": [{"to_id": "wolverine", "relation": "ward",
                           "evidence": "p3: 'he took her in'"}],
    })
    ready_book.save_characters(characters)

    lines = {line.split(" |")[0].lstrip("- "): line
             for line in digest.roster_text(characters).splitlines()}

    assert "ward of Wolverine" in lines["kayla"]
    assert "relationships" not in lines["wolverine"]     # none recorded, none shown


def test_a_relationship_to_an_unnamed_character_offers_no_id_to_say(ready_book):
    """Batwoman #5: "sister of impostor_batwoman" put an internal token exactly
    where a name goes, for a character the roster forbids naming. The relation
    survives — it is usually why the beat lands — but not as a name."""
    characters = ready_book.load_characters()
    characters["characters"].append({
        "id": "masked_twin", "named_in_story": False, "role_in_story": "supporting",
        "visual": "a woman in a cracked cowl",
    })
    characters["characters"].append({
        "id": "kayla", "name": "Kayla", "named_in_story": True,
        "role_in_story": "supporting",
        "relationships": [{"to_id": "masked_twin", "relation": "sister",
                           "evidence": "p7: 'my sister'"}],
    })
    ready_book.save_characters(characters)

    lines = {line.split(" |")[0].lstrip("- "): line
             for line in digest.roster_text(characters).splitlines()}

    assert "sister of masked_twin" not in lines["kayla"]
    assert "sister of the unnamed character" in lines["kayla"]
    assert "never say that id" in lines["kayla"]


def test_a_relationship_pointing_nowhere_is_dropped(ready_book):
    """A target that is not on the roster cannot be named or described, so
    there is nothing the director could do with the relation."""
    characters = ready_book.load_characters()
    characters["characters"].append({
        "id": "kayla", "name": "Kayla", "named_in_story": True,
        "role_in_story": "supporting",
        "relationships": [{"to_id": "ghost", "relation": "daughter", "evidence": "p1"}],
    })
    ready_book.save_characters(characters)

    lines = {line.split(" |")[0].lstrip("- "): line
             for line in digest.roster_text(characters).splitlines()}

    assert "daughter" not in lines["kayla"]
    assert "ghost" not in lines["kayla"]


# ------------------------------------------------- the teller's register

def test_a_voice_defect_becomes_a_local_problem(ready_book, directed, monkeypatch):
    """The three register defects come back as strictly-local repairs; an
    unknown kind from a drifting model is dropped, not crashed on."""
    def fake(**kw):
        if kw.get("label") == "checking narration voice":
            return {"violations": [
                {"shot": 3, "kind": "second_person", "phrase": "your mother"},
                {"shot": 5, "kind": "speaker_not_quote", "phrase": "Her mother shouted:"},
                {"shot": 7, "kind": "too_poetic", "phrase": "not a real kind"},
            ]}
        return {"violations": []}
    monkeypatch.setattr(validate.llm, "ask_json", fake)

    problems = validate.check(ready_book, directed())

    assert any("shot 3" in p and "'your mother'" in p and "third person" in p for p in problems)
    assert any("shot 5" in p and "clear the speaker" in p for p in problems)
    assert not any("shot 7" in p for p in problems)


def test_a_failed_voice_check_is_skipped_not_fatal(ready_book, directed, monkeypatch):
    """Style is not hallucination: names blocking validation is right; a
    register nit blocking a video would not be."""
    def fake(**kw):
        if kw.get("label") == "checking narration voice":
            raise RuntimeError("TTT down")
        return {"violations": []}
    monkeypatch.setattr(validate.llm, "ask_json", fake)

    validate.check(ready_book, directed())     # must not raise
