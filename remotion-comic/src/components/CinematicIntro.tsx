import React from "react";
import { AbsoluteFill, Img, interpolate, staticFile, useCurrentFrame, useVideoConfig } from "remotion";

// ~4s at 24fps: the cover drifts closer under a vignette, the title settles
// in over it, and the whole card hands off to shot 1 through black.
export const INTRO_SECONDS = 4;
export const getIntroDuration = (fps: number) => Math.round(INTRO_SECONDS * fps);

interface Props {
  title: string;
  coverSrc: string;
}

export const CinematicIntro: React.FC<Props> = ({ title, coverSrc }) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();

  const zoom = interpolate(frame, [0, durationInFrames], [1.08, 1.22]);
  const coverIn = interpolate(frame, [0, Math.round(0.5 * fps)], [0, 1], {
    extrapolateRight: "clamp",
  });
  const titleAt = Math.round(1.0 * fps);
  const titleOpacity = interpolate(frame, [titleAt, titleAt + Math.round(0.6 * fps)], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const titleRise = interpolate(titleOpacity, [0, 1], [24, 0]);
  const lineWidth = interpolate(
    frame,
    [titleAt + Math.round(0.4 * fps), titleAt + Math.round(1.0 * fps)],
    [0, 360],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );
  // Hand off through black so shot 1 opens clean.
  const fadeOut = interpolate(frame, [durationInFrames - 12, durationInFrames], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill style={{ backgroundColor: "#000" }}>
      <style>{`
        @font-face {
          font-family: 'Bungee';
          src: url('${staticFile("fonts/Bungee-Regular.ttf")}');
        }
      `}</style>
      <AbsoluteFill style={{ opacity: coverIn }}>
        <Img
          src={staticFile(coverSrc)}
          style={{
            width: "100%",
            height: "100%",
            objectFit: "cover",
            transform: `scale(${zoom})`,
            transformOrigin: "center 35%",
          }}
        />
      </AbsoluteFill>
      <AbsoluteFill
        style={{
          background:
            "radial-gradient(ellipse at center, rgba(0,0,0,0.25) 0%, rgba(0,0,0,0.78) 100%)",
        }}
      />
      <AbsoluteFill
        style={{ justifyContent: "center", alignItems: "center", textAlign: "center" }}
      >
        <div
          style={{
            opacity: titleOpacity,
            transform: `translateY(${titleRise}px)`,
            color: "#fff",
            fontFamily: "Bungee, sans-serif",
            fontSize: 84,
            lineHeight: 1.15,
            padding: "0 8%",
            textShadow: "0 4px 30px rgba(0,0,0,0.9)",
          }}
        >
          {title}
        </div>
        <div
          style={{
            width: lineWidth,
            height: 5,
            marginTop: 28,
            backgroundColor: "#ffd400",
            borderRadius: 3,
          }}
        />
      </AbsoluteFill>
      {fadeOut > 0 && (
        <AbsoluteFill style={{ backgroundColor: "#000", opacity: fadeOut }} />
      )}
    </AbsoluteFill>
  );
};
