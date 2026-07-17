import React from "react";
import { AbsoluteFill, Img, interpolate, staticFile, useCurrentFrame, useVideoConfig } from "remotion";

// ~5s at 24fps: fade in from the last shot, "THE END" over the title, then
// the subscribe prompt. The standard YouTube close, kept quiet. The director
// may choose a backdrop panel (a quiet aftermath image), drawn heavily dimmed
// under the text; without one the card stays dark.
export const OUTRO_SECONDS = 5;
export const getOutroDuration = (fps: number) => Math.round(OUTRO_SECONDS * fps);

interface Props {
  title: string;
  backdropSrc?: string;
}

export const EndCard: React.FC<Props> = ({ title, backdropSrc }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const cardIn = interpolate(frame, [0, Math.round(0.4 * fps)], [0, 1], {
    extrapolateRight: "clamp",
  });
  const endAt = Math.round(0.5 * fps);
  const endOpacity = interpolate(frame, [endAt, endAt + Math.round(0.5 * fps)], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const ctaAt = Math.round(2.0 * fps);
  const ctaOpacity = interpolate(frame, [ctaAt, ctaAt + Math.round(0.5 * fps)], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const ctaPulse = 1 + 0.02 * Math.sin(((frame - ctaAt) / fps) * Math.PI * 1.5);

  return (
    <AbsoluteFill style={{ backgroundColor: "#0b0b0d", opacity: cardIn }}>
      <style>{`
        @font-face {
          font-family: 'Bungee';
          src: url('${staticFile("fonts/Bungee-Regular.ttf")}');
        }
      `}</style>
      {backdropSrc && (
        <>
          <Img
            src={staticFile(backdropSrc)}
            style={{ width: "100%", height: "100%", objectFit: "cover" }}
          />
          <AbsoluteFill
            style={{
              background:
                "radial-gradient(ellipse at center, rgba(11,11,13,0.82) 0%, rgba(11,11,13,0.95) 100%)",
            }}
          />
        </>
      )}
      <AbsoluteFill
        style={{ justifyContent: "center", alignItems: "center", textAlign: "center" }}
      >
      <div
        style={{
          opacity: endOpacity,
          color: "#fff",
          fontFamily: "Bungee, sans-serif",
          fontSize: 96,
          letterSpacing: 4,
        }}
      >
        THE END
      </div>
      <div
        style={{
          opacity: endOpacity,
          color: "rgba(255,255,255,0.55)",
          fontFamily: "Bungee, sans-serif",
          fontSize: 30,
          marginTop: 18,
          padding: "0 10%",
          lineHeight: 1.3,
        }}
      >
        {title}
      </div>
      <div
        style={{
          opacity: ctaOpacity,
          transform: `scale(${ctaPulse})`,
          color: "#ffd400",
          fontFamily: "Bungee, sans-serif",
          fontSize: 34,
          marginTop: 64,
        }}
      >
        LIKE &amp; SUBSCRIBE FOR MORE COMICS
      </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
