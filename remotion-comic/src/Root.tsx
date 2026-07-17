import React from "react";
import { AbsoluteFill, Audio, Composition, Sequence, staticFile } from "remotion";
import { ComicManifest } from "./types";
import { PanelSequences, getTotalFrames } from "./components/PanelSequences";
import { CinematicIntro, getIntroDuration } from "./components/CinematicIntro";
import { EndCard, getOutroDuration } from "./components/EndCard";
import { ProgressBar, TitleCard, getTitleCardDuration } from "remotion-animation-kit";

const TITLE_CARD_FRAMES = getTitleCardDuration(24);
const INTRO_FRAMES = getIntroDuration(24);
const OUTRO_FRAMES = getOutroDuration(24);

// The portrait short opens on the slam TitleCard; landscape longform gets the
// calmer bookends — a cinematic cover intro and an end card.
const bookendFrames = (manifest: ComicManifest) => {
  const isPortrait = manifest.height > manifest.width;
  return isPortrait
    ? { intro: TITLE_CARD_FRAMES, outro: 0 }
    : { intro: INTRO_FRAMES, outro: OUTRO_FRAMES };
};

const defaultManifest: ComicManifest = {
  fps: 24,
  width: 1920,
  height: 1080,
  comicTitle: "Comic",
  panels: [
    {
      imageSrc: "",
      audioSrc: "",
      durationInSeconds: 5,
      narrationText: "",
      sceneCaption: "",
      animation: "ken_burns",
    },
  ],
};

const ComicVideoComp: React.FC<{ manifest: ComicManifest }> = ({ manifest }) => {
  const isPortrait = manifest.height > manifest.width;
  const { intro, outro } = bookendFrames(manifest);
  const panelFrames = getTotalFrames(manifest.panels, manifest.fps);
  const cover = manifest.cover ?? manifest.panels[0]?.imageSrc ?? "";
  return (
    <AbsoluteFill style={{ backgroundColor: "#000" }}>
      {manifest.music?.src && (
        <Audio src={staticFile(manifest.music.src)} volume={manifest.music.volume} />
      )}
      {isPortrait ? (
        <Sequence from={0} durationInFrames={intro} layout="none">
          <TitleCard
            title={manifest.comicTitle}
            media={manifest.panels.map((p) => ({ imageSrc: p.imageSrc }))}
          />
        </Sequence>
      ) : (
        <Sequence from={0} durationInFrames={intro} layout="none">
          <CinematicIntro title={manifest.comicTitle} coverSrc={cover} />
        </Sequence>
      )}
      <Sequence from={intro} layout="none">
        <PanelSequences panels={manifest.panels} fps={manifest.fps} />
      </Sequence>
      {outro > 0 && (
        <Sequence from={intro + panelFrames} durationInFrames={outro} layout="none">
          <EndCard title={manifest.comicTitle} backdropSrc={manifest.outroImage} />
        </Sequence>
      )}
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
        const { intro, outro } = bookendFrames(manifest);
        return {
          fps: manifest.fps,
          width: manifest.width,
          height: manifest.height,
          durationInFrames: intro + getTotalFrames(manifest.panels, manifest.fps) + outro,
        };
      }}
    />
  );
};
