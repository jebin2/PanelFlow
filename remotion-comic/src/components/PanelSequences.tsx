import React from "react";
import { AbsoluteFill, Audio, Sequence, staticFile } from "remotion";
import { TransitionSeries, springTiming } from "@remotion/transitions";
import { PanelData, PanelTransition } from "../types";
import { PanelWithEvents } from "./PanelWithEvents";
import { getPresentation, TRANSITION_FRAMES } from "remotion-animation-kit";

const TRANSITION_SFX: Partial<Record<PanelTransition, { file: string; volume: number }>> = {
  slide:    { file: "sfx_whoosh.mp3", volume: 0.22 },
  wipe:     { file: "sfx_whoosh.mp3", volume: 0.18 },
  whip_pan: { file: "sfx_whoosh.mp3", volume: 0.28 },
  push:     { file: "sfx_whoosh.mp3", volume: 0.22 },
};

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

// Transitions with no direction of their own: safe over any animation.
// Everything else (slide/wipe/flip/zoom_through/whip_pan) moves the container,
// and doubles up with an animation that enters under its own motion.
const NEUTRAL = new Set<PanelTransition>([
  "none", "fade", "toss", "iris", "clock_wipe", "halftone", "barn_door",
]);

function resolveTransition(panel: PanelData, isFirst: boolean): PanelTransition {
  if (isFirst) return "none";
  const t = panel.transitionIn ?? "none";
  if (NEUTRAL.has(t)) return t;
  if (SELF_ENTRANCING.has(panel.animation)) return "fade";
  return t;
}

/** Returns the effective transition for panel[i], accounting for duration constraints. */
function effectiveTransition(panels: PanelData[], i: number, fps: number): PanelTransition {
  const raw = resolveTransition(panels[i], i === 0);
  if (raw === "none") return "none";
  const frames = Math.ceil(panels[i].durationInSeconds * fps);
  const prevFrames = Math.ceil(panels[i - 1].durationInSeconds * fps);
  if (frames < TRANSITION_FRAMES || prevFrames < TRANSITION_FRAMES) return "none";
  return raw;
}

export function getTotalFrames(panels: PanelData[], fps: number): number {
  return panels.reduce((sum, p, i) => {
    const frames = Math.ceil(p.durationInSeconds * fps);
    const hasTransition = effectiveTransition(panels, i, fps) !== "none";
    return sum + frames - (hasTransition ? TRANSITION_FRAMES : 0);
  }, 0);
}

/** The frame ranges (relative to the first panel) where narration speaks —
 * the same cursor arithmetic the TransitionSeries lays panels out with. The
 * music ducks inside these windows and swells outside them. */
export function narratedWindows(panels: PanelData[], fps: number): { start: number; end: number }[] {
  const windows: { start: number; end: number }[] = [];
  let cursor = 0;
  panels.forEach((p, i) => {
    const frames = Math.ceil(p.durationInSeconds * fps);
    if (effectiveTransition(panels, i, fps) !== "none") cursor -= TRANSITION_FRAMES;
    if ((p.narrationText ?? "").trim()) windows.push({ start: cursor, end: cursor + frames });
    cursor += frames;
  });
  return windows;
}

interface Props {
  panels: PanelData[];
  fps: number;
  /** True when a music track plays: its baked-in hits replace the static SFX. */
  muteSfx?: boolean;
}

export const PanelSequences: React.FC<Props> = ({ panels, fps, muteSfx }) => {
  // Calculate the absolute start frame of each panel in the composition.
  // Each panel contributes (durationInFrames - TRANSITION_FRAMES) to the
  // cursor, except the first which contributes its full duration.
  const panelStartFrames: number[] = [];
  let cursor = 0;
  panels.forEach((panel, i) => {
    panelStartFrames.push(cursor);
    const frames = Math.ceil(panel.durationInSeconds * fps);
    const hasTransition = effectiveTransition(panels, i, fps) !== "none";
    cursor += frames - (hasTransition ? TRANSITION_FRAMES : 0);
  });

  return (
    <AbsoluteFill>
      <TransitionSeries>
        {panels.map((panel, i) => {
          const durationInFrames = Math.ceil(panel.durationInSeconds * fps);
          const transition = effectiveTransition(panels, i, fps);

          return (
            <React.Fragment key={i}>
              {transition !== "none" && (
                <TransitionSeries.Transition
                  presentation={getPresentation(transition)}
                  timing={springTiming({ durationInFrames: TRANSITION_FRAMES })}
                />
              )}
              <TransitionSeries.Sequence durationInFrames={durationInFrames}>
                <PanelWithEvents panel={panel} fps={fps} muteSfx={muteSfx} />
              </TransitionSeries.Sequence>
            </React.Fragment>
          );
        })}
      </TransitionSeries>

      {/* Transition SFX — placed outside TransitionSeries at absolute frame positions
          to avoid audio quirks inside TransitionSeries.Sequence */}
      {panels.map((panel, i) => {
        if (muteSfx || i === 0) return null;
        const transition = effectiveTransition(panels, i, fps);
        const sfxInfo = TRANSITION_SFX[transition];
        if (!sfxInfo) return null;
        const startFrame = panelStartFrames[i];
        return (
          <Sequence key={`tsf-${i}`} from={startFrame} durationInFrames={TRANSITION_FRAMES} layout="none">
            <Audio src={staticFile(`sfx/${sfxInfo.file}`)} volume={sfxInfo.volume} />
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};
