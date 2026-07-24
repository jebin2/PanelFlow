# Pipeline v2 — Stage 1: Asset Preparation

Stage 1 turns a raw CBZ into a fully cached, structured, on-disk dataset that
later stages consume. It is **deterministic + vision-analysis only** — no
creative decisions, no narration writing, no video work. Everything here is
objective description of what is on the page.

Stage 1 is split into six small sub-stages, each with a strict contract
(input → output → done-marker), each independently runnable and re-runnable:

| Sub-stage | Name                  | Kind             | Done-marker                          |
|-----------|-----------------------|------------------|--------------------------------------|
| 1.1       | Extract               | deterministic    | every `page.json.status ≥ extracted` |
| 1.2       | Split                 | deterministic/ML | every `page.json.status ≥ split`     |
| 1.3       | Analyze               | vision LLM       | every `page.json.status = analyzed`  |
| 1.4       | Reconcile characters  | text LLM         | `characters.json.reconciled = true`  |
| 1.5       | Synthesize story      | text LLM         | `book.json.story` written            |
| 1.6       | Validate              | deterministic    | `book.json.analysis.completed_at`    |

A runner executes them in order, skipping any sub-stage whose done-marker is
already satisfied. Each sub-stage is also exposed individually so a single
step can be re-run or debugged in isolation without touching the others:

```bash
python -m panelflow.cli "<comic_folder>"              # whole of Stage 1
python -m panelflow.cli "<comic_folder>" --only 1.3   # one sub-stage
python -m panelflow.cli "<comic_folder>" --model X    # override the LLM
```

Code lives in `panelflow/` (`stage1/` = one module per sub-stage,
`paths.py` = the `Assets` accessor, `llm.py` = the only place that talks to a
model, `prompts/` = prompt text). Tests: `tests/`, runnable with no API
key or project venv (`python -m pytest tests`).

Design goals:

- **Run once, cache forever.** Vision calls are the expensive part; the
  director (Stage 2) can be re-run endlessly against these assets for free.
- **Objective, not creative.** Stage 1 records *what is in the image*.
  Voice, pacing, narration, skipping, and animation choices belong to Stage 2.
- **Idempotent & resumable.** Every step checks a `status` field and skips
  finished work. A crashed run resumes exactly where it died.
- **No backward compatibility.** Comics already in flight finish on the old
  pipeline; only new CBZs use this structure.

---

## Folder layout

```
<comic_folder>/                        # e.g. content/comic/X-Men United 001 (2026)/
  X-Men United 001 (2026).cbz          # original, never modified
  assets/                              # ← everything Stage 1 produces
    book.json                          # index + book-level analysis (written last)
    characters.json                    # grounded character registry (see below)
    pages/
      0001/
        page.jpg                       # extracted page image, ORIGINAL dimensions
        page.json                      # everything known about this page + its panels
        panels/
          panel_01.jpg                 # crops, clean names, reading order,
          panel_02.jpg                 #   ORIGINAL dimensions (never resized —
          ...                          #   Remotion/ken-burns wants max pixels)
      0002/
        ...
  direction/                           # Stage 2 output (longform.json, shorts.json)
  build/                               # Stage 3 workdir (tts, stt, intermediate renders)
  output/                              # final videos + thumbnail
```

Rules:

- Page dirs are zero-padded reading order (`0001`, `0002`, …), derived from
  the sorted CBZ member names.
- Panel images use clean sequential names in reading order. Bounding boxes
  live in `page.json`, **not** in filenames (the extractor encodes bboxes in
  filenames like `panel_1_(1006, 176, 1757, 1085).jpg` — Stage 1 parses these
  into JSON and renames the files).
- Panel analysis lives inside `page.json`, not one JSON per panel: the
  analysis comes from a single vision call per page, so one atomic write per
  page means a crash can never leave half-analyzed panels, and the director
  reads the whole book at once anyway. Panel *images* are separate files.

---

## `page.json` schema

