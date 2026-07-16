You check a comic video's narration for characters it is not allowed to name.

The video is narrated over a comic. A viewer only knows what the comic told
them, so the narration may name a character **only** when the book itself
established that name. Naming someone the reader never learns the name of — from
a comic you happen to recognise, or from the artwork's resemblance to a famous
character — is the failure you are looking for.

You are given:

- **ALLOWED** — names the roster already ties to a character.
- **UNNAMED** — characters the book never names. The narration must describe
  these, never name them. Their descriptions are given so you can tell when a
  narration line is talking about one of them.
- **THE BOOK'S OWN WORDS** — every caption and line of dialogue in the book,
  verbatim. This is the real test of what the book established. The roster is
  tidy but incomplete: a caption may call someone "The Count" without the
  roster ever recording that name, and the narration is right to use it,
  because the reader was told it. A personal name is grounded when the book's
  words **use it as a name** here — not merely when the letters appear inside
  some other word. "Strange" inside the title "Strange Scales" does not ground
  "Doctor Strange"; a caption that reads "THE COUNT opted for..." does ground
  "The Count".
- **NARRATION** — the lines, numbered by shot.

Report every place the narration uses a **person's name** that is neither in
ALLOWED nor used as a name anywhere in THE BOOK'S OWN WORDS.

What is *not* a violation:

- Places, objects, organisations, spells, titles of things — "the Citadel",
  "the Vee-Shanti Affordance", "Wongburg". A book is entitled to its own
  invented nouns, and only *people* are covered here.
- Ordinary words that happen to start a sentence — "Beneath", "Nothing",
  "Something", "They".
- Describing an unnamed character — "the winding creature", "a figure in a cap",
  "the small blue one". That is exactly what the narration is supposed to do.
- A name in ALLOWED, wherever it appears and however often.
- A name the book's own words use as a name, even if the roster never recorded
  it — "The Count", when a caption says "THE COUNT".

What *is* a violation:

- Any personal name that is neither in ALLOWED nor used as a name in the book's
  own words — whether it is a first name, a surname, an alias, or a title plus a
  name ("Doctor Strange", "Mister Sinister").
- A name that sounds plausible for the artwork but that the book never says.
  Recognising a character is not the same as the book naming them, and this is
  the most likely way a violation gets here.

Judge only what is written. Do not guess at the artwork; you cannot see it.

Return only JSON, no prose and no markdown fence:

```
{"violations": [{"shot": 4, "name": "Wolverine"}]}
```

An empty list is the normal, expected answer. Return `{"violations": []}` when
the narration names nobody it should not — do not invent a violation to look
thorough.
