import React, { useMemo } from "react";
import { AbsoluteFill, Audio, Img, Sequence, interpolate, random, spring, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { PanelData } from "../types";

export const AssembleIntro: React.FC<{ panel: PanelData }> = ({ panel }) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames, width: fullWidth, height: fullHeight } = useVideoConfig();
  
  const [boxX, boxY, boxW, boxH] = panel.bubbleBbox && panel.bubbleBbox.length === 4 
    ? panel.bubbleBbox 
    : [0, 0, fullWidth, fullHeight];

  // Dynamically size grid so pieces are roughly 200px
  const targetPieceSize = 250;
  const COLS = Math.max(3, Math.round(boxW / targetPieceSize));
  const ROWS = Math.max(3, Math.round(boxH / targetPieceSize));
  
  const pieceWidth = boxW / COLS;
  const pieceHeight = boxH / ROWS;
  
  // Snap pieces together by 1.5s or 40% of duration
  const assembleDuration = Math.min(fps * 1.5, Math.floor(durationInFrames * 0.4));

  // Energy Weld glow opacity peaking EXACTLY when they snap together
  const energyWeldOpacity = interpolate(
    frame,
    [Math.max(0, assembleDuration - 10), assembleDuration, assembleDuration + 8],
    [0, 1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );

  // Impact scale pulse + gentle dramatic drift
  const zoom = frame < assembleDuration
    ? 1
    : interpolate(frame, [assembleDuration, assembleDuration + 5, durationInFrames], [1.08, 1.02, 1.06], { extrapolateRight: "clamp" });

  // Camera Shake right when the pieces hit each other
  const shakeX = frame >= assembleDuration && frame < assembleDuration + 10
    ? Math.sin(frame * 4.3) * interpolate(frame, [assembleDuration, assembleDuration + 10], [12, 0], { extrapolateRight: "clamp" })
    : 0;

  const shakeY = frame >= assembleDuration && frame < assembleDuration + 10
    ? Math.cos(frame * 4.7) * interpolate(frame, [assembleDuration, assembleDuration + 10], [12, 0], { extrapolateRight: "clamp" })
    : 0;

  
  // Pre-calculate random targets so they don't jump per frame
  const puzzlePieces = useMemo(() => {
    const arr = [];
    for (let r = 0; r < ROWS; r++) {
      for (let c = 0; c < COLS; c++) {
        const index = r * COLS + c;
        const seed = index + 42;
        
        // Random starting positions (outside the main view)
        const startX = (random(`x_${seed}`) * 2 - 1) * fullWidth * 1.5;
        const startY = (random(`y_${seed}`) * 2 - 1) * fullHeight * 1.5;
        const startRot = (random(`rot_${seed}`) * 2 - 1) * 360; // -360 to 360
        // Random delay for a staggered entrance
        const delayFrames = Math.floor(random(`delay_${seed}`) * (fps * 0.5));

        arr.push({ r, c, index, startX, startY, startRot, delayFrames });
      }
    }
    return arr;
  }, [fullWidth, fullHeight, fps]);

  return (
    <AbsoluteFill style={{ backgroundColor: "#000" }}>
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

      {/* Background container that punches and shakes after assembling */}
      <AbsoluteFill
        style={{
          transform: `scale(${zoom}) translate(${shakeX}px, ${shakeY}px)`,
          transformOrigin: "center center",
        }}
      >
        {puzzlePieces.map((piece) => {
          // Spring physics for snapping
          const progress = spring({
            frame: Math.max(0, frame - piece.delayFrames),
            fps,
            config: { damping: 14, stiffness: 100 },
            durationInFrames: assembleDuration - piece.delayFrames,
          });

          const xShift = interpolate(progress, [0, 1], [piece.startX, 0]);
          const yShift = interpolate(progress, [0, 1], [piece.startY, 0]);
          const rotate = interpolate(progress, [0, 1], [piece.startRot, 0]);

          // Fade in early
          const opacity = interpolate(Math.max(0, frame - piece.delayFrames), [0, 5], [0, 1], { extrapolateRight: "clamp" });

          return (
            <div
              key={piece.index}
              style={{
                position: "absolute",
                width: pieceWidth,
                height: pieceHeight,
                left: boxX + piece.c * pieceWidth,
                top: boxY + piece.r * pieceHeight,
                overflow: "hidden",
                opacity,
                transform: `translate(${xShift}px, ${yShift}px) rotate(${rotate}deg)`,
                transformOrigin: "center center",
                // Energy Weld: 2px solid line + inner/outer glow using pure boxShadow to avoid layout shift
                boxShadow: energyWeldOpacity > 0
                  ? `0 0 0 2px rgba(0, 255, 255, ${energyWeldOpacity}),
                     0 0 15px rgba(0, 255, 255, ${energyWeldOpacity}),
                     inset 0 0 15px rgba(0, 255, 255, ${energyWeldOpacity})`
                  : undefined,
                zIndex: energyWeldOpacity > 0 ? 10 : 1,
              }}
            >
              {panel.imageSrc && (
                <Img
                  src={staticFile(panel.imageSrc)}
                  style={{
                    position: "absolute",
                    left: -(boxX + piece.c * pieceWidth),
                    top: -(boxY + piece.r * pieceHeight),
                    width: fullWidth,
                    height: fullHeight,
                    objectFit: "contain",
                  }}
                />
              )}
            </div>
          );
        })}
      </AbsoluteFill>

      {panel.audioSrc && <Audio src={staticFile(panel.audioSrc)} />}

      {/* Pieces flying in — soft whoosh as they travel */}
      <Audio src={staticFile("sfx/sfx_whoosh.mp3")} volume={0.28} />

      {/* Snap moment — deep boom when all pieces lock together */}
      <Sequence from={assembleDuration} durationInFrames={60} layout="none">
        <Audio src={staticFile("sfx/sfx_impact.mp3")} volume={0.55} />
      </Sequence>

      {/* Energy weld glow — electrical flash sound synced to cyan glow */}
      <Sequence from={Math.max(0, assembleDuration - 3)} durationInFrames={30} layout="none">
        <Audio src={staticFile("sfx/sfx_flash.mp3")} volume={0.30} />
      </Sequence>
    </AbsoluteFill>
  );
};
