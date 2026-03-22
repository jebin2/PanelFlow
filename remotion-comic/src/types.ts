import type { AnimationName, TransitionName, WordTiming } from "remotion-animation-kit";

export type { WordTiming };
export type { TransitionName as PanelTransition };

// PanelFlow uses all shared animations plus its own custom ones
export type PanelAnimation = AnimationName | "assemble" | "three_part_build_up";

export interface PanelEvent {
  type: "tremble" | "flash" | "shockwave" | "heartbeat" | "rattle";
  startSeconds: number;
  durationSeconds: number;
}

export interface PanelData {
  imageSrc: string;
  audioSrc: string;
  durationInSeconds: number;
  bubbleBbox: [number, number, number, number];
  narrationText: string;
  sceneCaption: string;
  animation: PanelAnimation;
  transitionIn?: TransitionName;
  events?: PanelEvent[];
  wordTimings?: WordTiming[];
  originalWidth?: number;
  originalHeight?: number;
  buildUpParts?: number;
  secondaryImageSrc?: string;
  secondaryOriginalWidth?: number;
  secondaryOriginalHeight?: number;
}

export interface ComicManifest {
  fps: number;
  width: number;
  height: number;
  comicTitle: string;
  pageNumber: number;
  panels: PanelData[];
}
