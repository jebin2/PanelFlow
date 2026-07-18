"""3.3 music: the shape is measured here, the score is asked of a model, the
render is a tool. These tests pin the shape (sections, intensity, density) and
the contract around the model and the tool — that a failed score costs no video,
and an unchanged one costs no re-render.
"""
import json
import os
import types

import pytest

from panelflow.v2.stage3 import music


class _Assets:
    def __init__(self, folder, pages):
        self.folder = str(folder)
        self._pages = pages

    def load_page(self, index):
        return self._pages[index]

    def target_dir(self, target):
        path = os.path.join(self.folder, "render", target)
        os.makedirs(path, exist_ok=True)
        return path

    def music_path(self, target):
        return os.path.join(self.target_dir(target), "music.mp3")

    def rel_to_book(self, path):
        return "render_assets/" + os.path.relpath(path, self.folder)


PAGES = {1: {"panels": [{"id": 1, "intensity": 2}, {"id": 2, "intensity": 5}]}}


def _panel_shot(panel, transition="none"):
    return {"source": {"kind": "panel", "page": 1, "panel": panel}, "transition_in": transition}


# ------------------------------------------------------------------- the shape

def test_intensity_reads_the_source_panels():
    assets = _Assets("/tmp", PAGES)
    assert music._intensity(assets, _panel_shot(1)) == 2
    assert music._intensity(assets, {"source": {"kind": "pan", "page": 1,
                                                 "from_panel": 1, "to_panel": 2}}) == 5
    assert music._intensity(assets, {"source": {"kind": "full_page", "page": 1}}) == 5


def test_bands():
    assert [music._band(i) for i in (0, 2, 3, 4, 5)] == \
        ["calm", "calm", "rising", "intense", "intense"]


def test_sections_are_phrases_not_shots(tmp_path):
    """The stutter bug: alternating intensity must NOT give one section per
    shot. Shots fold into the running section until it is a phrase long; only
    then may a band change open a new one."""
    assets = _Assets(tmp_path, PAGES)
    direction = {"shots": [                      # calm/intense alternating x6
        _panel_shot(1 if i % 2 == 0 else 2) for i in range(6)]}
    manifest = {"panels": [
        {"narrationText": "x", "durationInSeconds": 5} for _ in range(6)]}

    sections = music._sections(assets, direction, manifest)

    # Uniform alternation is one musical stretch, not six two-and-a-half-cycle
    # bits: no dominant band ever emerges to justify a cut.
    assert len(sections) == 1
    assert sum(s["seconds"] for s in sections) == 30


def test_a_sections_band_is_where_it_spends_its_time(tmp_path):
    """One intense flash inside a calm stretch scores calm; a mostly-intense
    finale scores intense."""
    assets = _Assets(tmp_path, PAGES)
    direction = {"shots": [_panel_shot(1), _panel_shot(2), _panel_shot(1),  # 12s calm, 5s intense
                           _panel_shot(2), _panel_shot(2), _panel_shot(1)]} # 12s intense, 4s calm
    manifest = {"panels": [
        {"narrationText": "x", "durationInSeconds": d}
        for d in (6, 5, 6, 6, 6, 4)]}

    sections = music._sections(assets, direction, manifest)

    assert [s["band"] for s in sections] == ["calm", "intense"]


def test_a_trailing_sliver_folds_into_the_last_phrase(tmp_path):
    assets = _Assets(tmp_path, PAGES)
    direction = {"shots": [_panel_shot(1)] * 4 + [_panel_shot(2)]}
    manifest = {"panels": [
        {"narrationText": "", "durationInSeconds": 5} for _ in range(4)
    ] + [{"narrationText": "", "durationInSeconds": 2}]}       # 2s intense tail

    sections = music._sections(assets, direction, manifest)

    assert len(sections) == 1                    # the coda joined the phrase
    assert sections[0]["seconds"] == 22
    assert sections[0]["narration"] == "sparse"


def test_bookends_extend_the_edge_sections(tmp_path):
    """The score plays from frame 0 and under the end card, so the intro and
    outro seconds stretch the opening and closing sections."""
    assets = _Assets(tmp_path, PAGES)
    direction = {"shots": [_panel_shot(1)] * 4}
    manifest = {"panels": [
        {"narrationText": "x", "durationInSeconds": 5} for _ in range(4)]}

    plain = music._sections(assets, direction, manifest)
    booked = music._sections(assets, direction, manifest, bookends=(4.0, 5.0))

    assert sum(s["seconds"] for s in booked) == sum(s["seconds"] for s in plain) + 9


