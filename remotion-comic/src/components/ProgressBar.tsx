import React from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from "remotion";

export const ProgressBar: React.FC = () => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();

  const progress = Math.min(frame / (durationInFrames - 1), 1);

  return (
    <AbsoluteFill style={{ pointerEvents: "none", zIndex: 200 }}>
      {/* Track */}
      <div
        style={{
          position: "absolute",
          bottom: 0,
          left: 0,
          right: 0,
          height: "7px",
          backgroundColor: "rgba(255, 255, 255, 0.20)",
        }}
      >
        {/* Fill */}
        <div
          style={{
            height: "100%",
            width: `${progress * 100}%`,
            background: "linear-gradient(90deg, #FF6B35 0%, #FFD23F 100%)",
            borderRadius: "0 4px 4px 0",
            boxShadow: "0 0 8px rgba(255, 107, 53, 0.7)",
          }}
        />
      </div>
    </AbsoluteFill>
  );
};
