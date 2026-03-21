import React from "react";
import { AbsoluteFill, interpolate } from "remotion";
import type {
  TransitionPresentation,
  TransitionPresentationComponentProps,
} from "@remotion/transitions";
import { fade } from "@remotion/transitions/fade";
import { slide } from "@remotion/transitions/slide";
import { wipe } from "@remotion/transitions/wipe";
import { flip } from "@remotion/transitions/flip";
import { PanelTransition } from "./types";

export const TRANSITION_FRAMES = 18; // ~0.75s at 24fps

// Custom "toss" — outgoing panel spins/shrinks away, incoming rises up
const TossComponent: React.FC<TransitionPresentationComponentProps<Record<string, never>>> = ({
  children,
  presentationProgress,
  presentationDirection,
}) => {
  const style: React.CSSProperties =
    presentationDirection === "exiting"
      ? {
          transform: `scale(${interpolate(presentationProgress, [0, 1], [1, 0.72])}) rotate(${interpolate(presentationProgress, [0, 1], [0, 18])}deg)`,
          opacity: interpolate(presentationProgress, [0, 1], [1, 0]),
          transformOrigin: "center center",
        }
      : {
          transform: `translateY(${interpolate(presentationProgress, [0, 1], [60, 0])}%) rotate(${interpolate(presentationProgress, [0, 1], [-8, 0])}deg)`,
          opacity: interpolate(presentationProgress, [0, 1], [0, 1]),
          transformOrigin: "center center",
        };

  return React.createElement(AbsoluteFill, { style }, children);
};

const toss = (): TransitionPresentation<Record<string, never>> => ({
  component: TossComponent,
  props: {},
});

export function getPresentation(transition: PanelTransition): TransitionPresentation<Record<string, never>> {
  switch (transition) {
    case "fade":  return fade()  as unknown as TransitionPresentation<Record<string, never>>;
    case "slide": return slide() as unknown as TransitionPresentation<Record<string, never>>;
    case "wipe":  return wipe()  as unknown as TransitionPresentation<Record<string, never>>;
    case "flip":  return flip()  as unknown as TransitionPresentation<Record<string, never>>;
    case "toss":  return toss();
    default:      return fade()  as unknown as TransitionPresentation<Record<string, never>>;
  }
}
