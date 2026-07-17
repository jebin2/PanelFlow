import React from "react";
import { AbsoluteFill, Img, spring, staticFile, useCurrentFrame, useVideoConfig } from "remotion";

// Chat-popup speaker tag: the character's face in a circle beside their name,
// popping in at the top-left when a shot's narration is their spoken line.
export const NameTag: React.FC<{ name: string; imageSrc: string }> = ({ name, imageSrc }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const pop = spring({
    frame,
    fps,
    config: { damping: 12, stiffness: 160, mass: 0.7 },
    durationInFrames: 18,
  });

  return (
    <AbsoluteFill
      style={{
        justifyContent: "flex-start",
        alignItems: "flex-start",
        padding: "3.5% 0 0 3%",
        pointerEvents: "none",
        zIndex: 90,
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
          display: "flex",
          alignItems: "center",
          gap: 16,
          transform: `scale(${pop}) translateX(${(1 - pop) * -40}px)`,
          transformOrigin: "left center",
          opacity: pop,
          backgroundColor: "rgba(10,10,14,0.72)",
          borderRadius: 60,
          padding: "8px 28px 8px 8px",
          boxShadow: "0 6px 24px rgba(0,0,0,0.55)",
        }}
      >
        <Img
          src={staticFile(imageSrc)}
          style={{
            width: 84,
            height: 84,
            borderRadius: "50%",
            objectFit: "cover",
            border: "3px solid #ffd400",
          }}
        />
        <div
          style={{
            fontFamily: "Bungee, sans-serif",
            fontSize: 34,
            color: "#fff",
            textShadow: "0 2px 8px rgba(0,0,0,0.8)",
            whiteSpace: "nowrap",
          }}
        >
          {name}
        </div>
      </div>
    </AbsoluteFill>
  );
};