def test_the_prompt_carries_each_section_length(tmp_path):
    prompt = music._prompt("tense", [{"cycles": 12, "band": "calm", "narration": "heavy"},
                                     {"cycles": 6, "band": "intense", "narration": "sparse"}], 18)
    assert "12 cycles" in prompt and "6 cycles" in prompt
    assert "18 cycles" in prompt and "tense" in prompt


# ------------------------------------------------------- the model + the tool

@pytest.fixture
def scored(monkeypatch):
    """Stub the composer and the renderer: the model returns a pattern, the tool
    'renders' by touching the output, and the track reads as non-silent."""
    calls = {"compose": 0, "render": 0}

    def fake_ask_json(**kw):
        calls["compose"] += 1
        return {"pattern": "arrange([2, note(\"c2\").s(\"sawtooth\")])"}

    def fake_run(cmd, input=None, **kw):
        calls["render"] += 1
        open(json.loads(input)["out"], "w").close()
        return types.SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setattr(music.llm, "ask_json", fake_ask_json)
    monkeypatch.setattr(music.subprocess, "run", fake_run)
    monkeypatch.setattr(music, "_mean_volume", lambda path: -20.0)
    return calls


def _book(tmp_path):
    assets = _Assets(tmp_path, PAGES)
    direction = {"music": {"mood": "tense"}, "shots": [_panel_shot(2)]}
    manifest = {"fps": 24, "panels": [{"narrationText": "hi", "durationInSeconds": 6}]}
    return assets, direction, manifest


def test_no_mood_means_no_music(tmp_path):
    assets, direction, manifest = _book(tmp_path)
    direction["music"] = {"mood": ""}
    assert music.run(assets, "shorts", direction, manifest) == {}


def test_a_scored_video_gets_a_music_ref_and_is_cached(tmp_path, scored):
    assets, direction, manifest = _book(tmp_path)

    ref = music.run(assets, "shorts", direction, manifest)
    assert ref["src"].endswith("render/shorts/music.mp3")
    assert ref["volume"] == music.BED_VOLUME
    assert os.path.exists(assets.music_path("shorts"))

    again = music.run(assets, "shorts", direction, manifest)   # unchanged
    assert again == ref
    assert scored["compose"] == 1 and scored["render"] == 1     # not recomposed


def test_hits_are_stacked_over_the_bed(tmp_path, scored):
    """A manifest with an event renders as stack(bed, hit layer), and the
    rendered pattern is what the meta records."""
    assets, direction, manifest = _book(tmp_path)
    manifest["panels"][0]["events"] = [{"type": "tremble", "startSeconds": 1.0}]

    music.run(assets, "shorts", direction, manifest)

    with open(os.path.join(assets.target_dir("shorts"), "music.json")) as f:
        pattern = json.load(f)["pattern"]
    assert pattern.startswith("stack(arrange(")
    assert "gm_timpani" in pattern


def test_a_failed_render_costs_no_video(tmp_path, monkeypatch):
    assets, direction, manifest = _book(tmp_path)
    monkeypatch.setattr(music.llm, "ask_json",
                        lambda **kw: {"pattern": "note(\"c2\").s(\"sawtooth\")"})
    monkeypatch.setattr(music.subprocess, "run",
                        lambda *a, **k: types.SimpleNamespace(returncode=1, stderr="boom", stdout=""))

    assert music.run(assets, "shorts", direction, manifest) == {}   # skipped, not raised
    # ...but the pattern that failed is kept for the postmortem.
    assert os.path.exists(assets.music_path("shorts") + ".failed.js")


def test_a_silent_render_is_rejected(tmp_path, monkeypatch):
    assets, direction, manifest = _book(tmp_path)
    monkeypatch.setattr(music.llm, "ask_json", lambda **kw: {"pattern": "silence"})
    monkeypatch.setattr(music.subprocess, "run",
                        lambda cmd, input=None, **k: (open(json.loads(input)["out"], "w").close(),
                                                      types.SimpleNamespace(returncode=0, stderr="", stdout=""))[1])
    monkeypatch.setattr(music, "_mean_volume", lambda path: -90.0)

    assert music.run(assets, "shorts", direction, manifest) == {}
