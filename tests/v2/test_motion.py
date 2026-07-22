"""The renderer's silent transition downgrade, as Python knows it.

The sets here are a copy of a rule that lives in TypeScript, so the last test
reads the TSX and fails if the two ever drift.
"""
import os
import re

from panelflow.v2 import motion

TSX = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                   "remotion-comic", "src", "components", "PanelSequences.tsx")


def test_a_directional_transition_fights_an_animation_that_enters_itself():
    assert motion.fights("whip_pan", "whip_right")
    assert motion.fights("push", "slam_left")
    assert motion.fights("wipe", "tilt_in")
    assert motion.resolve("whip_pan", "whip_right") == "fade"


def test_a_neutral_transition_survives_anything():
    for transition in motion.NEUTRAL:
        assert not motion.fights(transition, "slam_left")
        assert motion.resolve(transition, "slam_left") == transition


def test_a_still_animation_keeps_its_directional_transition():
    assert not motion.fights("whip_pan", "punch_in")
    assert motion.resolve("wipe", "ken_burns") == "wipe"


def test_the_sets_match_the_renderer():
    """The rule is written twice because the renderer is not Python. If the TSX
    moves and this does not, 2.3 blesses a transition that will not play and the
    score puts a whoosh where there is no sound."""
    with open(TSX) as f:
        source = f.read()

    def names(constant):
        block = re.search(rf"const {constant} = new Set(?:<[^>]*>)?\(\[(.*?)\]\)",
                          source, re.S)
        return set(re.findall(r'"([^"]+)"', block.group(1)))

    assert names("SELF_ENTRANCING") == motion.SELF_ENTRANCING
    assert names("NEUTRAL") == motion.NEUTRAL
