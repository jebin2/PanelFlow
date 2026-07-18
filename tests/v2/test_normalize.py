"""Mechanical shape-fixing the model drifts on — settled in code, not by the
repair model. These pin the two coercions and that judgment is left alone.
"""
from panelflow.v2.stage2 import normalize


def test_ids_are_assigned_by_position():
    shots = [{"narration": "a"}, {"narration": "b"}, {"narration": "c"}]
    normalize.normalize_shots(shots)
    assert [s["id"] for s in shots] == [1, 2, 3]


def test_a_bare_string_event_becomes_an_object():
    shots = [{"narration": "x", "events": ["flash", "shockwave"]}]
    normalize.normalize_shots(shots)
    assert shots[0]["events"] == [
        {"type": "flash", "at_fraction": normalize.DEFAULT_AT_FRACTION},
        {"type": "shockwave", "at_fraction": normalize.DEFAULT_AT_FRACTION},
    ]


def test_an_event_object_is_left_untouched():
    event = {"type": "flash", "at_fraction": 0.3}
    shots = [{"narration": "x", "events": [event]}]
    normalize.normalize_shots(shots)
    assert shots[0]["events"] == [event]


def test_a_narrated_shot_cannot_keep_silent_seconds():
    shots = [{"narration": "he turns", "silent_seconds": 2}]
    normalize.normalize_shots(shots)
    assert shots[0]["silent_seconds"] is None


def test_a_truly_silent_shot_keeps_its_hold():
    shots = [{"narration": "", "silent_seconds": 2}]
    normalize.normalize_shots(shots)
    assert shots[0]["silent_seconds"] == 2


def test_no_events_key_is_fine():
    shots = [{"narration": "x"}]
    normalize.normalize_shots(shots)
    assert shots[0]["events"] == []
