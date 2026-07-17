import type { AnimationName, TransitionName, WordTiming } from "remotion-animation-kit";

export type { WordTiming };
export type { TransitionName as PanelTransition };

// PanelFlow uses all shared animations plus its own custom ones
export type PanelAnimation = AnimationName | "assemble" | "three_part_build_up";

export interface PanelEvent {
  type:
    | "tremble"
    | "flash"
    | "shockwave"
    | "heartbeat"
    | "rattle"
    | "zoom_punch"
    | "speed_lines"
    | "vignette_pulse"
    | "color_drain";
  startSeconds: number;
  durationSeconds: number;
}

export interface PanelData {
  imageSrc: string;
  audioSrc: string;
  durationInSeconds: number;
  /** Where AssembleIntro assembles its pieces; whole frame when omitted. */
  bubbleBbox?: [number, number, number, number];
  narrationText: string;
  sceneCaption: string;
  animation: PanelAnimation;
  /**
   * The point the animation should pull toward, as a fraction of the *frame*
   * (not of the panel — the panel is letterboxed into the frame, so the
   * compiler resolves that). Omitted means the centre.
   */
  focalOrigin?: [number, number];
  /** Ceiling on the animation's zoom, so it cannot crop this panel's lettering. */
  zoomLimit?: number;
  /**
   * A camera that travels: the shot opens framed on one part of the image and
   * closes on another (a `pan` shot, whose image spans two panels). Overrides
   * the animation's own zoom and pan, since the geometry of the two panels —
   * not the animation's taste — decides where the camera must be. Implies a
   * centred origin, so it is never combined with `focalOrigin`.
   */
  camera?: {
    zoom: number;
    panStart: [number, number];
    panEnd: [number, number];
  };
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
  panels: PanelData[];
  /** A single music bed for the whole video, played low under the narration. */
  music?: { src: string; volume: number };
}
