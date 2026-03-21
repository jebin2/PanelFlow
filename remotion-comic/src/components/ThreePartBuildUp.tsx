import React from "react";
import {
  AbsoluteFill,
  Audio,
  Img,
  Sequence,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { PanelData } from "../types";

export const ThreePartBuildUp: React.FC<{ panel: PanelData }> = ({ panel }) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames, height: screenHeight, width: screenWidth } = useVideoConfig();

  const imgAspect =
    panel.originalWidth && panel.originalHeight
      ? panel.originalWidth / panel.originalHeight
      : 0.6;

  // Fit image to 96% of screen width, but also cap so the full 3-section stack
  // never exceeds 2.7× screen height (keeps all sections visible on landscape too)
  const maxByWidth = screenWidth * 0.96;
  const maxByHeight = screenHeight * 2.7 * imgAspect; // sectionH ≤ 0.9 × screenHeight
  const imgRenderWidth = Math.min(maxByWidth, maxByHeight);
  const imgRenderHeight = imgRenderWidth / imgAspect;
  const sectionH = imgRenderHeight / 3;
  const groupLeft = (screenWidth - imgRenderWidth) / 2; // = screenWidth * 0.02

  const phaseFrames = Math.floor(durationInFrames / 3);
  const transitionFrames = Math.min(24, Math.floor(phaseFrames / 2));

  // Smoothly track how many sections are visible (1 → 2 → 3)
  // used to keep the cumulative stack vertically centred on screen
  const numVisible = interpolate(
    frame,
    [
      phaseFrames - transitionFrames / 2,
      phaseFrames + transitionFrames / 2,
      2 * phaseFrames - transitionFrames / 2,
      2 * phaseFrames + transitionFrames / 2,
    ],
    [1, 2, 2, 3],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );

  // Top of the whole stack so visible content stays centred
  const groupTop = screenHeight / 2 - (numVisible * sectionH) / 2;

  const renderSection = (index: number) => {
    const startFrame = index * phaseFrames;

    // Spring slide-in from below
    const slideProgress = spring({
      frame: frame - startFrame,
      fps,
      config: { damping: 16, stiffness: 100 },
      durationInFrames: transitionFrames,
    });

    const slideY =
      frame < startFrame
        ? screenHeight
        : interpolate(slideProgress, [0, 1], [screenHeight, 0]);

    // Absolute position of this section on screen
    const sectionTop = groupTop + index * sectionH;

    return (
      <div
        key={index}
        style={{
          position: "absolute",
          left: groupLeft,
          top: sectionTop,
          width: imgRenderWidth,
          height: sectionH,
          overflow: "hidden",
          transform: `translateY(${slideY}px)`,
          opacity: frame < startFrame ? 0 : 1,
        }}
      >
        {/* Full image shifted up so the correct 1/3 row is visible */}
        <Img
          src={staticFile(panel.imageSrc)}
          style={{
            position: "absolute",
            top: -(index * sectionH),
            left: 0,
            width: imgRenderWidth,
            height: imgRenderHeight,
          }}
        />
      </div>
    );
  };

  return (
    <AbsoluteFill style={{ backgroundColor: "#000", overflow: "hidden" }}>
      {/* Blurred background fill */}
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

      {renderSection(0)}
      {renderSection(1)}
      {renderSection(2)}

      {panel.audioSrc && <Audio src={staticFile(panel.audioSrc)} />}

      {/* Section SFX — escalating sounds as each strip slides up */}
      <Sequence from={0}           durationInFrames={transitionFrames} layout="none">
        <Audio src={staticFile("sfx/sfx_whoosh.mp3")}       volume={0.28} />
      </Sequence>
      <Sequence from={phaseFrames} durationInFrames={transitionFrames} layout="none">
        <Audio src={staticFile("sfx/sfx_paper_slide.mp3")}  volume={0.40} />
      </Sequence>
      <Sequence from={phaseFrames * 2} durationInFrames={transitionFrames} layout="none">
        <Audio src={staticFile("sfx/sfx_sandbag.mp3")}      volume={0.42} />
      </Sequence>
    </AbsoluteFill>
  );
};
