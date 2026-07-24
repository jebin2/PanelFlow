"""2.4 expand: keep the words, move the picture. The model decides which panel
depicts which sentence; these tests pin everything code owns around it — the
verbatim guarantee, the floor, the shot rebuild, and the skip rules."""
import json
import os

import pytest

from panelflow.stage2 import expand


# ---- a minimal book: one page of panels, one direction on disk -------------

class _Assets:
    def __init__(self, folder, pages, direction):
        self.folder, self.name = str(folder), "book"
        self._pages = pages
        self._path = os.path.join(str(folder), "longform.json")
        with open(self._path, "w") as f:
            json.dump(direction, f)

    def pages(self):
        return list(self._pages.items())

    def load_direction(self, target):
        with open(self._path) as f:
            return json.load(f)

    def save_direction(self, target, data):
        with open(self._path, "w") as f:
            json.dump(data, f)

    def expand_cache_path(self, target):
        return os.path.join(self.folder, f"{target}.expand.json")


PAGE = {3: {"panels": [
    {"id": 1, "intensity": 1, "description": "a car on a coast road"},
    {"id": 2, "intensity": 1, "description": "the car arrives at the convent"},
    {"id": 3, "intensity": 2, "description": "two women talk by the car"},
    {"id": 4, "intensity": 2, "description": "three women walk to a doorway"},
    {"id": 5, "intensity": 2, "description": "one addresses the others"},
]}}

# Each sentence clears the ~9-word floor on its own, so a clean 3-way split
# survives (real narration runs this long — shot 2 was 12+ words a sentence).
S1 = "Two women stand talking quietly by the car outside the lit convent."
S2 = "Three of them walk together toward the large doorway of the building."
S3 = "One of them addresses the others warmly as they gather by the steps."
NARRATION = f"{S1} {S2} {S3}"


def _shot(**over):
    shot = {"id": 1, "source": {"kind": "panel", "page": 3, "panel": 3},
            "narration": NARRATION, "animation": "ken_burns",
            "animation_target": "whole", "transition_in": "fade",
            "silent_seconds": None, "speaker": None, "events": [], "why": "the arrival"}
    shot.update(over)
    return shot


def _book(tmp_path, shots):
    return _Assets(tmp_path, PAGE,
                   {"target": "longform", "validated": True, "shots": shots})


# ---- the skip rules (no model) ---------------------------------------------

def test_a_pan_or_full_page_is_never_a_candidate():
    assert not expand._is_candidate(_shot(source={"kind": "pan", "page": 3,
                                                  "from_panel": 1, "to_panel": 2}))
    assert not expand._is_candidate(_shot(source={"kind": "full_page", "page": 3}))


def test_a_direct_quote_is_never_a_candidate():
    assert not expand._is_candidate(_shot(speaker="batwoman"))


def test_a_line_too_short_for_two_slices_is_never_a_candidate():
    assert not expand._is_candidate(_shot(narration="She ran."))


def test_a_long_narrator_panel_shot_is_a_candidate():
    assert expand._is_candidate(_shot())


# ---- the verbatim guarantee & floor (no model) -----------------------------

def test_a_paraphrase_is_rejected():
    """If the pieces do not reproduce the line word for word, the split is
    untrustworthy and the shot stays whole."""
    segments = [{"panel": 3, "text": "Two women chat quietly by the car outside the lit convent."},
                {"panel": 4, "text": f"{S2} {S3}"}]      # 'chat' != 'stand talking'
    assert expand._settle(segments, NARRATION, {1, 2, 3, 4, 5}) == []


def test_a_made_up_panel_is_rejected():
    segments = [{"panel": 3, "text": S1},
                {"panel": 9, "text": f"{S2} {S3}"}]
    assert expand._settle(segments, NARRATION, {1, 2, 3, 4, 5}) == []


def test_a_repeated_panel_is_collapsed():
    segments = [{"panel": 3, "text": S1},
                {"panel": 3, "text": S2},
                {"panel": 5, "text": S3}]
    settled = expand._settle(segments, NARRATION, {1, 2, 3, 4, 5})
    assert [s["panel"] for s in settled] == [3, 5]
    assert settled[0]["text"] == f"{S1} {S2}"


def test_a_below_floor_slice_merges_into_its_larger_neighbour():
    segments = [{"panel": 3, "text": S1},
                {"panel": 4, "text": "Three walk."},                       # 2 words, below floor
                {"panel": 5, "text": S3}]
    settled = expand._merge_short([dict(s) for s in segments])
    # the sliver is gone; every survivor clears the floor
    assert all(expand._count(s["text"]) >= expand.FLOOR_WORDS for s in settled)
    assert "Three walk." in " ".join(s["text"] for s in settled)


# ---- the shot rebuild (no model) -------------------------------------------

def test_the_first_shot_keeps_the_opening_the_rest_hard_cut():
    segments = [{"panel": 3, "text": S1}, {"panel": 4, "text": S2},
                {"panel": 5, "text": S3}]
    shots = expand._to_shots(_shot(), segments)

    assert [s["transition_in"] for s in shots] == ["fade", "none", "none"]
    assert all(s["animation"] == "ken_burns" for s in shots)          # parent reused
    assert all(s["source"]["panel"] == seg["panel"]
               for s, seg in zip(shots, segments))
    assert " ".join(s["narration"] for s in shots) == NARRATION       # verbatim, in order


