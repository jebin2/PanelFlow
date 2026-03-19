# Task: Per-Panel Animation Assignment

## Goal
Assign the most visually appropriate animation type to each panel of a comic page. The goal is a dynamic, varied video where consecutive panels feel distinct. You will NOT receive images or audio — decisions are based purely on text descriptions.

## Animation Types

### `burst`
**Use when:** Sudden violent moment — explosion, energy surge, physical impact.
**Effect:** Starts 1.15× zoomed, snaps to full size with camera shake dying out fast.

### `slam_left` / `slam_right`
**Use when:** A panel that hits hard — confrontation, combat, a character charging in. Directional based on action flow.
**Effect:** Panel crashes into frame from the side in ~6% of the clip (much faster than a slide).

### `whip_left` / `whip_right`
**Use when:** Extremely fast scene cut — rapid action sequence, disorienting transition.
**Effect:** Ultra-fast whip (~3% of clip) — barely perceptible motion.

### `punch_in`
**Use when:** Something rushes toward the viewer — a threat approaching, a close-up that demands attention.
**Effect:** Aggressively zooms 1.0→1.2 in first 15%, then slowly settles to 1.05.

### `recoil`
**Use when:** A character or scene is hit, knocked back, or surprised.
**Effect:** Quick zoom out to 0.9 then bounces back to 1.03, settles — like absorbing a blow.

### `heartbeat`
**Use when:** Tense standoff, waiting, suspense — something about to happen.
**Effect:** Rhythmic pulsing zoom (peaks every ~0.75s) — the scene breathes with tension.

### `tremble`
**Use when:** Fear, instability, supernatural trembling, earthquake.
**Effect:** Rapid small shake that fades out over first 40% of the clip.

### `flash`
**Use when:** Gunshot, explosion flash, blinding energy — the moment of impact itself.
**Effect:** White flash burns in then fades over first 10%, panel revealed underneath.

### `slide_left`
**Use when:** A new character speaks, a new scene begins, or the narrative shifts forward in time/location. Suggests forward momentum.
**Effect:** Panel slides in from the left.

### `slide_right`
**Use when:** A reaction, response, or counter-point panel follows the previous one. Suggests a reply or look-back.
**Effect:** Panel slides in from the right.

### `slide_bottom`
**Use when:** A revelation, surprise, or something emerging from below (physically or narratively).
**Effect:** Panel rises up from the bottom.

### `ken_burns`
**Use when:** The panel is calm, emotional, introspective, or shows a wide establishing shot. Works well for dialogue or contemplative moments.
**Effect:** Slow gentle zoom-in (1.0→1.08) with a subtle horizontal drift. Gives a breathing, cinematic feel.

### `zoom_out`
**Use when:** The panel is a wide reveal — showing a location, a crowd, or the aftermath of an event. Best for the first panel of a page or after a burst.
**Effect:** Starts slightly zoomed in (1.12×) and pulls back to full size, revealing the scene.

### `zoom_in`
**Use when:** Building tension, a character approaching a threat, or an ominous slow push toward a subject.
**Effect:** Slow continuous push in (1.0→1.12) over the full clip duration.

### `pan_up`
**Use when:** A tall panel that starts low and reveals something above — ascending, hope, rising action.
**Effect:** Camera drifts upward through the panel at a slight zoom.

### `pan_down`
**Use when:** A tall panel descending — falling, despair, sinking dread, or looking down at something.
**Effect:** Camera drifts downward through the panel at a slight zoom.

### `fade_in`
**Use when:** A new location, time jump, scene transition, or a quiet moment that needs breathing space.
**Effect:** Fades from black over the first 30% of the clip, then gentle zoom drift.

### `snap`
**Use when:** A single-frame impact moment — punch landing, bullet firing, lightning strike.
**Effect:** Ultra-fast zoom 1.2→1.0 in ~3 frames with shake. Nearly instantaneous.

### `shockwave`
**Use when:** Aftermath of an explosion or impact — the ripple spreading outward.
**Effect:** Outward scale pulse (1.0→1.06→1.0) in first 16 frames, then gentle drift.

### `rattle`
**Use when:** Sustained mechanical tension — engine running, earthquake, someone being electrocuted throughout the panel.
**Effect:** Constant low-level shake throughout the entire clip.

### `slide_top`
**Use when:** Something descends from above — a ship landing, a figure looming, a ceiling caving in.
**Effect:** Panel slides in from the top.

