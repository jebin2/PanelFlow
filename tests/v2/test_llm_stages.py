"""Sub-stages 1.3–1.5 with a stubbed LLM: what we keep, clamp, and refuse from
a model response. These are the anti-hallucination and anti-corruption gates."""
import copy

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
        def fake(system_prompt, user_prompt, schema=None, image_path=None, model=None):
            if "analyse one comic page" in system_prompt:
                seen["page_prompt"] = user_prompt
                return copy.deepcopy(page if page is not None else PAGE_RESPONSE)
            if "match a comic page's dialogue" in system_prompt:
                return {"matches": []}
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


def test_unassigned_captions_are_located_too(monkeypatch):
    """A caption in a gutter is the text least likely to fall inside any panel's
    box, and so the text most worth being able to locate. Verbatim from page 2:
    the caption spans the page, and _locate_dialogue used to walk only panels."""
    page = {
        "page_index": 2,
        "panels": [{"id": 1, "dialogue": [{"text": "OH, AFANAF IS STILL THERE.", "kind": "speech"}]}],
        "analysis": {"unassigned_dialogue": [
            {"text": "THE CITADEL. BELOW THE SANCTUM SANCTORUM.", "kind": "caption"}]},
        "ocr_lines": [
            {"text": "OH, AFANAF", "box": [146, 609, 326, 636]},
            {"text": "THE CITADEL", "box": [247, 17, 547, 57]},
            {"text": "BELOW -THESANGTOMSANGTORUM", "box": [33, 69, 766, 105]},
        ],
    }
    # 0 is the panel's speech, 1 is the unassigned caption: one flat numbering.
    monkeypatch.setattr(analyze.llm, "ask_json", lambda **kw: {"matches": [
        {"dialogue_index": 0, "lines": [0]},
        {"dialogue_index": 1, "lines": [1, 2]},
    ]})

    analyze._locate_dialogue(page, None)

    assert page["panels"][0]["dialogue"][0]["region"] == [146, 609, 326, 636]
    # The union of the caption's two lines, which is what a crop must not cut.
    assert page["analysis"]["unassigned_dialogue"][0]["region"] == [33, 17, 766, 105]


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


# ---------------------------------------------------------------- dialogue location

OCR_LINES = [
    {"text": "OH, AFANAF", "box": [146, 609, 326, 636]},
    {"text": "IS STILL THERE", "box": [142, 640, 330, 667]},
    {"text": "NIGHT....", "box": [186, 732, 288, 763]},
]

SPOKEN_PAGE = {
    **PAGE_RESPONSE,
    "panels": [
        {**PAGE_RESPONSE["panels"][0],
         "dialogue": [{"speaker": "Anton", "kind": "speech",
                       "text": "OH, AFANAF IS STILL THERE... NIGHT..."}]},
        PAGE_RESPONSE["panels"][1],
    ],
}


def _stub_both(monkeypatch, matches=None, match_raises=False):
    """Page analysis and the dialogue match come through the same ask_json."""
    seen = {}

    def fake(system_prompt, user_prompt, schema=None, image_path=None, model=None):
        if "match a comic page's dialogue" in system_prompt:
            if match_raises:
                raise RuntimeError("TTT down")
            seen["match_prompt"] = user_prompt
            return {"matches": matches if matches is not None else []}
        # A fresh copy each call: the stage writes into what it is handed, and a
        # real provider never returns the same object twice.
        return copy.deepcopy(SPOKEN_PAGE)

    monkeypatch.setattr(analyze.llm, "ask_json", fake)
    return seen


def _with_ocr(assets, lines=OCR_LINES):
    for index in assets.page_indices():
        page = assets.load_page(index)
        page["ocr_lines"] = [dict(l) for l in lines]
        assets.save_page(index, page)


def test_dialogue_is_given_the_box_of_its_bubble(ready, monkeypatch):
    """OCR knows where the words are but mangles them; the vision model reads
    them but cannot measure. Only a text match joins the two."""
    _with_ocr(ready)
    seen = _stub_both(monkeypatch, matches=[{"dialogue_index": 0, "lines": [0, 1, 2]}])

    analyze.run(ready)

    entry = ready.load_page(1)["panels"][0]["dialogue"][0]
    assert entry["region"] == [142, 609, 330, 763]      # union of the three lines
    assert "OH, AFANAF" in seen["match_prompt"]         # OCR text reaches the matcher
    assert "IS STILL THERE" in seen["match_prompt"]


def test_an_unmatched_line_leaves_dialogue_unplaced(ready, monkeypatch):
    """Never force a match: the model may have read a line OCR missed."""
    _with_ocr(ready)
    _stub_both(monkeypatch, matches=[{"dialogue_index": 0, "lines": []}])

    analyze.run(ready)
    assert "region" not in ready.load_page(1)["panels"][0]["dialogue"][0]


def test_out_of_range_line_numbers_are_ignored(ready, monkeypatch):
    _with_ocr(ready)
    _stub_both(monkeypatch, matches=[{"dialogue_index": 0, "lines": [0, 99]}])

    analyze.run(ready)
    assert ready.load_page(1)["panels"][0]["dialogue"][0]["region"] == [146, 609, 326, 636]


def test_dialogue_without_ocr_lines_is_left_alone(ready, monkeypatch):
    """OCR failing costs the link, not the analysis."""
    _stub_both(monkeypatch)
    analyze.run(ready)

    page = ready.load_page(1)
    assert page["status"] == "analyzed"
    assert "region" not in page["panels"][0]["dialogue"][0]


def test_a_failed_match_does_not_fail_the_page(ready, monkeypatch):
    _with_ocr(ready)
    _stub_both(monkeypatch, match_raises=True)

    analyze.run(ready)
    page = ready.load_page(1)
    assert page["status"] == "analyzed"
    assert "region" not in page["panels"][0]["dialogue"][0]
