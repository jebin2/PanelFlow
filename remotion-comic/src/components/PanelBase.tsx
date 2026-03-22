import React from "react";
import { Audio, Img, staticFile } from "remotion";
import { AnimatedBase } from "remotion-animation-kit";
import type { BaseAnimationProps } from "remotion-animation-kit";
import { PanelData } from "../types";

interface Props extends BaseAnimationProps {
  panel: PanelData;
}

export const PanelBase: React.FC<Props> = ({ panel, ...animProps }) => {
  const background = panel.imageSrc ? (
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
  ) : undefined;

  return (
    <AnimatedBase {...animProps} background={background} audioSrc={panel.audioSrc}>
      {panel.imageSrc && (
        <Img
          src={staticFile(panel.imageSrc)}
          style={{ width: "100%", height: "100%", objectFit: "contain" }}
        />
      )}
    </AnimatedBase>
  );
};