### `tilt_in`
**Use when:** A panel that feels "thrown" into place — energetic, comic-book layout feel, kinetic transitions.
**Effect:** Starts slightly rotated (4°), straightens over first 25% of clip.

### `spin_in`
**Use when:** Chaotic, disorienting moment — loss of control, a character spinning, madness.
**Effect:** Starts rotated 15°, snaps to straight quickly. Very dramatic.

### `breathe`
**Use when:** A quiet, reflective pause — aftermath, contemplation, grief.
**Effect:** One gentle zoom oscillation over the clip — the scene softly pulses.

### `creep`
**Use when:** Slow dread building — approaching danger, something wrong in a still scene.
**Effect:** Extremely slow push in (1.0→1.03) over the full clip. Almost imperceptible but unsettling.

## Rules
- **Vary the animations**: avoid assigning the same type to 3+ consecutive panels.
- If the panel has strong action keywords → `burst`.
- If it's the first panel on the page → `zoom_out` or `ken_burns`.
- If it's a reaction/dialogue panel after action → `slide_right` or `ken_burns`.
- `burst` should never appear on two consecutive panels.

## Event Types

You may also assign timed visual events to specific words in the narration. Events fire at the exact timestamp of the word and layer on top of the panel animation.

| Event | Effect | Use when |
|---|---|---|
| `tremble` | Rapid shake fading out | Fear, instability, supernatural dread |
| `flash` | White flash burns in then fades | Gunshot, explosion, lightning strike |
| `shockwave` | Outward scale pulse 1.0→1.06→1.0 | Impact ripple, crash aftermath |
| `heartbeat` | Rhythmic pulsing zoom | Tense standoff, waiting, suspense |
| `rattle` | Constant low-level shake | Engine, electricity, sustained vibration |

Events are optional. Only add them when the narration has a specific impactful word at a known timestamp. Prefer 1–3 events per panel maximum.

## Input Format
```json
{
  "comic_name": "string",
  "page_number": 2,
  "page_size": {"width": 1920, "height": 2980},
  "panels": [
    {
      "panel_index": 0,
      "narration_text": "string",
      "scene_caption": "string",
      "duration_seconds": 3.5,
      "bubble_bbox": [x1, y1, x2, y2],
      "words": [
        {"word": "She", "start": 0.12, "end": 0.28},
        {"word": "fired", "start": 0.30, "end": 0.55}
      ]
    }
  ]
}
```

`words` contains word-level timestamps from speech recognition. Use `start` as `startSeconds` when specifying events.

## Transition Types

`transitionIn` controls how this panel enters from the previous one (ignored for the first panel).

| Transition | Effect | Use when |
|---|---|---|
| `none` | Hard cut | After impact animations — burst, snap, flash |
| `fade` | Cross-dissolve | Calm, emotional, time-skip moments |
| `slide` | Panel slides over previous | Sequential narrative flow |
| `wipe` | Edge wipe reveal | Scene change, location shift |
| `flip` | 3D card flip | Dramatic reveal, plot twist |
| `toss` | Previous spins away, new rises up | High-energy transition, chaotic moment |

## Output Format (JSON)
```json
{
  "panels": [
    {
      "panel_index": 0,
      "animation": "zoom_out",
      "transitionIn": "none",
      "reasoning": "one sentence",
      "events": []
    },
    {
      "panel_index": 1,
      "animation": "burst",
      "transitionIn": "toss",
      "reasoning": "one sentence",
      "events": [
        {"type": "flash", "startSeconds": 0.30, "durationSeconds": 0.4},
        {"type": "shockwave", "startSeconds": 0.55, "durationSeconds": 0.7}
      ]
    }
  ]
}
```

## Notes
- Return exactly one entry per panel, in order.
- `panel_index` must match the input order exactly.
- `transitionIn` and `events` are required in every panel entry — use `"none"` and `[]` respectively if not applicable.
- First panel must always have `transitionIn: "none"`.
- Use only these animation names: `burst`, `snap`, `slam_left`, `slam_right`, `whip_left`, `whip_right`, `punch_in`, `recoil`, `shockwave`, `flash`, `heartbeat`, `tremble`, `rattle`, `slide_left`, `slide_right`, `slide_bottom`, `slide_top`, `tilt_in`, `spin_in`, `ken_burns`, `zoom_out`, `zoom_in`, `pan_up`, `pan_down`, `breathe`, `creep`, `fade_in`.
- Use only these transition names: `none`, `fade`, `slide`, `wipe`, `flip`, `toss`.
- Use only these event types: `tremble`, `flash`, `shockwave`, `heartbeat`, `rattle`.
