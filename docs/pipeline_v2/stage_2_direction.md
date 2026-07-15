# Pipeline v2 — Stage 2: Direction

Stage 2 is the **director**: a text-only LLM pass (Claude) that reads the
Stage 1 assets and decides *how the video tells the story* — which panels
to show or skip, what the narration says, which animation and transition
each shot gets, and the pacing. It emits schema-validated shot lists into
`direction/`, which are the only input Stage 3 (production) consumes.

Design goals:

- **Zero vision cost.** All image understanding happened in Stage 1;
  direction is pure text reasoning over JSON and can be re-run endlessly.
- **Creative decisions live here, and only here.** Stage 1 is objective
  description; Stage 3 is mechanical execution. Every judgment call —
  skip/keep, narration voice, animation choice — is the director's.
- **Everything validated before render.** A direction file with a dangling
  panel ref, an unknown animation, or an off-budget word count never
  reaches Stage 3.

**Gate:** Stage 2 only runs when `book.json.analysis.completed_at` is set
(Stage 1.6 passed). Stage 3 only runs on direction files with
`validated: true` (Stage 2.3 passed).

---

## Sub-stages

| Sub-stage | Name              | Kind                        | Done-marker                          |
|-----------|-------------------|-----------------------------|--------------------------------------|
| 2.1       | Direct longform   | text LLM (Claude)           | `direction/longform.json` exists     |
| 2.2       | Direct shorts     | text LLM (Claude)           | `direction/shorts.json` exists       |
| 2.3       | Validate & repair | deterministic + LLM repair  | `validated: true` in each file       |

```
assets/ ──2.1─▶ longform.json ──┐
        ──2.2─▶ shorts.json  ───┴──2.3─▶ validate ⇄ repair (≤2) ──▶ validated: true
```

2.1 and 2.2 are **separate passes, not one call**: the two formats have
opposed philosophies (longform covers the whole story with even pacing;
shorts is hook-first and ruthless about cutting, hard 60–120s), and one
prompt doing both does both worse. They share the same input context, so
the second call is cache-friendly.

**Shorts count:** one per book (`max_shorts` config knob, default 1 — a
book has one best hook; more shorts cannibalize each other and spoil the
longform). If ever raised, files become `shorts_01.json`, `shorts_02.json`;
nothing else changes.

**Model:** `direction_model` config value, default Sonnet — direction is a
long-context text reasoning task; switching models never invalidates
existing direction files by itself (re-direction is always explicit).

---

## Shot-list schema (`direction/longform.json`, `direction/shorts.json`)

```jsonc
{
  "schema_version": 1,
  "target": "longform",                  // longform | shorts
  "style_version": "v1",                 // re-direct knob, like Stage 1's prompt_version
  "direction_model": "claude-sonnet-…",  // provenance
  "validated": true,                     // set only by 2.3
  "meta": {
    "youtube_title": "…",
    "description": "…",
    "twitter_post": "…",
    "thumbnail": { "page": 1, "panel": 1 }
  },
  "music": {
    "mood": "tense, building orchestral" // ONE mood per video — matches the
  },                                     //   one-track render path; a future
                                         //   schema_version may add changes[]
  "shots": [
    {
      "id": 1,                           // sequential, 1-based
      "source": { "page": 3, "panel": 2 },
      // other source kinds:
      //   { "page": 5, "kind": "full_page" }
      //   { "page": 3, "kind": "pan", "from_panel": 2, "to_panel": 3 }  ← uses Stage 1 bboxes
      "narration": "Logan steps onto the deck — and he's not alone.",
      "animation": "punch_in",           // from the allowed vocabulary ONLY
      "animation_target": "focal_point", // focal_point | whole — Stage 3 resolves via page.json
      "transition_in": "fade",           // none | fade | toss | …
      "silent_seconds": null,            // only for narration:"" beat shots (else null)
      "events": [
        { "type": "shockwave", "at_fraction": 0.4 }
      ],
      "why": "reveal beat, intensity 5 — hard cut into the claws"
      // director's rationale: kept for debugging bad pacing, stripped before render
    }
  ]
}
```

Key properties:

- **Shots reference `page`/`panel` ids, never file paths.** Stage 3
  resolves ids → images, bboxes, focal points, text regions via
  `page.json`. Direction files stay portable and validatable.
- **No durations in the shot list.** Shot duration comes from TTS audio
  length in Stage 3. The director controls pacing through narration
  *length* (word budget, below) and explicit `silent_seconds` beat shots.
- **Animation vocabulary is a schema enum** — the existing Remotion set
  (`burst`, `punch_in`, `slam_left`, `slam_right`, `snap`, `ken_burns`,
  `breathe`, `three_part_build_up`, `pan_up`, `pan_down`, `zoom_in`,
  `zoom_out`, `tilt_in`, `slide_bottom`, …). The prompt documents *when*
  each is appropriate (reveal → `punch_in`, fight → `slam_*`, calm →
  `ken_burns`, ending → `zoom_out`). This replaces the old
  `random.choice(_MID_ANIMS)`.
