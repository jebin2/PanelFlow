import React from "react";
import { TransitionSeries, springTiming } from "@remotion/transitions";
import { PanelData } from "../types";
import { PanelWithEvents } from "./PanelWithEvents";
import { getPresentation, TRANSITION_FRAMES } from "../transitions";

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
        const transition = i > 0 ? (panel.transitionIn ?? "none") : "none";

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
