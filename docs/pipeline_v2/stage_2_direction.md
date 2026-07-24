# Pipeline v2 — Stage 2: Direction

Stage 2 is the **director**: a text-only LLM pass that reads the Stage 1 assets
and decides *how the video tells the story* — which panels to show or skip, what
the narration says, which animation and transition each shot gets, and the
pacing. It emits schema-validated shot lists into `direction/`, which are the
only input Stage 3 (production) consumes.

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

| Sub-stage | Name              | Kind                        | Done-marker                                     |
|-----------|-------------------|-----------------------------|-------------------------------------------------|
| 2.1       | Direct longform   | text LLM                    | `longform.json` has shots at the current `style_version` |
| 2.2       | Direct shorts     | text LLM                    | `shorts.json` has shots at the current `style_version`   |
| 2.3       | Validate & repair | checks + LLM repair         | `validated: true` in each file                  |

```
assets/ ──2.1─▶ longform.json ──┐
        ──2.2─▶ shorts.json  ───┴──2.3─▶ validate ⇄ repair (≤2) ──▶ validated: true
```

2.1 and 2.2 are **separate calls, not one call answering twice**: the two
formats have opposed philosophies (longform covers the whole story at an even
pace; shorts is hook-first and ruthless about cutting, ≤120s), and one
prompt doing both does both worse.

They are **one module**, though — `stage2/direct.py`, taking a target. The
philosophies live entirely in the system prompt (`direct_longform.md`,
`direct_shorts.md`); both read the identical book, so nothing in the code needs
to know which is running. Two modules would have differed by a string.

**Shorts count:** one per book. A book has one best hook; more shorts
cannibalize each other and spoil the longform. If that ever changes, files
become `shorts_01.json`, `shorts_02.json` and nothing else does.

**Model: TTT/opencode**, like every other text call in the pipeline — there is
no Claude API here. `llm.ask_json` routes on the absence of an image, so the
director gets the text provider automatically; `PANELFLOW_TEXT_PROVIDER`
overrides it, and `--model` overrides per run. Switching models never
invalidates existing direction files by itself (re-direction is always
explicit).

**Cost, measured on a 19-page book:** 2.1 took 299s, 2.2 took 507s, 2.3 with a
repair ~200s and without one 13s. Input context is ~6k tokens for the whole
book — one call, no chunking. (A thick 100+ page volume might change that;
deferred until one shows up.)

---

## Shot-list schema (`direction/longform.json`, `direction/shorts.json`)