```jsonc
{
  "schema_version": 1,
  "page_index": 3,                     // 1-based, reading order
  "image": "page.jpg",
  "width": 1988,
  "height": 3056,
  "page_type": "story",                // cover | story | splash | credits | ad | recap
  "is_spread": false,                  // landscape double-page spread (detected in 1.1)
  "status": "analyzed",                // extracted → split → analyzed
  "extraction": {
    "tool": "comic-panel-extractor",
    "panel_count": 5
  },
  "ocr_lines": [                       // 1.2: every line OCR found, with its box.
    { "text": "BELOW -THESANGTOMSANGTORUM",  //   Text is kept only so 1.3 can match
      "box": [33, 69, 766, 105] }      //   dialogue to boxes — it is too mangled to use.
  ],
  "analysis": {
    "model": "GeminiUIChat",           // provenance
    "prompt_version": "v2",            // bump → this page gets re-analyzed
    "scene_summary": "Logan confronts Creed on the helicarrier deck as a storm builds.",
    "mood": "tense",
    "continuity_note": "Follows directly from the ambush on page 2.",
    "reading_order_suspect": false,    // vision model doubts the extractor's panel ordering
    "content_warnings": [],            // e.g. "graphic-violence" | "blood" | "gore" — for monetization decisions
    "unassigned_dialogue": [           // captions/titles in gutters or spanning panels
      { "speaker": "", "text": "MEANWHILE, IN GENOSHA…", "kind": "caption",
        "region": [33, 17, 766, 105] } //   located like panel dialogue (below)
    ]
    // NOTE: no page-level character list — characters are per-panel refs;
    // the page-level set is derived (union of panel refs), one source of truth.
    // NOTE: no story_beat here — beats need whole-book context and are
    // assigned globally in 1.5 (book.json.story.beats).
  },
  "panels": [
    {
      "id": 1,                         // reading order on the page
      "image": "panels/panel_01.jpg",
      "bbox": [1006, 176, 1757, 1085], // [x1, y1, x2, y2] on page.jpg, pixels
      "text_regions": [                // speech bubbles / captions, page coords, from
        [1050, 200, 1400, 340]         //   OCR in 1.2 — camera must never crop through
      ],                               //   these. 1.3 cannot write this field.
      "focal_point": [0.62, 0.41],     // where the subject is, normalized to the panel —
                                       //   zoom/ken-burns target
      "role": "establishing",          // establishing | action | reaction | dialogue | reveal | transition
      "description": "Wide shot of the helicarrier deck, rain starting, two figures far apart.",
      "characters": [                  // refs into characters.json ONLY — never free-form names
        { "ref": "wolverine", "confidence": "high", "evidence": "claws, yellow-blue suit" },
        { "ref": "guard_1", "confidence": "medium", "evidence": "bald, grey uniform, partial view" }
      ],
      "dialogue": [
        {
          "speaker": "wolverine",      // roster ref, or "" if unknown/off-panel
          "text": "You shouldn't have come back.",
          "kind": "speech",            // speech | thought | caption | sfx
          "region": [1050, 200, 1400, 340]  // where this line is written, matched to
        }                              //   OCR's boxes in 1.3. Absent if unmatched.
      ],
      "intensity": 2,                  // 1 calm … 5 peak action
      "skippable": true                // objective hint: carries no unique story info
    }
  ]
}
```

Field notes:

- **`role`, `intensity`, `skippable`** are the three fields the director acts
  on directly (animation choice, pacing, skip decisions). Everything else is
  context for narration writing.
- **`dialogue` lives per-panel** with a `kind` classifier. SFX are captured
  and classified here, which **replaces the old `remove_sound_effect`
  sanitise step**: the director simply never narrates `kind: "sfx"` entries.
- **`skippable` is a hint, not a decision.** Stage 1 states "this panel
  carries no unique story information"; Stage 2 decides whether to skip it.
- **`bbox` enables full-page camera work.** Because panel positions on the
  page are known, the director can choose "pan across the page from panel 2
  to panel 3" instead of only hard cuts between crops.
- **`text_regions` are camera constraints.** Panel bboxes say where to cut;
  text regions say where the camera must never crop through — a zoom that
  slices a speech bubble in half is the most amateur-looking artifact a
  comic video can have. (This replaces the old hardcoded `bubbleBbox`
  placeholder in the Remotion manifest.)
  **They come from OCR in 1.2, and 1.3 is never asked for one.** The
  extractor's own text detector is disabled upstream (its import is commented
  out in comic-panel-extractor's `main.py`), and the obvious substitute — ask
  the vision model, which is already looking at the page — does not work: asked
  for pixel coordinates it invents them, and a real run returned a text region
  200px below the bottom of an 800x752 page. Models read; they do not measure.
