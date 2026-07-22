"""What the renderer actually plays when a transition meets an animation.

`remotion-comic/src/components/PanelSequences.tsx` does not play every
transition it is handed. A directional transition slides the whole outgoing
frame away while the incoming one arrives; an animation like `slam_left` also
enters the panel under its own motion. Both at once is two competing movements
over the same 18 frames, so the renderer resolves the fight by forcing `fade`.

That resolution is silent — the direction on disk still says `whip_pan` — which
is why it lives here rather than being rediscovered by everyone who needs it:
2.3 flags the fight so the director can settle it deliberately, and 3.3 places
the score's whooshes on the transitions that survive. Keep both sets in step
with resolveTransition() in the TSX; they are the same rule, written twice
because the renderer is not Python.
"""

# Transitions that never fight: they do not move the frame, so any animation
# may enter through them.
NEUTRAL = {"none", "fade", "toss", "iris", "clock_wipe", "halftone", "barn_door"}

# Animations that enter under their own motion, from off-frame.
SELF_ENTRANCING = {"slide_left", "slide_right", "slide_bottom", "slide_top",
                   "slam_left", "slam_right", "whip_left", "whip_right",
                   "spin_in", "tilt_in"}


def fights(transition, animation):
    """True when the renderer will quietly replace this pairing with a fade."""
    return transition not in NEUTRAL and animation in SELF_ENTRANCING


def resolve(transition, animation):
    """The transition the renderer will actually play into this shot."""
    return "fade" if fights(transition, animation) else transition
