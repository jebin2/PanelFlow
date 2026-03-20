import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig, staticFile } from "remotion";
import { PanelData } from "../types";

// Deterministic tilt per word so it looks hand-placed, not random
function wordTilt(word: string): number {
  const code = word.split("").reduce((acc, c) => acc + c.charCodeAt(0), 0);
  return ((code % 11) - 5) * 0.9; // -4.5 to +4.5 degrees
}

// Alternate yellow / white for visual rhythm
function wordColor(index: number): string {
  return index % 2 === 0 ? "#FFE600" : "#FFFFFF";
}

export const KineticSubtitles: React.FC<{ panel: PanelData }> = ({ panel }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  if (!panel.wordTimings || panel.wordTimings.length === 0) return null;

  const currentSeconds = frame / fps;

  const currentIndex = panel.wordTimings.findIndex(
    (wt) => currentSeconds >= wt.start && currentSeconds <= wt.end
  );

  if (currentIndex === -1) return null;

  const currentWord = panel.wordTimings[currentIndex];
  const wordStartFrame = Math.round(currentWord.start * fps);

  const elapsed = frame - wordStartFrame;

  // Snappy overshoot scale: starts small, punches past target, settles
  const scale = interpolate(
    elapsed,
    [0, 3, 7, 13],
    [0.6, 1.45, 1.05, 1.1],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );

  // Vertical bounce: drops in from slightly above
  const translateY = interpolate(
    elapsed,
    [0, 4, 9, 14],
    [-30, 6, -3, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );

  // Tilt settles to 0 after entry
  const tiltBase = wordTilt(currentWord.word);
  const tilt = interpolate(
    elapsed,
    [0, 5, 12],
    [tiltBase * 2.5, -tiltBase * 0.4, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );

  const color = wordColor(currentIndex);
  const fontSize = currentWord.word.length > 9 ? "90px" : "140px";
  const strokeColor = "#000000";

  return (
    <AbsoluteFill
      style={{
        display: "flex",
        justifyContent: "flex-end",
        alignItems: "center",
        paddingBottom: "22%",
        paddingLeft: "40px",
        paddingRight: "40px",
        pointerEvents: "none",
        zIndex: 100,
      }}
    >
      <style>{`
        @font-face {
          font-family: 'Bungee';
          src: url('${staticFile("fonts/Bungee-Regular.ttf")}');
        }
      `}</style>

      <div
        style={{
          transform: `scale(${scale}) translateY(${translateY}px) rotate(${tilt}deg)`,
          transformOrigin: "center bottom",
          textAlign: "center",
          maxWidth: "88%",
          filter: `drop-shadow(0px 6px 0px ${strokeColor}) drop-shadow(0px -6px 0px ${strokeColor}) drop-shadow(6px 0px 0px ${strokeColor}) drop-shadow(-6px 0px 0px ${strokeColor}) drop-shadow(0px 16px 20px rgba(0,0,0,0.85))`,
        }}
      >
        <div style={{ position: "relative" }}>
          {/* Layer 1: thick black outline */}
          <span
            style={{
              position: "absolute",
              left: 0,
              right: 0,
              top: 0,
              fontFamily: "Bungee, sans-serif",
              fontSize,
              fontWeight: 900,
              color: strokeColor,
              textTransform: "uppercase",
              WebkitTextStroke: "22px black",
              lineHeight: 1,
              letterSpacing: "3px",
              wordBreak: "break-word",
              paintOrder: "stroke fill",
            }}
          >
            {currentWord.word}
          </span>

          {/* Layer 2: coloured text */}
          <span
            style={{
              position: "relative",
              fontFamily: "Bungee, sans-serif",
              fontSize,
              fontWeight: 900,
              color,
              textTransform: "uppercase",
              lineHeight: 1,
              letterSpacing: "3px",
              wordBreak: "break-word",
            }}
          >
            {currentWord.word}
          </span>
        </div>
      </div>
    </AbsoluteFill>
  );
};
