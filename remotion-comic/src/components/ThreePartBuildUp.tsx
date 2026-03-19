import React from "react";
import { AbsoluteFill, Img, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig, Audio, Easing } from "remotion";
import { PanelData } from "../types";

export const ThreePartBuildUp: React.FC<{ panel: PanelData }> = ({ panel }) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames, height: screenHeight, width: screenWidth } = useVideoConfig();

  const imgAspect = (panel.originalWidth && panel.originalHeight) 
    ? panel.originalWidth / panel.originalHeight 
    : 0.6; // fallback for typical portrait comic

  // With objectFit: "contain", the image is rendered with height = screenHeight.
  // To scale so that the image width fits the screen width:
  const fitWidthScale = screenWidth / (screenHeight * imgAspect);

  // Target scales for each phase:
  // Phase 1 (1 part): fill the screen as much as possible (up to 3x height)
  const scale1 = Math.min(fitWidthScale, 3.0);
  // Phase 2 (2 parts): fill the screen as much as possible (up to 1.5x height)
  const scale2 = Math.min(fitWidthScale, 1.5);
  // Phase 3 (3 parts): standard Ken Burns start
  const scale3 = 1.05;

  const phaseFrames = Math.floor(durationInFrames / 3);
  const transitionFrames = Math.min(30, Math.floor(phaseFrames / 2));

  // Ken Burns: subtle zoom throughout
  const zoom = interpolate(
    frame,
    [0, durationInFrames],
    [1.0, 1.1],
    { extrapolateRight: "clamp" }
  );

  // Dynamic base scale: zooms out as more segments are added
  const baseScale = interpolate(
    frame,
    [
      phaseFrames - transitionFrames / 2, 
      phaseFrames + transitionFrames / 2, 
      2 * phaseFrames - transitionFrames / 2, 
      2 * phaseFrames + transitionFrames / 2
    ],
    [scale1, scale2, scale2, scale3],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.bezier(0.33, 1, 0.68, 1) }
  );

  const finalZoom = zoom * baseScale;

  // Gentle drift
  const driftY = interpolate(frame, [0, durationInFrames], [-25, 25]);

  const renderPart = (index: number) => {
    const startFrame = index * phaseFrames;
    const isAppearing = frame >= startFrame && frame < startFrame + transitionFrames;
    
    // Individual slide-in progress
    const slideProgress = spring({
      frame: frame - startFrame,
      fps,
      config: { damping: 16, stiffness: 100 },
      durationInFrames: transitionFrames,
    });

    // Vertical "push up" to keep visible parts centered
    // Phase 1 (0 to 1/3): Top 1/3 is centered. Offset = 33%
    // Phase 2 (1/3 to 2/3): Top 2/3 are centered. Offset = 16.5%
    // Phase 3 (2/3 to end): All 100% is centered. Offset = 0%
    const pushUpOffset = interpolate(
      frame,
      [
        phaseFrames - transitionFrames / 2, 
        phaseFrames + transitionFrames / 2, 
        2 * phaseFrames - transitionFrames / 2, 
        2 * phaseFrames + transitionFrames / 2
      ],
      [33.33, 16.66, 16.66, 0],
      { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.bezier(0.33, 1, 0.68, 1) }
    );

    // Current part Y position (relative to its slot)
    // When appearing, it slides from below the screen.
    const baseY = frame < startFrame ? screenHeight : interpolate(slideProgress, [0, 1], [screenHeight, 0]);

    const clipTop = (index * 33.33) + "%";
    const clipBottom = (100 - (index + 1) * 33.33) + "%";

    return (
      <AbsoluteFill
        key={index}
        style={{
          transform: `translateY(${pushUpOffset}%)`,
          opacity: frame < startFrame ? 0 : 1,
        }}
      >
        <AbsoluteFill
          style={{
            transform: `translateY(${baseY}px)`,
            clipPath: `inset(${clipTop} 0% ${clipBottom} 0%)`,
          }}
        >
          <Img
            src={staticFile(panel.imageSrc)}
            style={{
              width: "100%",
              height: "100%",
              objectFit: "contain",
            }}
          />
        </AbsoluteFill>
      </AbsoluteFill>
    );
  };

  return (
    <AbsoluteFill style={{ backgroundColor: "#000", overflow: "hidden" }}>
      {/* Blurred background fill — hides black bars */}
      {panel.imageSrc && (
        <Img
          src={staticFile(panel.imageSrc)}
          style={{
            position: "absolute",
            width: "100%",
            height: "100%",
            objectFit: "cover",
            filter: "blur(24px) brightness(0.35)",
            transform: "scale(1.08)",
          }}
        />
      )}
      <AbsoluteFill style={{ transform: `scale(${finalZoom}) translateY(${driftY}px)` }}>
        {renderPart(0)}
        {renderPart(1)}
        {renderPart(2)}
      </AbsoluteFill>
      {panel.audioSrc && <Audio src={staticFile(panel.audioSrc)} />}
    </AbsoluteFill>
  );
};
