import React from "react";
import { AbsoluteFill, Audio, Sequence, interpolate, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { PanelData, PanelEvent } from "../types";
import { PanelBase } from "./PanelBase";
import { AssembleIntro } from "./AssembleIntro";
import { NameTag } from "./NameTag";
import { ThreePartBuildUp } from "remotion-animation-kit";
import { KineticSubtitles } from "remotion-animation-kit";
import { getAnimationProps } from "remotion-animation-kit";

interface Props {
  panel: PanelData;
  fps: number;
  /** True when a music track plays: its baked-in hits replace the static SFX. */
  muteSfx?: boolean;
}

const EVENT_SFX: Partial<Record<PanelEvent["type"], { file: string; volume: number }>> = {
  tremble:   { file: "sfx_rumble.mp3",    volume: 0.20 },
  flash:     { file: "sfx_flash.mp3",     volume: 0.32 },
  // shockwave is assigned to every mid-panel as a visual pulse — no SFX to avoid repetition
  heartbeat: { file: "sfx_heartbeat.mp3", volume: 0.25 },
  rattle:    { file: "sfx_rumble.mp3",    volume: 0.20 },
};

/** Comic action lines radiating from the focal point, held clear of it so the
 * subject stays readable. Geometry is fixed per line index — the burst holds
 * still while its opacity plays the envelope. */
const SpeedLines: React.FC<{ opacity: number; origin: [number, number] }> = ({ opacity, origin }) => {
  const [cx, cy] = [origin[0] * 100, origin[1] * 100];
  const lines = Array.from({ length: 28 }, (_, i) => {
    const angle = (i / 28) * Math.PI * 2 + (i % 3) * 0.07;
    const inner = 24 + (i % 5) * 4;   // % distance where the line starts
    const outer = 160;                 // safely past every frame corner
    return {
      x1: cx + Math.cos(angle) * inner,
      y1: cy + Math.sin(angle) * inner,
      x2: cx + Math.cos(angle) * outer,
      y2: cy + Math.sin(angle) * outer,
      width: 0.4 + (i % 4) * 0.25,
    };
  });
  return (
    <AbsoluteFill style={{ opacity, pointerEvents: "none" }}>
      <svg width="100%" height="100%" viewBox="0 0 100 100" preserveAspectRatio="none">
        {lines.map((l, i) => (
          <line
            key={i}
            x1={l.x1} y1={l.y1} x2={l.x2} y2={l.y2}
            stroke="#fff"
            strokeWidth={l.width}
            strokeLinecap="round"
            opacity={0.9}
          />
        ))}
      </svg>
    </AbsoluteFill>
  );
};

export const PanelWithEvents: React.FC<Props> = ({ panel, fps, muteSfx }) => {
  const frame = useCurrentFrame();
  // Same kinetic word everywhere; landscape sits it at the bottom edge so it
  // stays off the artwork, portrait keeps the kit's default height.
  const { width, height } = useVideoConfig();
  const isPortrait = height > width;

  // PanelFlow's own two animations are whole components rather than a set of
  // transforms, so they leave before any of the below applies — and leaving
  // here rather than further down is what narrows `panel.animation` to the
  // names the kit actually knows.
  if (panel.animation === "assemble") {
    return <AssembleIntro panel={panel} />;
  }
  if (panel.animation === "three_part_build_up") {
    return <ThreePartBuildUp data={panel} />;
  }

  // The animation says how to move; the panel says where to aim and how far it
  // may go. The panel wins, because only it knows where the subject and the
  // lettering are.
  const animProps = {
    ...getAnimationProps(panel.animation ?? "ken_burns"),
    ...(panel.focalOrigin && { originX: panel.focalOrigin[0], originY: panel.focalOrigin[1] }),
    ...(panel.zoomLimit != null && { zoomLimit: panel.zoomLimit }),
    ...(panel.camera && {
      zoomStart: panel.camera.zoom,
      zoomEnd: panel.camera.zoom,
      zoomSettleFraction: 1,
      panXStart: panel.camera.panStart[0],
      panYStart: panel.camera.panStart[1],
      panXEnd: panel.camera.panEnd[0],
      panYEnd: panel.camera.panEnd[1],
    }),
  };
  const events = panel.events ?? [];

  let eventShakeX = 0;
  let eventShakeY = 0;
  let eventScale = 1;
  let flashOpacity = 0;
  let speedLinesOpacity = 0;
  let vignetteOpacity = 0;
  let drainAmount = 0;
  let invertOn = false;
  let blackOpacity = 0;
  let blurPx = 0;
  let pullScale = 1;

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
      case "zoom_punch": {
        // Harder than shockwave: a sharp jab in, then a settling decay.
        const punch = interpolate(ep, [0, 0.12, 1], [1.0, 1.12, 1.0], { extrapolateRight: "clamp" });
        eventScale = Math.max(eventScale, punch);
        break;
      }
      case "speed_lines": {
        speedLinesOpacity = Math.max(
          speedLinesOpacity,
          interpolate(ep, [0, 0.15, 0.7, 1], [0, 0.85, 0.6, 0], { extrapolateRight: "clamp" })
        );
        break;
      }
      case "vignette_pulse": {
        vignetteOpacity = Math.max(
          vignetteOpacity,
          interpolate(ep, [0, 0.4, 1], [0, 0.65, 0], { extrapolateRight: "clamp" })
        );
        break;
      }
      case "color_drain": {
        drainAmount = Math.max(
          drainAmount,
          interpolate(ep, [0, 0.25, 0.75, 1], [0, 1, 1, 0], { extrapolateRight: "clamp" })
        );
        break;
      }
      case "invert_flash": {
        // Binary, not faded: a half-inverted image reads as muddy, a fully
        // inverted couple of frames reads as an impact frame.
        invertOn = invertOn || ep < 0.5;
        break;
      }
      case "black_flash": {
        blackOpacity = Math.max(
          blackOpacity,
          interpolate(ep, [0, 0.3, 1], [1, 0.5, 0], { extrapolateRight: "clamp" })
        );
        break;
      }
      case "blur_pulse": {
        blurPx = Math.max(
          blurPx,
          interpolate(ep, [0, 0.4, 1], [0, 7, 0], { extrapolateRight: "clamp" })
        );
        break;
      }
      case "zoom_pull": {
        pullScale = Math.min(
          pullScale,
          interpolate(ep, [0, 0.12, 1], [1.0, 0.92, 1.0], { extrapolateRight: "clamp" })
        );
        break;
      }
    }
  }

  const scale = eventScale * pullScale;
  const hasEventTransform = eventShakeX !== 0 || eventShakeY !== 0 || scale !== 1;
  const filters = [
    drainAmount > 0 && `grayscale(${drainAmount}) brightness(${1 - 0.15 * drainAmount})`,
    invertOn && "invert(1)",
    blurPx > 0.2 && `blur(${blurPx.toFixed(1)}px)`,
  ].filter(Boolean);

  return (
    <AbsoluteFill
      style={
        hasEventTransform || filters.length > 0
          ? {
            ...(hasEventTransform && {
              transform: `scale(${scale}) translate(${eventShakeX}px, ${eventShakeY}px)`,
              transformOrigin: "center center",
            }),
            ...(filters.length > 0 && { filter: filters.join(" ") }),
          }
          : undefined
      }
    >
      <PanelBase panel={panel} {...animProps} />
      {panel.wordTimings && (
        <KineticSubtitles
          wordTimings={panel.wordTimings}
          bottomPadding={isPortrait ? undefined : "4%"}
        />
      )}
      {panel.nameTag && <NameTag name={panel.nameTag.name} imageSrc={panel.nameTag.imageSrc} />}
      {flashOpacity > 0 && (
        <AbsoluteFill
          style={{ backgroundColor: "#fff", opacity: flashOpacity, pointerEvents: "none" }}
        />
      )}
      {blackOpacity > 0 && (
        <AbsoluteFill
          style={{ backgroundColor: "#000", opacity: blackOpacity, pointerEvents: "none" }}
        />
      )}
      {speedLinesOpacity > 0 && (
        <SpeedLines opacity={speedLinesOpacity} origin={panel.focalOrigin ?? [0.5, 0.5]} />
      )}
      {vignetteOpacity > 0 && (
        <AbsoluteFill
          style={{
            background: `radial-gradient(ellipse at center, transparent 40%, rgba(0,0,0,${vignetteOpacity}) 100%)`,
            pointerEvents: "none",
          }}
        />
      )}
      {events.map((event, i) => {
        const sfxInfo = muteSfx ? undefined : EVENT_SFX[event.type];
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
