export type PanelAnimation =
  // Impact / Energy
  | "burst"        // zoom burst 1.15→1.0 fast + shake
  | "snap"         // ultra-fast zoom 1.2→1.0 in ~3 frames — instant hit
  | "slam_left"    // panel crashes in from left (ultra-fast)
  | "slam_right"   // panel crashes in from right (ultra-fast)
  | "whip_left"    // extreme fast whip from left
  | "whip_right"   // extreme fast whip from right
  | "punch_in"     // aggressive zoom 1.0→1.2 fast, settle to 1.05
  | "recoil"       // quick zoom out 1.0→0.9 then bounce back
  | "shockwave"    // outward pulse 1.0→1.06→1.0 in first 16 frames, then settle
  | "flash"        // white flash burns in then fades
  // Tension / Sustained
  | "heartbeat"    // rhythmic pulsing zoom — standoffs
  | "tremble"      // rapid small shake dying out — fear
  | "rattle"       // constant low-level shake throughout — machinery, vibration
  // Slides
  | "slide_left"
  | "slide_right"
  | "slide_bottom"
  | "slide_top"
  // Rotation
  | "tilt_in"      // starts slightly rotated (~3°) and straightens — comic panel thrown into place
  | "spin_in"      // starts rotated (~15°) snaps straight — chaotic, dramatic
  // Camera
  | "ken_burns"    // slow zoom + horizontal drift — calm, emotional
  | "zoom_out"     // zoom out 1.12→1.0 — wide revealing shot
  | "zoom_in"      // slow push in 1.0→1.12 — building tension
  | "pan_up"       // camera drifts upward
  | "pan_down"     // camera drifts downward
  | "breathe"      // gentle oscillating zoom — calm meditative pause
  | "creep"        // extremely slow zoom 1.0→1.03 — dread, horror
  | "fade_in"      // fade from black
  | "assemble";    // pieces fly in and snap together

export type PanelTransition = "none" | "fade" | "slide" | "wipe" | "flip" | "toss";

export interface PanelEvent {
  type: "tremble" | "flash" | "shockwave" | "heartbeat" | "rattle";
  startSeconds: number;
  durationSeconds: number;
}

export interface PanelData {
  imageSrc: string;
  audioSrc: string;
  durationInSeconds: number;
  bubbleBbox: [number, number, number, number];
  narrationText: string;
  sceneCaption: string;
  animation: PanelAnimation;
  transitionIn?: PanelTransition;
  events?: PanelEvent[];
}

export interface ComicManifest {
  fps: number;
  width: number;
  height: number;
  comicTitle: string;
  pageNumber: number;
  panels: PanelData[];
}
