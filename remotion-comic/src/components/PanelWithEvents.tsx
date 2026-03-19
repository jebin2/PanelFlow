import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame } from "remotion";
import { PanelData } from "../types";
import { PanelBase } from "./PanelBase";
import { getAnimationProps } from "../animations";

interface Props {
  panel: PanelData;
  fps: number;
}

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
      {flashOpacity > 0 && (
        <AbsoluteFill
          style={{ backgroundColor: "#fff", opacity: flashOpacity, pointerEvents: "none" }}
        />
      )}
    </AbsoluteFill>
  );
};
