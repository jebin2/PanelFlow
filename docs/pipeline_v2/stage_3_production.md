# Pipeline v2 — Stage 3: Production

Stage 3 is the **factory**: it takes a validated direction file and produces
the video it describes. Nothing here decides anything — every judgment call was
made upstream. If something in Stage 3 seems to need a decision, it belongs in
Stage 2, not here.

What *does* live here is arithmetic the upstream stages cannot do:

- a shot's duration is however long the voice takes to say its line, which
  nobody knows until TTS has run;
- a focal point on a *panel* has to become an origin on the *frame*, which
  needs the letterboxing;
- a `pan` between two panels has to become a crop plus a travelling camera.

**Gate:** Stage 3 only runs on a direction file with `validated: true`
(Stage 2.3 passed). It refuses anything else.

---

## Sub-stages

| Sub-stage | Name    | Kind                    | Cached by                                    |
|-----------|---------|-------------------------|----------------------------------------------|
| 3.1       | voice   | TTS + STT (network)     | audio file per shot, keyed by shot **and text** |
| 3.2       | compile | pure arithmetic          | nothing — recomputed every run, it is free   |
| 3.3       | render  | Remotion (subprocess)    | video newer than its direction file          |
| 3.4       | publish | image + JSON             | nothing; `PUBLISHED` ends the book's life    |

```
direction/<target>.json ──3.1─▶ audio + durations + word timings
                         ──3.2─▶ render/<target>/manifest.json
                         ──3.3─▶ render/<target>/<target>.mp4
                         ──3.4─▶ progress.json + thumbnail.jpg   (both targets)
```

3.1–3.3 run per target; **3.4 is book-level** — a handoff names both videos, so
`--output shorts` skips it and says so.

Both targets (`longform` 1920×1080, `shorts` 1080×1920) run the same three
modules; the only differences are the frame size and the direction file. The
vertical frame is also what makes the renderer show its title card and progress
bar — `Root.tsx` gates both on `height > width`, so shorts get them for free.

Everything lands under `render/<target>/` inside the comic folder
(git-ignored): `audio/`, `images/` (pan crops), `manifest.json`, the video.

## 3.1 voice — narration becomes audio, duration, word timings

This runs *before* the manifest is compiled because it is what decides the
timings. The director wrote `at_fraction: 0.4` — four tenths of the way through
a shot whose length nobody knew yet. Only once the audio exists is there a
second number to turn that fraction into.

Per speaking shot: TTS → `trim_silence` → `speed_up_audio` → measure. Silent
shots (`narration: ""`) get their `silent_seconds` and no audio file — a
direction with 10 shots and one silent closer legitimately produces 9 wavs.

**The cache is keyed by what is spoken** — `shot_003_<md5-of-narration>.wav` —
not just by position. A re-directed or repaired shot 3 must not find the *old*
shot 3's audio and play the old script over the new cut; new words mean a new
file, and the old one stays behind as a dead cache entry (bytes, nothing else).
TTS is the slowest thing in the pipeline, so a rerun after a crash re-speaks
only what never finished.

**Word timings** come from STT (`<audio>.json` beside the wav is both cache and
result), but the *words* shown on screen are the script's: STT only exists here
to say *when* each word lands. When the word counts pair up one to one, the
subtitle prints the narration verbatim on STT's clock; when they don't, the
alignment is unknowable and what was heard is better than a guess. STT failing
entirely just means no kinetic subtitles for that shot — the video still plays.

## 3.2 compile — direction + voice tracks become a manifest

One manifest per target for the whole book (v1's per-page `pageNumber` render
loop is gone — nothing ever read the field back). All the geometry lives in
`stage3/geometry.py`, pure functions with no I/O, pinned by
`tests/test_geometry.py` — a wrong answer there does not raise, it quietly
zooms at the wrong spot, and nobody notices until they watch the video.

**Focal points.** Stage 1 recorded `focal_point` as fractions of the *panel*;
the renderer letterboxes the panel into the frame (`objectFit: contain`), so a
point 65% across the panel is somewhere else entirely in the frame.
`to_frame_fraction` resolves that, and the kit receives frame fractions
(`focalOrigin`) it can apply without knowing any of this.

