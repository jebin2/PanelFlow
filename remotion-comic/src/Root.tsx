import React from "react";
import { AbsoluteFill, Composition } from "remotion";
import { ComicManifest } from "./types";
import { PanelSequences, getTotalFrames } from "./components/PanelSequences";

const defaultManifest: ComicManifest = {
  fps: 24,
  width: 1920,
  height: 1080,
  comicTitle: "Comic",
  pageNumber: 1,
  panels: [
    {
      imageSrc: "",
      audioSrc: "",
      durationInSeconds: 5,
      bubbleBbox: [0, 0, 1920, 1080],
      narrationText: "",
      sceneCaption: "",
      animation: "ken_burns",
    },
  ],
};

const ComicVideoComp: React.FC<{ manifest: ComicManifest }> = ({ manifest }) => {
  return (
    <AbsoluteFill style={{ backgroundColor: "#000" }}>
      <PanelSequences panels={manifest.panels} fps={manifest.fps} />
    </AbsoluteFill>
  );
};

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="ComicVideo"
      component={ComicVideoComp}
      defaultProps={{ manifest: defaultManifest }}
      fps={defaultManifest.fps}
      width={defaultManifest.width}
      height={defaultManifest.height}
      durationInFrames={getTotalFrames(defaultManifest.panels, defaultManifest.fps)}
      calculateMetadata={({ props }) => {
        const { manifest } = props;
        return {
          fps: manifest.fps,
          width: manifest.width,
          height: manifest.height,
          durationInFrames: getTotalFrames(manifest.panels, manifest.fps),
        };
      }}
    />
  );
};
