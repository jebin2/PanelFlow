"""The shot vocabulary is not ours — it is whatever the renderer can play.

schemas.py transcribes three unions out of TypeScript, and a transcription rots
the moment the renderer gains a move. These tests read the real sources and
fail when they disagree, because the alternative is a direction file that
validates here and then dies at render — or, worse, a director that never
learns about an animation someone added for it.

If one of these fails, the kit changed. Update schemas.py *and* the two director
prompts, which teach when to use each name and cannot be generated.
"""
import os
import re

import pytest

from panelflow.stage2 import schemas

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# The kit is a github dependency of remotion-comic; on a dev box it is cloned
# beside PanelFlow. Nothing else in the suite needs it, so skip when it is absent.
KIT_TYPES = os.path.join(os.path.dirname(_REPO), "remotion-animation-kit", "src", "types.ts")
PANELFLOW_TYPES = os.path.join(_REPO, "remotion-comic", "src", "types.ts")

needs_kit = pytest.mark.skipif(
    not os.path.exists(KIT_TYPES),
    reason="remotion-animation-kit is not checked out beside PanelFlow")


def _union(source, declaration):
    """The string literals of a TypeScript union, up to its terminating ';'."""
    body = source.split(declaration)[1].split(";")[0]
    return set(re.findall(r'"([a-z_]+)"', body))


@needs_kit
def test_our_animations_are_exactly_what_the_renderer_can_play():
    kit = _union(open(KIT_TYPES).read(), "export type AnimationName =")
    ours = set(schemas.ANIMATIONS) - set(schemas.PANELFLOW_OWN)

    assert ours == kit, (
        f"schemas.py and remotion-animation-kit disagree.\n"
        f"  the kit has, we do not: {sorted(kit - ours)}\n"
        f"  we have, the kit does not: {sorted(ours - kit)}"
    )


@needs_kit
def test_our_transitions_are_exactly_the_kit_s():
    kit = _union(open(KIT_TYPES).read(), "export type TransitionName =")

    assert set(schemas.TRANSITIONS) == kit


def test_panelflow_s_own_animations_are_declared_in_its_renderer():
    """`assemble` and `three_part_build_up` are ours, not the kit's."""
    source = open(PANELFLOW_TYPES).read()
    declared = _union(source, "export type PanelAnimation = AnimationName")

    assert set(schemas.PANELFLOW_OWN) == declared


def test_our_events_are_exactly_what_the_renderer_fires():
    """Events are a subset of the animation names and a different thing: an
    animation is the shot's movement, an event fires during it."""
    source = open(PANELFLOW_TYPES).read()
    declared = _union(source, "export interface PanelEvent {\n  type:")

    assert set(schemas.EVENTS) == declared