- **`region` on a line of dialogue is the other half of that split.**
  `text_regions` answers "where must a crop not cut", and OCR alone can answer
  it. `region` answers "where is *this line* written", which needs both
  sources: OCR knows where lettering is but mangles what it says
  ("THESANGTOMSANGTORUM"), while the vision model reads it correctly but cannot
  measure. 1.3 matches one to the other by text and the union is computed in
  code — see 1.3.
  Note a panel's `text_regions` and its dialogue's `region` can disagree about
  which panel owns a bubble, and both are right: `dialogue` answers *who says
  this* (the speaker's panel), `text_regions` answers *where the ink is* (the
  box it is drawn in). A bubble floating up out of its speaker's panel lands in
  both, differently.
- **`focal_point` is the camera target.** A punch-in or ken-burns needs to
  know where the subject is — a face, the clash point, the revealed object.
  Without it, animation drifts toward empty sky.
- **`prompt_version`** is the cache-invalidation knob: improve the analysis
  prompt, bump the version, re-run — only the analysis step redoes; extraction
  and splitting stay cached.

---

## `characters.json` schema — grounded character registry

Character identification is the highest-hallucination-risk part of Stage 1
("it looks like Gambit, so I'll say Gambit"). The registry exists so the
model **never answers an open-ended "who is this?"** — it only matches
against a closed set or registers a new entry with a descriptive slug.

```jsonc
{
  "schema_version": 1,
  "seeded_from": "ComicInfo.xml",      // or null when no metadata existed
  "reconciled": true,                  // final reconciliation pass done
  "characters": [
    {
      "id": "wolverine",               // stable slug; panel refs point here
      "name": "Wolverine",
      "aliases": ["Logan"],
      "named_in_story": true,          // name is grounded: appears in dialogue/captions
      "named_by": { "page": 2, "panel": 4 },   // where the grounding occurred (null if from ComicInfo)
      "visual": "short black hair, mutton chops, yellow-blue suit with black mask points",
      "first_seen": { "page": 2, "panel": 3 },
      "reference_images": ["pages/0002/panels/panel_03.jpg"],  // clearest full view
      "role_in_story": "protagonist",  // filled by reconciliation pass
      "source": "comicinfo"            // comicinfo | dialogue | visual-only
    },
    {
      "id": "guard_1",                 // unnamed characters keep descriptive slugs forever
      "name": null,
      "visual": "bald security guard, grey uniform",
      "first_seen": { "page": 4, "panel": 1 },
      "reference_images": ["pages/0004/panels/panel_01.jpg"],
      "inferred_identity": null,       // world-knowledge guess, if any — flagged, never trusted
      "source": "visual-only"
    }
  ]
}
```

### Anti-hallucination rules (enforced in the analysis prompt)

1. **Closed-set only.** Per panel, the model outputs character `ref`s from
   the current roster, or `"new"` + a visual description. Free-form names
   are rejected by schema validation.
2. **Names must be grounded inside the book** (dialogue, captions, recap
   pages) or come from ComicInfo. A visually recognized but unnamed
   character stays a descriptive slug (`hooded_figure`). World-knowledge
   recognition ("that's clearly Doctor Doom") may only be recorded as
   `inferred_identity` — flagged for the director, never silently trusted.
3. **Evidence required.** Every identification carries visible evidence
   ("claws + yellow suit") and a confidence level. Citing evidence
   measurably reduces confabulation, and low-confidence refs are queryable.
4. **"Unknown" is a correct answer.** The prompt frames abstaining as
   success, not failure — models hallucinate most when unsure and pushed.

### Seeding (extract step)

Most CBZs ship a `ComicInfo.xml` with a `<Characters>` tag plus series
metadata. If present, it seeds the roster with real names as ground truth
(`source: "comicinfo"`); the per-page analysis then *matches* against those
names instead of inventing them. If absent, the roster starts empty and is
built purely from evidence — the reconciliation pass (below) does the
naming work at the end.

### Reconciliation pass (after all pages analyzed)

Greedy page-by-page roster growth leaves messiness; a single text-only LLM
call over the full roster + all page summaries/dialogue/evidence returns:

