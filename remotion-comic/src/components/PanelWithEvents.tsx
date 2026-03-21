import React from "react";
import { AbsoluteFill, Audio, Sequence, interpolate, staticFile, useCurrentFrame } from "remotion";
import { PanelData, PanelEvent } from "../types";
import { PanelBase } from "./PanelBase";
import { AssembleIntro } from "./AssembleIntro";
import { ThreePartBuildUp } from "./ThreePartBuildUp";
import { KineticSubtitles } from "./KineticSubtitles";
import { getAnimationProps } from "../animations";

interface Props {
  panel: PanelData;
  fps: number;
}

const EVENT_SFX: Partial<Record<PanelEvent["type"], { file: string; volume: number }>> = {
  tremble:   { file: "sfx_rumble.mp3",    volume: 0.20 },
  flash:     { file: "sfx_flash.mp3",     volume: 0.32 },
  // shockwave is assigned to every mid-panel as a visual pulse — no SFX to avoid repetition
  heartbeat: { file: "sfx_heartbeat.mp3", volume: 0.25 },
  rattle:    { file: "sfx_rumble.mp3",    volume: 0.20 },
};

export const PanelWithEvents: React.FC<Props> = ({ panel, fps }) => {
  const frame = useCurrentFrame();
  const animProps = getAnimationProps(panel.animation ?? "ken_burns");
  const events = panel.events ?? [];

  let eventShakeX = 0;
  let eventShakeY = 0;
  let eventScale = 1;
  let flashOpacity = 0;

  for (const event of events) {
    const eventStartFrame = Math.round(event.startSeconds * fps);
    const eventDurFrames = Math.max(1, Math.round(event.durationSeconds * fps));
    const eventEndFrame = eventStartFrame + eventDurFrames;

    if (frame < eventStartFrame || frame >= eventEndFrame) continue;

    const ef = frame - eventStartFrame;
    const ep = ef / eventDurFrames;

    switch (event.type) {
      case "tremble": {
        const intensity = interpolate(ep, [0, 0.7, 1], [8, 6, 0], { extrapolateRight: "clamp" });
        eventShakeX += Math.sin(ef * 5.1) * intensity;
        eventShakeY += Math.cos(ef * 4.7) * intensity;
        break;
      }
      case "flash": {
        flashOpacity = Math.max(
          flashOpacity,
          interpolate(ep, [0, 0.3, 1], [1, 0.5, 0], { extrapolateRight: "clamp" })
        );
        break;
      }
      case "shockwave": {
        const pulse = interpolate(ep, [0, 0.3, 1], [1.0, 1.06, 1.0], { extrapolateRight: "clamp" });
        eventScale = Math.max(eventScale, pulse);
        break;
      }
      case "heartbeat": {
        const pulse = 1.0 + 0.04 * Math.abs(Math.sin((ef * Math.PI) / 8));
        eventScale = Math.max(eventScale, pulse);
        break;
      }
      case "rattle": {
        eventShakeX += Math.sin(ef * 3.7) * 4;
        eventShakeY += Math.cos(ef * 4.1) * 4;
        break;
      }
    }
  }

  const hasEventTransform = eventShakeX !== 0 || eventShakeY !== 0 || eventScale !== 1;

  if (panel.animation === "assemble") {
    return <AssembleIntro panel={panel} />;
  }

  if (panel.animation === "three_part_build_up") {
    return <ThreePartBuildUp panel={panel} />;
  }

  return (
    <AbsoluteFill
      style={
        hasEventTransform
          ? {
            transform: `scale(${eventScale}) translate(${eventShakeX}px, ${eventShakeY}px)`,
            transformOrigin: "center center",
          }
          : undefined
      }
    >
      <PanelBase panel={panel} {...animProps} />
      {panel.wordTimings && <KineticSubtitles panel={panel} />}
      {flashOpacity > 0 && (
        <AbsoluteFill
          style={{ backgroundColor: "#fff", opacity: flashOpacity, pointerEvents: "none" }}
        />
      )}
      {events.map((event, i) => {
        const sfxInfo = EVENT_SFX[event.type];
        if (!sfxInfo) return null;
        const startFrame = Math.round(event.startSeconds * fps);
        const durFrames = Math.max(1, Math.round(event.durationSeconds * fps));
        return (
          <Sequence key={i} from={startFrame} durationInFrames={durFrames} layout="none">
            <Audio src={staticFile(`sfx/${sfxInfo.file}`)} volume={sfxInfo.volume} />
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};
