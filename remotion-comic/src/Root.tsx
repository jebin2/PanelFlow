import React from "react";
import { AbsoluteFill, Composition, Sequence } from "remotion";
import { ComicManifest } from "./types";
import { PanelSequences, getTotalFrames } from "./components/PanelSequences";
import { ProgressBar, TitleCard, getTitleCardDuration } from "remotion-animation-kit";

const TITLE_CARD_FRAMES = getTitleCardDuration(24);

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
  const isPortrait = manifest.height > manifest.width;
  const showTitle = isPortrait;
  const titleOffset = showTitle ? TITLE_CARD_FRAMES : 0;
  return (
    <AbsoluteFill style={{ backgroundColor: "#000" }}>
      {showTitle && (
        <Sequence from={0} durationInFrames={TITLE_CARD_FRAMES} layout="none">
          <TitleCard
            title={manifest.comicTitle}
            media={manifest.panels.map((p) => ({ imageSrc: p.imageSrc }))}
          />
        </Sequence>
      )}
      <Sequence from={titleOffset} layout="none">
        <PanelSequences panels={manifest.panels} fps={manifest.fps} />
      </Sequence>
      {isPortrait && <ProgressBar />}
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
      durationInFrames={TITLE_CARD_FRAMES + getTotalFrames(defaultManifest.panels, defaultManifest.fps)}
      calculateMetadata={({ props }) => {
        const { manifest } = props;
        const isPortrait = manifest.height > manifest.width;
        const titleFrames = isPortrait ? TITLE_CARD_FRAMES : 0;
        return {
          fps: manifest.fps,
          width: manifest.width,
          height: manifest.height,
          durationInFrames: titleFrames + getTotalFrames(manifest.panels, manifest.fps),
        };
      }}
    />
  );
};
