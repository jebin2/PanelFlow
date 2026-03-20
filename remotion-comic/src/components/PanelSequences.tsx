import React from "react";
import { TransitionSeries, springTiming } from "@remotion/transitions";
import { PanelData, PanelTransition } from "../types";
import { PanelWithEvents } from "./PanelWithEvents";
import { getPresentation, TRANSITION_FRAMES } from "../transitions";

// Animations that provide their own directional entrance.
// Combining them with a directional transition (slide/wipe/flip) causes a
// double-motion: the container slides in AND the image slides inside it.
// For these, downgrade any non-neutral transition to "fade" so the animation
// owns the direction and the transition just handles the blend.
const SELF_ENTRANCING = new Set([
  "slide_left", "slide_right", "slide_bottom", "slide_top",
  "slam_left",  "slam_right",
  "whip_left",  "whip_right",
  "spin_in",    "tilt_in",
]);

function resolveTransition(panel: PanelData, isFirst: boolean): PanelTransition {
  if (isFirst) return "none";
  const t = panel.transitionIn ?? "none";
  if (t === "none" || t === "fade" || t === "toss") return t;
  // slide / wipe / flip would conflict with self-entrancing animations
  if (SELF_ENTRANCING.has(panel.animation)) return "fade";
  return t;
}

export function getTotalFrames(panels: PanelData[], fps: number): number {
  return panels.reduce((sum, p, i) => {
    const frames = Math.ceil(p.durationInSeconds * fps);
    const hasTransition = i > 0 && p.transitionIn && p.transitionIn !== "none";
    return sum + frames - (hasTransition ? TRANSITION_FRAMES : 0);
  }, 0);
}

interface Props {
  panels: PanelData[];
  fps: number;
}

export const PanelSequences: React.FC<Props> = ({ panels, fps }) => {
  return (
    <TransitionSeries>
      {panels.map((panel, i) => {
        const durationInFrames = Math.ceil(panel.durationInSeconds * fps);
        const transition = resolveTransition(panel, i === 0);

        return (
          <React.Fragment key={i}>
            {transition !== "none" && (
              <TransitionSeries.Transition
                presentation={getPresentation(transition)}
                timing={springTiming({ durationInFrames: TRANSITION_FRAMES, bounce: 0 })}
              />
            )}
            <TransitionSeries.Sequence durationInFrames={durationInFrames}>
              <PanelWithEvents panel={panel} fps={fps} />
            </TransitionSeries.Sequence>
          </React.Fragment>
        );
      })}
    </TransitionSeries>
  );
};