```jsonc
{
  "schema_version": 1,
  "target": "longform",                  // longform | shorts
  "style_version": "v1",                 // re-direct knob, like Stage 1's prompt_version
  "direction_model": "default",          // provenance; "default" = TTT's own (opencode)
  "validated": true,                     // set only by 2.3 — Stage 3's gate
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
- **The shot vocabulary is not ours.** Animations, transitions and events are
  whatever the renderer can actually play, and that is declared in TypeScript:

  | vocabulary | source of truth |
  |---|---|
  | animations | `remotion-animation-kit/src/types.ts` → `AnimationName` (27 today) |
  | PanelFlow's own two | `remotion-comic/src/types.ts` → `PanelAnimation` (`assemble`, `three_part_build_up`) |
  | transitions | `remotion-animation-kit/src/types.ts` → `TransitionName` |
  | events | `remotion-comic/src/types.ts` → `PanelEvent.type` |

  `stage2/schemas.py` transcribes those unions into Python, and a transcription
  rots the moment the kit gains a move — so `tests/test_vocabulary.py` reads
  the real `.ts` files and fails when they disagree, naming what drifted. The
  kit is a github dependency and an actively improving repo; without that test,
  a new animation would silently never reach the director, and a removed one
  would validate here and die at render.

  **When the kit changes, update `schemas.py` and both director prompts.** The
  prompts group the names and say *when* each is appropriate (reveal →
  `punch_in`, fight → `slam_*`, calm → `ken_burns`, ending → `zoom_out`); that
  judgement is hand-written and cannot be generated from a type. The test
  catches the enum drifting, not the guidance.

  Note `shockwave`, `flash`, `heartbeat`, `tremble` and `rattle` are both
  animations *and* events, and are not the same thing either way: an animation
  is the shot's movement, an event fires *during* it.

  All of this replaces the old `random.choice(_MID_ANIMS)`.
- **`why` on every shot** costs a few tokens and makes bad output
  debuggable — read the director's reasoning instead of guessing.

---

## Prompt contract (what the director is told)

**Input context:** the book's title and synopsis, its beats, the roster, and
every page in reading order — rendered by `stage2/digest.py`, not handed over as
raw JSON. Measured at **~6k tokens** for a 19-page book: one call, no chunking.

The digest is a different view from Stage 1's, and deliberately:

- **`skip_overrides` are resolved in code.** 1.3 marks a panel skippable seeing
  only the pages before it; 1.5 overturns that with the whole book. The director
  is handed the answer and the reason, rather than two lists to cross-reference
  — and a director that missed the override would cut the setup for the ending.
- **Appearance is withheld, except where it is the only thing to say.** The
  director never sees pixels, so a character's `visual` is noise — unless the
  book never names them, in which case it is what the narration must reach for
  instead of a name.
- **Spreads, suspect ordering and content warnings are flagged inline**, since
  each one constrains what the director may do with that page.

**Rules, both targets:**

1. **Word budget.** Narration is timed at ~3.5 words/second — post-trim,
   post-speedup speech as 3.1 actually produces it, measured on a real render.
   **Longform is unbudgeted** — coverage is what matters, and the story decides
   its length; a book that earns four minutes must not be stretched to eight.
   **Shorts has a hard 120s ceiling** (~420 narration words total), enforced by
   the validator, so its prompt states it explicitly. Only the ceiling is hard:
   a short that runs 47s is a shorter short, not a defect — the platform
   punishes long, never brief.
2. **Character naming.** Decided in the digest, not the prompt: each roster line
   either says `say "X"` (with where the book grounded it) or `NOT named in this
   book — describe them`. Roster-grounded names win over a 1.4-reconciled
   `inferred_identity` when both exist. Everyone else is "a figure", "the
   guard".
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
| **Uses**   | deterministic checks + one model call for naming; failures go back to the director (≤ 2 repair calls) |

Facts, checked in code:

- every `source` page/panel ref resolves in `assets/` and the page has
  `status = analyzed`; pan shots reference two panels on the *same* page, and
  never on a page whose ordering is suspect
- `animation`, `transition_in`, `events[].type` all from their enums (see the
  vocabulary table above); `at_fraction` within 0..1
- `silent_seconds` only on empty-narration shots, and always on them — a shot's
  length otherwise comes from its voice track
- shot 1 opens on `transition_in: "none"`
- **longform:** every beat in `book.json.story.beats` has at least one shot. It
  may skip pages; it may not skip the plot. There is no length check.
- **shorts:** under the 120s ceiling; opens on intensity ≥ 4; ends on an
  ending-class animation
- narration is TTS-safe: no markup, no bracketed stage directions
- `meta` complete; thumbnail ref resolves; shot ids sequential from 1

**Naming is asked, not ruled on** — the one check here that is not a fact. The
whole narration goes to the text model with the roster: which names are sayable,
and which characters must be described instead.

It was a regex first, and that was worse than nothing. It passed "Wolverine
catches it." — narration puts the name first, and sentence-initial capitals were
exempt — while flagging "Beneath", "Nothing" and "They" in real narration. Its
false positives would have driven repairs, and a repair that fires on good work
damages it. No rule can do this job: the question is whether a capitalised word
is a person's name, and a book's own vocabulary cannot separate "Gambit" from
"Beneath". "Doctor Strange" is the proof — both words are in *Strange Scales*'
own title, so no grounding rule could flag it, and no prefilter would even
nominate it for asking. That is why the narration goes over unfiltered:
filtering candidates with a rule decides the very thing being asked.

A failure to reach the checker is **fatal, not skipped**. Swallowing it would
ship the video the check exists to stop.

On violation: the full error list goes back to the director as a repair call
("fix these, change nothing else"), **max 2 retries**, then hard-fail with the
report — a book failing validation never silently ships a broken video.
`validated: true` is the gate Stage 3 checks.

**A repair must repair, not delete.** The first real run proved why this needs
saying: told an event had the wrong key, the model dropped the event entirely
rather than fixing the key, discarding a `shockwave` the director had chosen for
the moment a notebook slams shut. The prompt now says deleting is not fixing,
whatever the fault is in — the only exception being a shot whose source page or
panel does not exist, which cannot be repaired.

---

## Idempotency & re-run matrix

| To redo…                     | Do this                                    | What re-runs |
|------------------------------|--------------------------------------------|--------------|
| longform direction           | delete `direction/longform.json`           | 2.1, 2.3     |
| shorts direction             | delete `direction/shorts.json`             | 2.2, 2.3     |
| both, new style              | bump `direct.STYLE_VERSION`                | 2.1–2.3      |
| validation only              | set `validated: false` in the file         | 2.3          |

As in Stage 1, **the version bump is manual and is the step that gets
forgotten**: a direction file records the `style_version` it was written under,
and `is_done` compares it to the constant. Rewrite a director prompt without
bumping, and the existing file is simply kept.

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

It is the first consumer of two Stage 1 fields nothing has read yet, so both are
unproven in anger: `focal_point` (the zoom target, relative to its panel) and
`text_regions` (the boxes a crop must not cut through). Expect to find out there
whether they are right.