**Zoom ceilings.** `text_regions` (page pixels, from Stage 1's OCR) are rebased
onto the panel and turned into one number: the largest zoom, about this origin,
that keeps every region on screen (`zoomLimit`). The kit clamps whatever any
animation reaches for. Python never needs per-animation zoom constants; the kit
never needs lettering geometry.

**Pans are true travel.** A `pan` shot crops both panels out of the page as one
image, then computes a camera: zoom in far enough to *fit* one panel (never
fill — `min` of the two axes), and travel so each end of the move lands its
panel dead centre. Because scaling about the frame centre never moves the
centre, travel and zoom are independent. Deliberately **no zoom ceiling here**:
the fit-zoom keeps the framed panel — lettering included — whole by
construction, and clamping on *both* panels' text at once always answers "do
not zoom", which is exactly not a pan.

**Transition padding.** The renderer's `TransitionSeries` overlaps two shots
only where a transition actually sits between them, and the overlap eats the
outgoing shot's last 18 frames. So a shot whose *next* shot transitions in is
padded by 0.75s or its narration is cut mid-word — and a shot before a hard cut
is not padded at all, or the pad plays as 0.75s of frozen silence. (The first
shorts render padded everything and had a gap after nearly every shot.)

**Events** are punctuation: `at_fraction` × the voiced duration, clamped so a
beat at the very end still gets its 0.6s on screen.

## 3.3 render — the manifest becomes a video

`npx remotion render ComicVideo --props manifest.json` in `remotion-comic/`,
then loudness normalization. Two mechanics worth knowing:

- **Props envelope.** `Root.tsx` takes the manifest as a *prop*, so the file on
  disk is `{"manifest": {...}}` — hand Remotion the bare manifest and
  `calculateMetadata` reads `undefined`.
- **Assets by symlink.** Remotion's `staticFile()` only reaches inside its own
  `public/`. Rather than copy a book's worth of artwork,
  `public/render_assets` is symlinked at the comic folder for the length of
  the render and removed after — two books can never leave each other's assets
  around, and the code refuses to delete a `render_assets` that is not a
  symlink (it did not create that).

**Done-marker:** the video exists **and is newer than its direction file**.
Existence alone would let a re-directed book report "already rendered" and
quietly ship last cut's video. `--only 3.3` bypasses the marker for a forced
re-render.

## 3.4 publish — the handoff, and the end of the book's life

Writes `progress.json` at the comic folder root and renders `thumbnail.jpg`.
That file is the entire contract with **pub_yt_x**, which needs no folder
convention: it `os.walk`s whatever root you give it looking for that filename.

```
pub_yt_x /home/jebin/git/PanelFlow      # or any root above the comic folders
```

**Paths are absolute, deliberately.** pub_yt_x resolves relative paths against
whichever scan root it was invoked with, and 3.4 cannot know that root. Its
`to_abs` returns an absolute path untouched, so absolute is the one answer
correct for every root.

**One title per video.** The longform's `meta` fills `YOUTUBE_TITLE` /
`YT_DESCRIPTION`; the short's fills `SHORTS_YOUTUBE_TITLE` /
`SHORTS_YT_DESCRIPTION`. Stock pub_yt_x read a single title and put it on both
uploads, which threw away the hook-first title 2.2 exists to write — so it now
takes a `key_prefix` and falls back to the unprefixed keys, leaving every older
progress.json working unchanged.

**The thumbnail is the panel the director chose** (`meta.thumbnail`, validated
by 2.3), cover-cropped to 1920×1080 around the panel's `focal_point` — v1 took
the first panel of the book and cropped from the top. Cover, not contain: a
thumbnail may lose a corner but never gains a bar, and the focal point decides
what survives.

**The schedule lives in progress.json.** The next free Wed/Fri/Sun slot at
03:30 or 14:30 UTC, found by reading the *sibling* folders' progress files —
nothing else knows what is queued. A slot already booked and still ahead is
kept, so re-running 3.4 after a re-render cannot move a video someone is
expecting on Sunday.

**This file is a tombstone, and the folder is disposable.** Once the upload
succeeds, pub_yt_x deletes everything beside progress.json — cbz, assets,
direction, render, all of it — and sets `PUBLISHED`. That is the intended
lifecycle: a book on the channel is done, and the disk comes back.
`Assets.published()` is what stops the CLI from walking into the wreckage and
trying to re-extract from a cbz that is gone; it is checked before Stage 1, not
inside it.

## The renderer: two layers, three copies

| layer | where | owns |
|---|---|---|
| `remotion-animation-kit` | own repo, shared with ReelForge | *capability*: animations, transitions, `zoomLimit`/`originX`/`originY`, TitleCard, subtitles |
| `remotion-comic` | plain folder in PanelFlow | *domain*: `PanelData`/`ComicManifest` schema, what to pass the kit |

remotion-comic imports from the kit; it never copies or overrides it. The kit
stays unaware of comics, panels, or lettering — it takes frame fractions and a
zoom cap and asks no questions.

**The npm trap:** the kit is a git dependency, and the lockfile pins it **by
commit hash**. Pushing a kit change and running `npm install` silently keeps
the old commit — `npm update remotion-animation-kit` is what moves the pin,
and the updated `package-lock.json` must be committed. Forgetting this fails
with no error: everything builds, renders, and quietly ignores the new
behaviour. (This happened; the first focal-point render would have shipped
with `transformOrigin: "center center"`.)

## What Stage 3 does not do

- **No music.** Stage 2 emits `music.mood`, but v1's `_add_bg_music` was
  already a no-op copy and the field has no consumer. Kept in the direction
  schema so directions don't churn when music becomes real.
- **No LLM calls.** `--model` means nothing here; every judgment was upstream.
- **No per-shot creative fallbacks.** An unknown source kind or missing panel
  is a hard error — 2.3 exists so that never reaches this stage.

**Cost, measured on the 19-page book:** 3.1 spoke 9 shorts shots in ~14 min
(TTS dominates everything); 3.2 is instant; 3.3 rendered the 47.5s short in
~1 min. Reruns with warm audio go straight to render.
