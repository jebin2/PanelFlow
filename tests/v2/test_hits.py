"""The hit layer is pure arithmetic over the manifest, so it is pinned hard:
where hits land on the music clock, which vocabulary earns one, and that the
generated layer advances one slot per cycle with every hit fired once.
"""
from panelflow.v2.stage3 import hits

FPS = 24
CPS = 0.5


def _panel(seconds, transition="none", animation="ken_burns", events=()):
    return {"durationInSeconds": seconds, "transitionIn": transition,
            "animation": animation, "events": list(events)}


def _manifest(panels):
    return {"fps": FPS, "panels": panels}


# ---------------------------------------------------------------- the timeline

def test_a_transition_hits_where_the_overlap_starts():
    manifest = _manifest([_panel(6), _panel(6, transition="slide")])
    # The second panel starts 18 overlap frames before the first one ends.
    assert hits.timeline(manifest, 0.0) == [((144 - 18) / FPS, "whoosh")]


def test_the_intro_bookend_shifts_the_clock():
    manifest = _manifest([_panel(6), _panel(6, transition="push")])
    assert hits.timeline(manifest, 4.0) == [(4.0 + (144 - 18) / FPS, "whoosh")]


def test_an_event_hits_at_its_second_inside_the_shot():
    manifest = _manifest([
        _panel(6, events=[{"type": "flash", "startSeconds": 2.5}]),
        _panel(6, events=[{"type": "tremble", "startSeconds": 1.0}]),
    ])
    assert hits.timeline(manifest, 0.0) == [(2.5, "strike"), (144 / FPS + 1.0, "rumble")]


def test_unscored_vocabulary_is_silent():
    """Shockwave had no MP3 either, and a fade never made a sound."""
    manifest = _manifest([
        _panel(6, events=[{"type": "shockwave", "startSeconds": 1.0}]),
        _panel(6, transition="fade"),
    ])
    assert hits.timeline(manifest, 0.0) == []


def test_a_downgraded_transition_makes_no_sound():
    """A directional transition over a self-entrancing animation renders as a
    fade (PanelSequences.tsx), so it must not whoosh in the score either."""
    manifest = _manifest([_panel(6), _panel(6, transition="slide", animation="slam_left")])
    assert hits.timeline(manifest, 0.0) == []


def test_a_too_short_panel_loses_its_transition():
    manifest = _manifest([_panel(6), _panel(0.5, transition="slide")])
    assert hits.timeline(manifest, 0.0) == []


# ------------------------------------------------------------------ the layers

def test_a_layer_has_one_slot_per_cycle_and_fires_once():
    layers = hits.layers([(4.0, "rumble")], total_cycles=4, cps=CPS)
    assert layers == ['note("<~ ~ [c1 ~ ~ ~] ~>").s("gm_timpani").gain(0.5).clip(4)']


def test_a_heartbeat_thumps_twice():
    (layer,) = hits.layers([(2.0, "heartbeat")], total_cycles=2, cps=CPS)
    assert "[c1 c1 ~ ~]" in layer and "gm_taiko_drum" in layer


def test_a_whoosh_rises_ahead_of_its_cut():
    """The reverse cymbal crests at its end, so it starts three quarters early."""
    (layer,) = hits.layers([(4.0, "whoosh")], total_cycles=4, cps=CPS)
    assert layer.startswith('note("<~ [~ c4 ~ ~] ~ ~>")')


def test_a_hit_past_the_track_is_clamped_inside():
    (layer,) = hits.layers([(99.0, "rumble")], total_cycles=2, cps=CPS)
    assert layer.startswith('note("<~ [~ ~ ~ c1]>")')


def test_no_hits_means_no_layers():
    assert hits.layers([], total_cycles=8, cps=CPS) == []