- **Merges** — same person registered twice (`hooded_figure` p2 =
  `scarred_man` p9; hood came off), with evidence for the merge.
- **Name promotions** — a slug registered early gets named by dialogue
  later (`scarred_man` → `marcus`, grounded by page 15 panel 4).
- **Alias links** — `Logan` ↔ `Wolverine`, grounded by on-page usage.
- **Role inference** — protagonist / antagonist / supporting, from the
  storyline.
- **`inferred_identity` consistency** — a character must carry exactly one
  world-knowledge identity claim across the whole book (not "Doctor Doom"
  on page 4 and a different guess on page 12); conflicting guesses are
  reconciled to one value or nulled out as untrustworthy. This matters
  because the director names inferred identities in narration by default.

Stage 1 then mechanically rewrites all panel `characters[].ref` values
through the merge map so every `page.json` stays consistent. Ambiguous
merges may include reference crops in the call (vision-assisted confirm),
but most are decidable from text evidence. `reconciled: true` marks
completion. When no ComicInfo seed existed, this pass simply does more of
the naming work — the mechanism is identical.

### Optional verification pass (flag, off by default)

For extra confidence: a separate per-page vision call gets only roster
reference images + one panel crop — no story context — and answers the
closed-set "which of these appear here?". Mismatches with the main analysis
get `"verified": false` on the panel ref, and the director narrates those
as "a figure" rather than by name. Catches narrative-bias errors
("Sabretooth *should* be here, so I see him") at the cost of doubling
vision calls; ship disabled, enable per-category if hallucinations show up.

### Downstream payoff