def test_an_event_lands_on_the_slice_that_holds_its_moment():
    """A parent event at 0.9 belongs to the last slice, rescaled to it."""
    segments = [{"panel": 3, "text": S1}, {"panel": 5, "text": S3}]
    shot = _shot(narration=f"{S1} {S3}",
                 events=[{"type": "flash", "at_fraction": 0.9}])
    shots = expand._to_shots(shot, segments)

    assert shots[0]["events"] == []
    assert shots[1]["events"][0]["type"] == "flash"
    assert shots[1]["events"][0]["at_fraction"] > 0.5      # late within its own slice


# ---- run() end to end, model stubbed ---------------------------------------

@pytest.fixture
def split_into_three(monkeypatch):
    monkeypatch.setattr(expand.llm, "ask_json", lambda **kw: {"segments": [
        {"panel": 3, "text": S1}, {"panel": 4, "text": S2}, {"panel": 5, "text": S3}]})


def test_run_expands_and_keeps_the_words(tmp_path, split_into_three):
    assets = _book(tmp_path, [_shot()])

    expand.run(assets, "longform")
    direction = assets.load_direction("longform")

    assert len(direction["shots"]) == 3
    assert [s["id"] for s in direction["shots"]] == [1, 2, 3]      # renumbered
    assert " ".join(s["narration"] for s in direction["shots"]) == NARRATION
    assert direction["expanded"] is True


def test_run_is_idempotent_via_the_flag(tmp_path, split_into_three):
    assets = _book(tmp_path, [_shot()])
    expand.run(assets, "longform")
    assert expand.is_done(assets, "longform")

    # a second run must not re-split the now single-sentence children
    calls = {"n": 0}
    import panelflow.stage2.expand as mod
    orig = mod.llm.ask_json
    mod.llm.ask_json = lambda **kw: calls.__setitem__("n", calls["n"] + 1) or orig(**kw)
    try:
        if not expand.is_done(assets, "longform"):
            expand.run(assets, "longform")
    finally:
        mod.llm.ask_json = orig
    assert calls["n"] == 0


def test_a_split_shot_logs_a_permanent_outcome_line(tmp_path, split_into_three, monkeypatch):
    """A clean split otherwise leaves only the overwriting heartbeat; a split
    prints a line that sticks, a no-op stays quiet."""
    seen = []
    monkeypatch.setattr(expand.logger_config, "info", lambda m, **kw: seen.append(m))
    expand.run(_book(tmp_path, [_shot()]), "longform")

    outcome = [m for m in seen if "→ 3 panels" in m]
    assert outcome and "3, 4, 5" in outcome[0]


def test_a_no_op_shot_logs_no_outcome_line(tmp_path, monkeypatch):
    monkeypatch.setattr(expand.llm, "ask_json", lambda **kw: {"segments": [
        {"panel": 3, "text": NARRATION}]})           # one segment == no split
    seen = []
    monkeypatch.setattr(expand.logger_config, "info", lambda m, **kw: seen.append(m))
    expand.run(_book(tmp_path, [_shot()]), "longform")

    assert not any("panels (" in m for m in seen)     # no per-shot line, only the summary


def test_a_shot_the_model_leaves_whole_is_unchanged(tmp_path, monkeypatch):
    monkeypatch.setattr(expand.llm, "ask_json", lambda **kw: {"segments": [
        {"panel": 3, "text": NARRATION}]})           # one segment == no split
    assets = _book(tmp_path, [_shot()])

    expand.run(assets, "longform")

    assert len(assets.load_direction("longform")["shots"]) == 1


def test_a_completed_shot_is_reused_from_cache_not_re_asked(tmp_path):
    """A run killed after some shots keeps their answers; a retry only pays for
    what is missing. Here the one shot is pre-cached, so the model is never
    called — a call would blow up the stub."""
    assets = _book(tmp_path, [_shot()])
    with open(assets.expand_cache_path("longform"), "w") as f:
        json.dump({expand._key(NARRATION): [
            {"panel": 3, "text": S1}, {"panel": 4, "text": S2},
            {"panel": 5, "text": S3}]}, f)

    def boom(**kw):
        raise AssertionError("a cached shot must not reach the model")
    import panelflow.stage2.expand as mod
    mod.llm.ask_json, orig = boom, mod.llm.ask_json
    try:
        expand.run(assets, "longform")
    finally:
        mod.llm.ask_json = orig

    assert len(assets.load_direction("longform")["shots"]) == 3


def test_a_fresh_answer_is_written_to_the_cache(tmp_path, split_into_three):
    assets = _book(tmp_path, [_shot()])
    expand.run(assets, "longform")

    with open(assets.expand_cache_path("longform")) as f:
        cache = json.load(f)
    assert expand._key(NARRATION) in cache


def test_a_failed_shot_is_not_cached(tmp_path, monkeypatch):
    """Opencode returns empty under load; caching that would poison the retry."""
    def fail(**kw):
        raise RuntimeError("TTT result had no text")
    monkeypatch.setattr(expand.llm, "ask_json", fail)
    assets = _book(tmp_path, [_shot()])

    expand.run(assets, "longform")

    assert not os.path.exists(assets.expand_cache_path("longform"))   # nothing remembered
    assert len(assets.load_direction("longform")["shots"]) == 1       # left whole


def test_an_unvalidated_direction_refuses(tmp_path):
    assets = _Assets(tmp_path, PAGE,
                     {"target": "longform", "validated": False, "shots": [_shot()]})
    with pytest.raises(ValueError, match="not validated"):
        expand.run(assets, "longform")


def test_shorts_never_expand():
    assert expand.is_done(object(), "shorts")
