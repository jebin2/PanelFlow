import { PanelAnimation } from "./types";

export interface PanelBaseProps {
  zoomStart?: number;
  zoomEnd?: number;
  zoomSettleFraction?: number;
  panXStart?: number;
  panXEnd?: number;
  panYStart?: number;
  panYEnd?: number;
  rotateStart?: number;    // degrees — for tilt_in / spin_in
  rotateEnd?: number;
  rotateSettleFraction?: number;
  slideFrom?: "left" | "right" | "bottom" | "top" | null;
  slideCompleteFraction?: number;
  shake?: boolean;
  fadeIn?: boolean;
  flashEffect?: boolean;
  punchIn?: boolean;
  recoilEffect?: boolean;
  heartbeatEffect?: boolean;
  trembleEffect?: boolean;
  rattleEffect?: boolean;
  shockwaveEffect?: boolean;
  breatheEffect?: boolean;
}

export function getAnimationProps(animation: PanelAnimation): PanelBaseProps {
  switch (animation) {

    // ── Impact / Energy ─────────────────────────────────────────────────────
    case "burst":
      return { zoomStart: 1.15, zoomEnd: 1.0, zoomSettleFraction: 0.25, shake: true };
    case "snap":
      return { zoomStart: 1.2, zoomEnd: 1.0, zoomSettleFraction: 0.04, shake: true };
    case "slam_left":
      return { slideFrom: "left", slideCompleteFraction: 0.06, zoomStart: 1.02, zoomEnd: 1.0 };
    case "slam_right":
      return { slideFrom: "right", slideCompleteFraction: 0.06, zoomStart: 1.02, zoomEnd: 1.0 };
    case "whip_left":
      return { slideFrom: "left", slideCompleteFraction: 0.03 };
    case "whip_right":
      return { slideFrom: "right", slideCompleteFraction: 0.03 };
    case "punch_in":
      return { punchIn: true };
    case "recoil":
      return { recoilEffect: true };
    case "shockwave":
      return { shockwaveEffect: true };
    case "flash":
      return { flashEffect: true, zoomStart: 1.0, zoomEnd: 1.04 };

    // ── Tension / Sustained ─────────────────────────────────────────────────
    case "heartbeat":
      return { heartbeatEffect: true };
    case "tremble":
      return { trembleEffect: true, zoomStart: 1.0, zoomEnd: 1.02 };
    case "rattle":
      return { rattleEffect: true, zoomStart: 1.0, zoomEnd: 1.02 };

    // ── Slides ───────────────────────────────────────────────────────────────
    case "slide_left":
      return { slideFrom: "left", slideCompleteFraction: 0.2 };
    case "slide_right":
      return { slideFrom: "right", slideCompleteFraction: 0.2 };
    case "slide_bottom":
      return { slideFrom: "bottom", slideCompleteFraction: 0.2 };
    case "slide_top":
      return { slideFrom: "top", slideCompleteFraction: 0.2 };

    // ── Rotation ─────────────────────────────────────────────────────────────
    case "tilt_in":
      return { rotateStart: 4, rotateEnd: 0, rotateSettleFraction: 0.25, zoomStart: 1.0, zoomEnd: 1.02 };
    case "spin_in":
      return { rotateStart: 15, rotateEnd: 0, rotateSettleFraction: 0.2, zoomStart: 1.05, zoomEnd: 1.0 };

    // ── Camera ────────────────────────────────────────────────────────────────
    case "ken_burns":
      return { zoomStart: 1.0, zoomEnd: 1.08, panXStart: -15, panXEnd: 15 };
    case "zoom_out":
      return { zoomStart: 1.12, zoomEnd: 1.0, zoomSettleFraction: 0.5 };
    case "zoom_in":
      return { zoomStart: 1.0, zoomEnd: 1.12 };
    case "pan_up":
      return { zoomStart: 1.05, zoomEnd: 1.05, panYStart: 30, panYEnd: -30 };
    case "pan_down":
      return { zoomStart: 1.05, zoomEnd: 1.05, panYStart: -30, panYEnd: 30 };
    case "breathe":
      return { breatheEffect: true };
    case "creep":
      return { zoomStart: 1.0, zoomEnd: 1.03 };
    case "fade_in":
      return { zoomStart: 1.0, zoomEnd: 1.04, fadeIn: true };

    default:
      return { zoomStart: 1.0, zoomEnd: 1.08 };
  }
}