The director may only reference roster `id`s, and narration validation
checks `named_in_story` / ComicInfo sourcing / reconciled
`inferred_identity` — a name that comes from *nowhere* can never reach the
video. (Inferred identities are named by default; roster-grounded names
win when both exist. See the Stage 2 doc's prompt contract.)

---

## `book.json` schema

```jsonc
{
  "schema_version": 1,
  "title": "X-Men United 001 (2026)",
  "series": "X-Men United",            // from ComicInfo, when present
  "publisher": "Marvel",               // from ComicInfo, when present
  "publisher_summary": "…",            // ComicInfo <Summary>: the publisher's blurb.
                                       //   Recorded, but deliberately NOT fed to 1.4 or 1.5 —
                                       //   see "What Stage 1 explicitly does NOT do"
  "category": "comic",
  "source": "X-Men United 001 (2026).cbz",
  "page_count": 22,
  "reading_direction": "ltr",          // ltr | rtl — from ComicInfo <Manga> tag / detection in 1.1;
                                       //   MUST be known before 1.2 orders the panels
  "pages": [                           // lightweight index; source of truth is each page.json
    { "index": 1, "dir": "pages/0001", "page_type": "cover", "status": "analyzed", "panel_count": 1 },
    { "index": 2, "dir": "pages/0002", "page_type": "story", "status": "analyzed", "panel_count": 6 }
  ],
  "story": {                           // written in 1.5, one call over all page analyses
    "synopsis": "…",
    "main_characters": ["wolverine", "sabretooth"],   // refs into characters.json
    "beats": [                         // beats are assigned HERE, with whole-book context —
      { "beat": "inciting incident", "pages": [2, 3] }   // never per-page in 1.3, where
    ],                                 //   everything mid-book looks "rising"
    "skip_overrides": [                // panel skippable hints overturned with forward context
      { "page": 3, "panel": 2, "skippable": false, "reason": "sets up the page-19 payoff" }
    ]
  },
  "analysis": {
    "model": "…",
    "prompt_version": "v1",            // 1.5's synthesis prompt — its own version,
                                       //   unrelated to page.json's (1.3's analyse prompt)
    "completed_at": "2026-07-14T00:00:00Z"   // written by 1.6, the gate Stage 2 checks
  }
}
```

- `pages[]` is a status index for resumability and the first thing the
  director loads. Per-page detail always lives in the page's own `page.json`.
- `story` replaces the old recap-history pickle mechanism. Intermediate state
  is these JSONs instead of pickled Gemini chat history, so the browser-UI
  fallback can slot in per page without any pkl surgery.

---

## Sub-stages

```
CBZ ──1.1─▶ extract ──1.2─▶ split ──1.3─▶ analyze (per page, sequential)
                                              │
            1.4─▶ reconcile characters ──1.5─▶ synthesize story ──1.6─▶ validate
```

### Sub-stage 1.1 — Extract

| | |
|---|---|
| **Input**  | `<comic_folder>/<name>.cbz` |
| **Output** | `pages/NNNN/page.jpg` per page, minimal `page.json` per page, skeleton `book.json`, seeded `characters.json` |
| **Done**   | every `page.json.status ≥ extracted` and `book.json.page_count` set |
| **Uses**   | no LLM, except one text call when the CBZ has no usable title (below) |

Unzip CBZ image members in sorted order to `pages/NNNN/page.jpg`. Write a
minimal `page.json` per page (`status: "extracted"`, dimensions, index) and
a skeleton `book.json` (title, source, page index). Parse `ComicInfo.xml`
if present: seed `characters.json` from its `<Characters>` tag and copy
title/series metadata into `book.json`. If absent, write an empty roster
with `seeded_from: null`.

**Title.** ComicInfo's `<Title>` wins; failing that it is composed from
`Series` + `Number` + `Volume`, which is ground truth and costs nothing. Only
when the CBZ carries no usable metadata does TTT read the filename — scene
release names ("Strange Scales - Infinity Comic 006 (2026)
(digital-mobile-Empire)") defeat tidy pattern rules, and the title goes into
every page's prompt. The model is told to use only what the filename says and
never to correct it against a comic it knows of. If TTT is unreachable the
folder name is used, so 1.1 still runs offline.

**Oversized pages are recompressed, and never resized.** Scans arrive at
~2.4MB/page (2730x4200); a 22-page book drops 51.9MB → 33.7MB at JPEG quality
80, and OCR does not suffer — on a real page it read the same 48 lines and got
*more* of them right, because the compression smooths the screentone that trips
PaddleOCR up. Only pages over 900KB are candidates: a small page is small
because it is already well compressed, and re-encoding an 800x1280 digital
release comes out *larger* (+6% at q85) while still discarding pixels. The
result is kept only if it actually shrank.

Dimensions are never touched, and the 900KB ceiling is therefore not always
met (11.5MP cannot reach it — even q40 misses, at 985KB). That is deliberate:
the page is only ~1.4x the width of the video frame, and panels are cropped out
of it and zoomed, so the pixels are spent on the render. Bytes are negotiable;
pixels are not.

Also determined here, because later sub-stages depend on them:

- **Reading direction.** From the ComicInfo `<Manga>` tag
  (`YesAndRightToLeft` → `rtl`), default `ltr`. This **must** be known
  before 1.2 names panels — an RTL book split in LTR order poisons panel
  ids, narration order, and camera pans for the entire pipeline.
- **Spread detection.** A landscape page (aspect ratio well above portrait,
  e.g. width/height > 1.3) is marked `is_spread: true`. Spreads are usually
  money-shot moments the director should treat differently (slow pan), and
  they shift page numbering.

### Sub-stage 1.2 — Split

| | |
|---|---|
| **Input**  | pages with `status = extracted`, `book.json.reading_direction` |
| **Output** | `panels/panel_NN.jpg` crops + `panels[]` skeletons (id, image, bbox, text_regions) + `ocr_lines` in `page.json` |
| **Done**   | every `page.json.status ≥ split` |
| **Uses**   | comic-panel-extractor (local YOLO/CV) + the OCR service, no LLM |

Run comic-panel-extractor on **every** page upfront (the old pipeline split
lazily during video creation, which is why shorts had to pick panels at
random). Parse bboxes from the extractor's filenames, rename crops to
`panel_NN.jpg` in reading order — **honoring `reading_direction`** (RTL
books order right-to-left within a row) — and record bboxes in `page.json`.
Pages where extraction finds a single panel (covers, splashes) just get
`panel_count: 1`. Per-page: a page failing extraction falls back to
`panel_count: 1` (whole page as its single panel) rather than blocking the
book. A tool that fails on *every* page is a broken tool rather than a hard
book, and raises — 19 whole-page "panels" would otherwise sail through 1.6 and
produce a video with no panel-level camera work at all.

**Duplicate detections are dropped.** The extractor sometimes finds one panel
twice: real page 6 came back as 710x1132 and 613x1097, nested, the same
drawing. Left in, the page is described twice and the video shows the same
panel twice in a row. Overlap alone cannot decide this, because an inset panel
sits *entirely* inside its parent and is a genuine separate panel. IoU
separates them — the duplicate scores 0.84, while a real inset scores 0.13
despite being 100% contained — so boxes above IoU 0.7 collapse to the larger
one, which may carry gutter where the smaller would cut art.

**Text regions come from OCR here**, not from the extractor's text detector
(disabled upstream) and not from the vision model in 1.3 (which invents
coordinates). PaddleOCR returns one box per *line*, so a five-line bubble
arrives as five boxes with a few pixels between them; a crop could pass
through those gaps, intersecting no box while cutting the bubble in half.
Lines are therefore merged into the bubble they belong to — side by side, with
a vertical gap under ~70% of a line's height — and assigned to panels by
overlap. Every line is also kept raw in `ocr_lines` for 1.3's dialogue
matching. OCR failing costs text regions, not the page.

The OCR call and the extractor both need only `page.jpg` and neither uses the
other's answer, so OCR is started first and waits on the network while the
extractor has the CPU — its ~18s hides inside the extractor's ~30s. Pages stay
sequential, so the OCR service still sees one request at a time.

### Sub-stage 1.3 — Analyze

| | |
|---|---|
| **Input**  | pages with `status = split`, current `characters.json` |
| **Output** | full `analysis` + `panels[]` detail in each `page.json`; new entries appended to `characters.json` |
| **Done**   | every `page.json.status = analyzed` |
| **Uses**   | vision LLM, one call per page, sequential (order matters) |

One vision call per page, in reading order. The request contains the full
page image, the accumulated context of previous pages' `scene_summary`
values — this preserves narrative continuity the way the old sequential
chat history did — and the **current character roster** (ids + visual
descriptions). The model returns the full `analysis` + `panels[]` structure
(including closed-set character refs with evidence) in one schema-validated
response; new characters are appended to `characters.json`. Write
`page.json` atomically.

**As built:** only `page.jpg` is uploaded; panels are identified to the
model by **id + bbox in the prompt text**, not by uploading each crop. This
is cheaper, keeps every panel in full-page context, and matches the LLM
wrapper's one-file-per-call API. 1.2's geometry stays authoritative: the
merge keeps `id`/`bbox` from the split and takes only the description
fields from the model, so a model that renumbers or relocates panels cannot
corrupt the page.

Per panel, 1.3 also produces:

- **`focal_point`** — *relative* position of the visual subject within its
  panel (face, clash point, revealed object), each axis 0..1; the zoom/ken-burns
  target for Stage 3. Deliberately not a pixel coordinate: "roughly which
  corner" is a judgement a model can make, and is clamped into range on the way
  in.
- **`content_warnings`** (page-level) — objective flags (graphic-violence,
  blood, gore) for downstream monetization decisions.
- **`reading_order_suspect`** (page-level) — set when the panel ordering
  from 1.2 contradicts the visual flow (creative layouts defeat CV
  ordering even in LTR books); the director treats such pages carefully.
- **`unassigned_dialogue`** (page-level) — captions/titles in gutters or
  spanning panels, so no on-page text is forced into the wrong panel or
  dropped.

Deliberately **not** produced here: `story_beat` (a sequential pass cannot know
mid-book whether a page is the climax — beats are assigned globally in 1.5) and
**any pixel coordinate** (see `text_regions`).

**Locating dialogue.** After the page comes back, each line of dialogue is
given the box of the bubble it is written in. Neither source can do this alone:
OCR measured the boxes but mangles stylised lettering, and the vision model
read the text correctly but cannot measure. So both are handed to the text
model, which returns *line numbers only* — the union of those boxes is computed
in code, because the moment a model is asked for a coordinate it invents one.
The vision model's split into bubbles drives the grouping, which no rule about
pixel gaps can do: two speakers trading one-liners sit as close together as two
lines of one bubble. Unassigned captions are located the same way, and are the
text most worth locating, being the least likely to fall inside any panel.
Best-effort — a failure costs the link, not the page.

**Output format.** The vision model is asked for `label: value` lines, not
JSON. It is driven through a chat UI which enforces no schema, and a browser
answering in prose is normal. If the direct parse fails, TTT reshapes the prose
into JSON against the schema; the reshape is a fallback, not the main path.

### Sub-stage 1.4 — Reconcile characters

| | |
|---|---|
| **Input**  | all pages analyzed + unreconciled `characters.json` |
| **Output** | merged/named/aliased roster; panel `characters[].ref` rewritten through the merge map |
| **Done**   | `characters.json.reconciled = true` |
| **Uses**   | text-only LLM, one call |

One text-only LLM call over the full roster and all page analyses: merges
duplicates, promotes names grounded by late dialogue, links aliases, infers
story roles. Stage code then mechanically rewrites all panel
`characters[].ref` values through the merge map so every `page.json` stays
consistent. See the characters.json section for the anti-hallucination
rules this pass operates under.

**It is also told which characters were drawn together in one panel**, computed
in code. From descriptions alone, one character registered twice and two
characters who resemble each other are indistinguishable — and the roster is
full of both. Real book: `pink_snake_left` and `pink_snake_right` read as an
obvious duplicate and are two characters, seen together three times;
`bearded_helper` and `mustached_helper` never share a panel and are the real
merge candidate. 1.4 would have to cross-reference every panel in the book to
notice, so the pairs are handed over.

Treated as near-absolute but **not enforced in code**: the pairing is 1.3's own
output rather than ground truth, and a character beside their own reflection or
wanted poster is registered twice in one panel and *is* one character. Blocking
a true merge is no better than making a false one, so 1.4 may override with
evidence that explains the sharing, and must say so in `evidence`.

### Sub-stage 1.5 — Synthesize story

| | |
|---|---|
| **Input**  | all pages analyzed, roster reconciled |
| **Output** | `book.json.story` (synopsis, main character refs, beats, skip overrides) |
| **Done**   | `book.json.story` written |
| **Uses**   | text-only LLM, one call |

One call over all page analyses produces `book.json.story`. This is where
whole-book judgments live, because only this pass has forward context:

- **`beats[]`** — setup/inciting/rising/climax/resolution mapped to page
  ranges. Assigned here, never per-page in 1.3, where the model hasn't
  seen the ending and everything mid-book looks "rising".
- **`skip_overrides[]`** — panel `skippable` hints from 1.3 that forward
  context overturns (a panel that looks redundant on page 3 may set up
  the page-19 payoff). The director reads hints *through* these overrides.

### Sub-stage 1.6 — Validate

| | |
|---|---|
| **Input**  | everything above |
| **Output** | `book.json.analysis.completed_at` — the gate Stage 2 checks |
| **Uses**   | deterministic, no LLM |

A cheap consistency pass over all Stage 1 output; **this is what actually
marks Stage 1 complete**, so a bug in any earlier step (e.g. the 1.4
merge-map rewrite) cannot silently poison the director:

- every page has `status = analyzed`; page index is contiguous
- every panel `characters[].ref` resolves in `characters.json`
- every `reference_images` / panel `image` path exists on disk
- every bbox and text region lies within its page bounds; focal points in [0,1]
- every `skip_overrides` / `beats` page+panel reference resolves
- `characters.json.reconciled = true`

Any violation is reported with file + field and `completed_at` is withheld.

---

## Models, and the division of labour

Four workers, and the boundaries between them are the load-bearing part:

| Worker | What it is | What it is asked for |
|---|---|---|
| **extractor** | comic-panel-extractor, local YOLO/CV | panel boxes |
| **OCR** | PaddleOCR at `jebin2-ocr.hf.space` | text boxes (its text is kept only for matching) |
| **vision** | Gemini web UI, driven in a neko docker browser | descriptions, characters, dialogue words, focal_point |
| **text** | TTT at `opencode.voidall.com`, model `opencode` | reshape prose→JSON, match dialogue↔boxes, reconcile, synthesize |

The rule underneath: **models transcribe and match; arithmetic and geometry stay
in code.** A model is never asked for a pixel coordinate, and never asked to
compute a union, an overlap, or a page number. It returns line numbers and ids;
code turns those into boxes. Every coordinate bug in this pipeline came from
crossing that line, and every fix has been to move the arithmetic back.

**Vision is the Gemini UI, and is not configurable.** It needs no API key — it
rides the browser's Google session. Search AI Mode was the default until it was
measured: it is a *search query*, capped at 2048 bytes, and 1.3 sends ~7.5KB.
73% of the prompt was silently dropped, taking every rule from "## Characters"
onward and the entire user message with the panel list. The model was shown an
image, half a rulebook, and no panel ids.

That one bug produced every 1.3 failure we spent days treating as prompt-wording
problems: prose instead of the requested format (the output section, byte 5217,
never arrived — it was never true that "AI Mode won't return JSON"), blank
`visual` on every character (its rule sits at byte 3160), and scene summaries
describing the layout instead of the story (no panel list, half the rules).
**If output quality ever collapses again, measure the prompt against whatever
box it is being typed into before rewriting a word of it.**

`gemini` as a *text* provider means the Gemini **API** and wants
`GEMINI_API_KEY` — a different thing entirely from the browser UI. The vision
selector was removed rather than repointed, so the name cannot mean two things.

**Text work goes to TTT, not the browser.** 1.4 and 1.5 are one call each, so
the browser's fragility (a docker container, a Google login, CSS selectors that
break when Google reships their frontend) buys nothing. Gemini working well for
1.3 is not an argument for text: 1.3 was never a model-quality problem, and
opencode is verified good on 1.4 and 1.5. `PANELFLOW_TEXT_PROVIDER` exists if
that ever stops being true.

---

## Idempotency & re-run matrix

Every sub-stage scans its done-markers and only processes what isn't done.
Targeted re-runs:

| To redo…                        | Do this                                             | What re-runs        |
|---------------------------------|-----------------------------------------------------|----------------------|
| one page's analysis             | reset that page's `status` to `split`               | 1.3 for that page, then 1.4–1.6 |
| all analysis (better prompt)    | bump `analyze.PROMPT_VERSION`                       | 1.3–1.6 only; extraction/split cached |
| one page entirely               | delete `pages/NNNN/`                                | 1.1–1.6 for that page |
| character reconciliation        | set `characters.json.reconciled = false`            | 1.4–1.6              |
| the story only                  | bump `synthesize.PROMPT_VERSION`                    | 1.5–1.6              |
| everything                      | delete `assets/`                                    | all                  |

Downstream invalidation is enforced: resetting an earlier sub-stage clears
the done-markers of later ones (a re-analyzed page invalidates
`reconciled` and `completed_at`).

**Bumping `PROMPT_VERSION` is a manual step, and the one that gets forgotten.**
Pages record the version they were analysed under, and `_is_current()` compares
it to the constant — so rewriting `analyze_page.md` without bumping means every
already-analysed page is skipped and the book stays half-described by the old
prompt. This has happened once already: the prompt was rewritten end to end
while the constant stayed `v1`. If a prompt change appears to do nothing, this
is why.

Note also that deleting `assets/` costs one 1.2 run — the extractor is ~30s of
CPU per page and there is no cache below the page level. Page images
re-extract in about a second, so surgical deletion rarely pays.

---

## What Stage 1 explicitly does NOT do

- No narration writing (Stage 2 owns voice, tone, pacing).
- No skip/keep decisions (only the `skippable` hint).
- No animation/transition choices.
- No TTS, STT, resizing, or rendering (Stage 3).
- No title/description/social-post generation (Stage 2, from `book.json.story`).
- **No reading of the publisher's blurb.** `publisher_summary` is recorded in
  `book.json` but reaches no prompt. For naming it is a hazard: a summary
  reading "Anton and Aleister's mysterious impersonator is revealed" names two
  characters without saying which face is which, and mapping them onto slugs is
  exactly the ungrounded guessing the roster rules forbid — names enter from
  ComicInfo only via *seeded roster entries*, which carry an identity, never via
  prose. For the story it turned out to be unnecessary: 1.5 found the
  impersonator reveal from the pages alone ("Lily screams that it is Afanaf's
  other half"), so the blurb would add marketing bias for no gain. It stays on
  disk for Stage 2's description/social copy, where it *is* the right source.

---

## Stage 2 preview (to be designed next)

The **director** — a text-only LLM pass (Claude) that reads `book.json` +
all `page.json` files and emits schema-validated shot lists into
`direction/` (`longform.json`, `shorts.json`): which panels to show or skip,
narration per shot, animation matched to content, transitions, pacing,
events. Re-runnable at zero vision cost.
