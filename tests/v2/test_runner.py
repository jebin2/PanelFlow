import pytest

from panelflow.v2.paths import Assets, invalidate_downstream
from panelflow.v2.stage1 import analyze, reconcile, runner, synthesize


@pytest.fixture
def fake_llm_stages(monkeypatch):
    """Stub the three LLM sub-stages, recording calls and writing what each
    real one writes, so the runner's ordering and gating are what's tested."""
    calls = []

    def fake_analyze(assets, model=None):
        calls.append("analyze")
        for index in assets.page_indices():
            page = assets.load_page(index)
            page["status"] = "analyzed"
            page["analysis"] = {"prompt_version": analyze.PROMPT_VERSION, "scene_summary": "s"}
            for panel in page["panels"]:
                panel["characters"] = []
                panel["focal_point"] = [0.5, 0.5]
            assets.save_page(index, page)
        assets.rebuild_index()
        invalidate_downstream(assets, include_roster=True)

    def fake_reconcile(assets, model=None):
        calls.append("reconcile")
        characters = assets.load_characters()
        characters["reconciled"] = True
        for character in characters["characters"]:
            character["reference_images"] = []
        assets.save_characters(characters)

    def fake_synthesize(assets, model=None):
        calls.append("synthesize")
        book = assets.load_book()
        book["story"] = {"synopsis": "x", "main_characters": [], "beats": [], "skip_overrides": []}
        assets.save_book(book)

    monkeypatch.setattr(analyze, "run", fake_analyze)
    monkeypatch.setattr(reconcile, "run", fake_reconcile)
    monkeypatch.setattr(synthesize, "run", fake_synthesize)
    return calls


def test_runner_completes_stage1_in_order(comic_folder, fake_extractor, fake_llm_stages):
    fake_extractor()
    assets = runner.run(comic_folder())

    assert fake_llm_stages == ["analyze", "reconcile", "synthesize"]
    assert assets.load_book()["analysis"]["completed_at"]


def test_second_run_does_no_llm_work(comic_folder, fake_extractor, fake_llm_stages):
    fake_extractor()
    folder = comic_folder()
    runner.run(folder)
    fake_llm_stages.clear()

    runner.run(folder)
    assert fake_llm_stages == []


def test_resetting_one_page_reruns_analysis_and_everything_after(comic_folder, fake_extractor, fake_llm_stages):
    fake_extractor()
    folder = comic_folder()
    runner.run(folder)
    fake_llm_stages.clear()

    assets = Assets(folder)
    page = assets.load_page(1)
    page["status"] = "split"
    assets.save_page(1, page)

    runner.run(folder)
    assert fake_llm_stages == ["analyze", "reconcile", "synthesize"]
    assert assets.load_book()["analysis"]["completed_at"]


def test_bumping_prompt_version_reruns_analysis_and_everything_after(
        comic_folder, fake_extractor, fake_llm_stages, monkeypatch):
    fake_extractor()
    folder = comic_folder()
    runner.run(folder)
    fake_llm_stages.clear()
    panels_before = Assets(folder).load_page(1)["panels"]

    monkeypatch.setattr(analyze, "PROMPT_VERSION", analyze.PROMPT_VERSION + "-bumped")
    runner.run(folder)

    assert fake_llm_stages == ["analyze", "reconcile", "synthesize"]
    # extraction and splitting stay cached — only the geometry's owner may set it
    assert [p["bbox"] for p in Assets(folder).load_page(1)["panels"]] == \
           [p["bbox"] for p in panels_before]


def test_only_flag_runs_a_single_sub_stage(comic_folder, fake_extractor, fake_llm_stages):
    fake_extractor()
    folder = comic_folder()

    runner.run(folder, only="1.1")
    assert fake_llm_stages == []
    assert Assets(folder).page_indices() == [1, 2]


def test_runner_raises_with_the_validation_report(comic_folder, fake_extractor, fake_llm_stages, monkeypatch):
    fake_extractor()
    folder = comic_folder()

    # Synthesis writes a story pointing at a page that does not exist
    def bad_synthesize(assets, model=None):
        book = assets.load_book()
        book["story"] = {"synopsis": "x", "main_characters": [],
                         "beats": [{"beat": "climax", "pages": [99]}], "skip_overrides": []}
        assets.save_book(book)
    monkeypatch.setattr(synthesize, "run", bad_synthesize)

    with pytest.raises(ValueError, match="unknown page 99"):
        runner.run(folder)
    assert not Assets(folder).load_book().get("analysis", {}).get("completed_at")
