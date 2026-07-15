"""Sub-stages 1.3–1.5 with a stubbed LLM: what we keep, clamp, and refuse from
a model response. These are the anti-hallucination and anti-corruption gates."""
import pytest

from panelflow.v2 import llm
from panelflow.v2.paths import Assets
from panelflow.v2.stage1 import analyze, extract, reconcile, split, synthesize

PAGE_RESPONSE = {
    "scene_summary": "Logan meets Creed.",
    "mood": "tense",
    "page_type": "story",
    "content_warnings": ["blood"],
    "unassigned_dialogue": [{"speaker": "", "text": "MEANWHILE", "kind": "caption"}],
    "new_characters": [{"id": "hooded_figure", "visual": "hooded", "first_panel": 2, "name": ""}],
    "panels": [
        {"id": 1, "role": "action", "description": "claws out", "intensity": 4, "skippable": False,
         "focal_point": [0.6, 0.4], "text_regions": [[520, 20, 700, 120]],
         "characters": [{"ref": "wolverine", "confidence": "high", "evidence": "claws"}],
         "dialogue": [{"speaker": "Wolverine", "text": "Bub.", "kind": "speech"},
                      {"speaker": "", "text": "SNIKT", "kind": "sfx"}]},
        {"id": 2, "role": "reaction", "description": "creed snarls", "intensity": 3, "skippable": True,
         "focal_point": [0.5, 0.5], "text_regions": [],
         "characters": [{"ref": "hooded_figure", "confidence": "low", "evidence": "hood"}],
         "dialogue": []},
    ],
}


@pytest.fixture
def stub_llm(monkeypatch):
    """Install per-call-type responses; returns the recorded prompts."""
    seen = {}

    def install(page=None, reconcile_result=None, story=None):
        def fake(system_prompt, user_prompt, schema, image_path=None, model=None):
            if "analyse one comic page" in system_prompt:
                seen["page_prompt"] = user_prompt
                return page if page is not None else PAGE_RESPONSE
            if "clean up a comic" in system_prompt:
                seen["reconcile_prompt"] = user_prompt
                return reconcile_result or {"merges": [], "updates": []}
            seen["story_prompt"] = user_prompt
            return story or {"synopsis": "s", "main_characters": [], "beats": [], "skip_overrides": []}

        for module in (llm, analyze.llm, reconcile.llm, synthesize.llm):
            monkeypatch.setattr(module, "ask_json", fake)
        return seen
    return install


@pytest.fixture
def ready(comic_folder, fake_extractor):
    fake_extractor()
    assets = Assets(comic_folder())
    extract.run(assets)
    split.run(assets)
    return assets


# ---------------------------------------------------------------- 1.3 analyze

def test_analyze_fills_page_and_registers_new_characters(ready, stub_llm):
    stub_llm()
    analyze.run(ready)

    page = ready.load_page(1)
    assert page["status"] == "analyzed"
    assert page["analysis"]["scene_summary"] == "Logan meets Creed."
    assert page["analysis"]["content_warnings"] == ["blood"]
    assert page["analysis"]["unassigned_dialogue"][0]["text"] == "MEANWHILE"
    assert "hooded_figure" in {c["id"] for c in ready.load_characters()["characters"]}


def test_analyze_drops_character_refs_that_are_not_in_the_roster(ready, stub_llm):
    """The model inventing a name is the failure this whole design exists to stop."""
    response = _with_panel_edit(0, characters=[
        {"ref": "wolverine", "confidence": "high", "evidence": "claws"},
        {"ref": "Gambit", "confidence": "high", "evidence": "invented"},
    ])
    stub_llm(page=response)
    analyze.run(ready)

    assert [c["ref"] for c in ready.load_page(1)["panels"][0]["characters"]] == ["wolverine"]


def test_analyze_clamps_out_of_range_intensity_and_focal_point(ready, stub_llm):
    stub_llm(page=_with_panel_edit(0, intensity=9, focal_point=[9.9, -3]))
    analyze.run(ready)

    panel = ready.load_page(1)["panels"][0]
    assert panel["intensity"] == 5
    assert panel["focal_point"] == [1.0, 0.0]


def test_analyze_survives_garbage_intensity_and_focal_point(ready, stub_llm):
    stub_llm(page=_with_panel_edit(0, intensity="very high", focal_point="middle"))
    analyze.run(ready)

    panel = ready.load_page(1)["panels"][0]
    assert panel["intensity"] == 3
    assert panel["focal_point"] == [0.5, 0.5]


def test_analyze_keeps_sfx_classified_rather_than_stripping_it(ready, stub_llm):
    stub_llm()
    analyze.run(ready)
    kinds = [d["kind"] for d in ready.load_page(1)["panels"][0]["dialogue"]]
    assert kinds == ["speech", "sfx"]


def test_analyze_keeps_split_geometry_as_truth(ready, stub_llm):
    """1.2 owns bboxes; a model that renumbers or moves panels must not win."""
    before = [p["bbox"] for p in ready.load_page(1)["panels"]]
    stub_llm(page=_with_panel_edit(0, id=99, bbox=[0, 0, 1, 1]))
    analyze.run(ready)

    page = ready.load_page(1)
    assert [p["bbox"] for p in page["panels"]] == before
    assert [p["id"] for p in page["panels"]] == [1, 2]


