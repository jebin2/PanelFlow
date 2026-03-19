import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig, staticFile } from "remotion";
import { PanelData } from "../types";

export const KineticSubtitles: React.FC<{ panel: PanelData }> = ({ panel }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  if (!panel.wordTimings || panel.wordTimings.length === 0) {
    return null;
  }

  const currentSeconds = frame / fps;

  const currentWord = panel.wordTimings.find(
    (wt) => currentSeconds >= wt.start && currentSeconds <= wt.end
  );

  if (!currentWord) {
    return null;
  }

  const wordStartFrame = currentWord.start * fps;

  // Pop animation for the current word
  const scale = interpolate(
    frame,
    [wordStartFrame, wordStartFrame + 2, wordStartFrame + 6],
    [1.0, 1.3, 1.1],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );

  return (
    <AbsoluteFill
      style={{
        display: "flex",
        justifyContent: "flex-end", // Push to bottom
        alignItems: "center",
        paddingBottom: "25%", // High enough to avoid UI elements of Shorts/TikTok
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
          position: "relative",
          transform: `scale(${scale})`,
          textAlign: "center",
          maxWidth: "90%",
          filter: "drop-shadow(0px 12px 15px rgba(0,0,0,0.7))", // Global depth
        }}
      >
        {/* Layer 1: Ultra-Thick Black Border (Back) */}
        <span
          style={{
            position: "absolute",
            left: 0,
            right: 0,
            top: 0,
            fontFamily: "Bungee, sans-serif",
            fontSize: currentWord.word.length > 8 ? "85px" : "135px",
            fontWeight: 900,
            color: "black",
            textTransform: "uppercase",
            WebkitTextStroke: "30px black", // Increased to massive 30px
            lineHeight: 1,
            letterSpacing: "4px", // Spacing it out more to allow for thick borders
            wordBreak: "break-word",
            paintOrder: "stroke fill",
          }}
        >
          {currentWord.word}
        </span>
        
        {/* Layer 2: White Text (Front) */}
        <span
          style={{
            position: "relative",
            fontFamily: "Bungee, sans-serif",
            fontSize: currentWord.word.length > 8 ? "85px" : "135px",
            fontWeight: 900,
            color: "white",
            textTransform: "uppercase",
            lineHeight: 1,
            letterSpacing: "4px",
            wordBreak: "break-word",
            // Small internal shadow for crispness
            textShadow: "0px 4px 8px rgba(0,0,0,0.3)",
          }}
        >
          {currentWord.word}
        </span>
      </div>
    </AbsoluteFill>
  );
};