- **`why` on every shot** costs a few tokens and makes bad output
  debuggable — read the director's reasoning instead of guessing.

---

## Prompt contract (what the director is told)

**Input context:** `book.json` (story, beats, page index), reconciled
`characters.json`, every `page.json` in reading order. A 22-page book is
roughly 30–60k tokens — one call, no chunking. (Thick 100+ page volumes
would need a chunked strategy; deferred until one actually shows up.)

**Rules, both targets:**

1. **Word budget.** Narration is timed at ~2.5 words/second. Longform
   target length comes from category config; shorts is a **hard 60–120s
   window** (~150–300 narration words total). The validator enforces this,
   so the prompt states it explicitly with the running-total expectation.
2. **Character naming.** Narration may name a character only if their
   roster entry has `named_in_story: true`, is ComicInfo-sourced, or has a
   (1.4-reconciled) `inferred_identity` — inferred identities are allowed
   by default (famous cameos get named), but roster-grounded names win
   when both exist. Everyone else is "a figure", "the guard".
3. **Never narrate `kind: "sfx"` dialogue.** (Stage 1 classified it; this
   rule replaces the old `remove_sound_effect` sanitise step.)
4. **Content warnings** on a page mean: don't linger — no slow pans, no
   extended holds on flagged panels.
5. **Skippable hints are read through `skip_overrides`** (a hint may have
   been overturned with whole-book context in 1.5).
6. **`reading_order_suspect` pages** get conservative treatment: full-page
   shots or single-panel shots, no cross-panel pans.
7. **Intro/outro are placed, not designed.** Welcome/finish phrases and
   the title-card intro remain category templates; the director decides
   which shot sits under them, nothing more. Brand stays consistent
   across videos.

**Longform additionally:**

- May skip panels *and whole pages* (ads, credits, recap pages are
  expected skips; story pages too when they add nothing) — but **must
  touch every beat in `book.json.story.beats`**. It can't skip its way
  past the plot.
- Spreads (`is_spread: true`) deserve their moment — typically a slow pan.

**Shorts additionally:**

- Structure: **hook → escalation → cliffhanger.** Nothing else. Open on
  intensity ≥ 4 with no transition; end on the question that drives
  viewers to the longform; never resolve it.
- Ruthless skipping is the default; coverage rules do not apply.

---

## Sub-stage 2.3 — Validate & repair

| | |
|---|---|
| **Input**  | `direction/*.json` with `validated` absent/false |
| **Output** | `validated: true`, or a hard-fail report |
| **Uses**   | deterministic checks; failed checks go back to the director (≤ 2 repair calls) |

Deterministic checklist:

- every `source` page/panel ref resolves in `assets/` and the page has
  `status = analyzed`; pan shots reference two panels on the *same* page
- `animation`, `transition_in`, `events[].type` all from their enums;
  `animation_target` valid for the source kind
- word budget: total narration words within target ±15% (shorts: inside
  the 60–120s window); `silent_seconds` only on empty-narration shots
- first/last shot rules (shorts opens intensity ≥ 4, `transition_in:
  "none"`; last shot uses an ending-class animation)
- narration names: every capitalized name-like token matches a roster
  name, alias, or reconciled `inferred_identity` — anything from *nowhere*
  is a violation
- narration is TTS-safe: no markup, no bracketed stage directions, no
  sfx-looking onomatopoeia
- `meta` complete; thumbnail ref resolves; shot ids sequential from 1

On violation: the full error list goes back to the director as a repair
call ("fix these, change nothing else"), **max 2 retries**, then hard-fail
with the report — a book failing validation never silently ships a broken
video. `validated: true` is the gate Stage 3 checks.

---

## Idempotency & re-run matrix

| To redo…                     | Do this                                    | What re-runs |
|------------------------------|--------------------------------------------|--------------|
| longform direction           | delete `direction/longform.json`           | 2.1, 2.3     |
| shorts direction             | delete `direction/shorts.json`             | 2.2, 2.3     |
| both, new style              | bump `style_version` in config             | 2.1–2.3      |
| validation only              | set `validated: false` in the file         | 2.3          |

Stage 1 invalidation cascades here: any Stage 1 re-run that clears
`completed_at` also clears `validated` on all direction files (the assets
they reference may have changed).

---

## What Stage 2 explicitly does NOT do

- No image analysis (Stage 1 — the director never sees pixels).
- No TTS, STT, rendering, music generation, or file resolution (Stage 3).
- No identity adjudication — `characters.json` is consumed as fact; if an
  identity looks wrong, fix it by re-running 1.4, not in direction.
- No per-shot music changes (single mood per video; future schema_version).

---

## Stage 3 preview (to be designed next)

**Production**: mechanical execution of a validated direction file — TTS
per shot, STT word timings, resolve page/panel ids to images + bboxes +
focal points, compile the Remotion manifest, render, music, loudness,
optimize. Mostly existing code (`create_comic_panel_video.py`,
`combineVideo`, `addMusic`, …) re-plumbed to consume `direction/*.json`.