def test_analyze_cannot_touch_text_regions(ready, stub_llm):
    """OCR measured them in 1.2. A vision model asked for pixel coordinates
    invents them — a real run returned a region below the page bottom — so 1.3
    is not asked, and anything it volunteers is ignored."""
    page = ready.load_page(1)
    page["panels"][0]["text_regions"] = [[50, 20, 300, 120]]
    ready.save_page(1, page)

    stub_llm(page=_with_panel_edit(0, text_regions=[[0, 0, 99999, 99999]]))
    analyze.run(ready)

    assert ready.load_page(1)["panels"][0]["text_regions"] == [[50, 20, 300, 120]]


def test_analyze_prompt_carries_roster_and_previous_pages(ready, stub_llm):
    seen = stub_llm()
    analyze.run(ready)

    prompt = seen["page_prompt"]
    assert "wolverine" in prompt and "sabretooth" in prompt
    assert "Logan meets Creed." in prompt          # page 1's summary reaches page 2
    assert "panel 1: bbox" in prompt


def test_analyze_is_skipped_when_already_current(ready, stub_llm):
    stub_llm()
    analyze.run(ready)
    assert analyze.is_done(ready)


# ---------------------------------------------------------------- 1.4 reconcile

def test_reconcile_merges_and_rewrites_panel_refs(ready, stub_llm):
    stub_llm(reconcile_result={
        "merges": [{"from_id": "hooded_figure", "into_id": "sabretooth", "evidence": "hood removed"}],
        "updates": [{"id": "sabretooth", "role_in_story": "antagonist", "aliases": ["Creed"]}],
    })
    analyze.run(ready)
    reconcile.run(ready)

    ids = {c["id"] for c in ready.load_characters()["characters"]}
    assert "hooded_figure" not in ids
    assert [c["ref"] for c in ready.load_page(1)["panels"][1]["characters"]] == ["sabretooth"]
    assert ready.load_characters()["reconciled"] is True


def test_reconcile_collapses_refs_a_merge_duplicated_within_one_panel(ready, stub_llm):
    page = _with_panel_edit(0, characters=[
        {"ref": "wolverine", "confidence": "high", "evidence": "claws"},
        {"ref": "hooded_figure", "confidence": "low", "evidence": "hood"},
    ])
    stub_llm(page=page, reconcile_result={
        "merges": [{"from_id": "hooded_figure", "into_id": "wolverine", "evidence": "same guy"}],
        "updates": [],
    })
    analyze.run(ready)
    reconcile.run(ready)

    assert [c["ref"] for c in ready.load_page(1)["panels"][0]["characters"]] == ["wolverine"]


def test_reconcile_invalidates_the_story(ready, stub_llm):
    stub_llm()
    analyze.run(ready)
    synthesize.run(ready)
    assert synthesize.is_done(ready)

    characters = ready.load_characters()
    characters["reconciled"] = False
    ready.save_characters(characters)
    reconcile.run(ready)
    assert not synthesize.is_done(ready)


# ---------------------------------------------------------------- 1.5 synthesize

def test_synthesize_drops_references_that_do_not_resolve(ready, stub_llm):
    stub_llm(story={
        "synopsis": "Logan fights Creed.",
        "main_characters": ["wolverine", "ghost"],
        "beats": [{"beat": "climax", "pages": [2, 99]}],
        "skip_overrides": [{"page": 1, "panel": 2, "skippable": False, "reason": "setup"},
                           {"page": 1, "panel": 77, "skippable": True, "reason": "bogus"}],
    })
    analyze.run(ready)
    reconcile.run(ready)
    synthesize.run(ready)

    story = ready.load_book()["story"]
    assert story["main_characters"] == ["wolverine"]
    assert story["beats"] == [{"beat": "climax", "pages": [2]}]
    assert [o["panel"] for o in story["skip_overrides"]] == [2]


def test_synthesize_is_skipped_once_written(ready, stub_llm):
    stub_llm()
    analyze.run(ready)
    synthesize.run(ready)
    assert synthesize.is_done(ready)


def _with_panel_edit(index, **changes):
    import copy
    response = copy.deepcopy(PAGE_RESPONSE)
    response["panels"][index].update(changes)
    return response


def test_story_so_far_does_not_claim_page_two_is_the_first_page(ready, stub_llm):
    """The cover often yields no summary; page 2 must not be told it is page 1."""
    from panelflow.v2.stage1.analyze import _story_so_far

    assert _story_so_far(ready, 1) == "(this is the first page)"
    assert _story_so_far(ready, 2) == "(nothing recorded from earlier pages)"

    page = ready.load_page(1)
    page["analysis"] = {"scene_summary": "Anton reviews the wards."}
    ready.save_page(1, page)
    assert "page 1: Anton reviews the wards." in _story_so_far(ready, 2)
