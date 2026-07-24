You are given one line of a comic video's narration and every panel on the
page it was drawn from. The line is already written and **you do not change a
single word of it.** Your only job is to find where the *picture* changes.

A narrator often tells several beats over one held image: a character arrives,
speaks, and is answered, while the screen shows one drawing the whole time. But
the page usually drew each of those beats as its own panel. Your task is to cut
the line into consecutive pieces and hand each piece the panel that actually
depicts it — so the image moves with the story instead of sitting still.

## What you return

An ordered list of segments. Each segment is a verbatim stretch of the line and
the id of the panel that shows it:

```
{"segments": [
  {"panel": 3, "text": "Mother Despina and Ione stand outside the lit convent, preparing for an arrival."},
  {"panel": 4, "text": "Everything has been readied. Master Slay is coming shortly."},
  {"panel": 5, "text": "Ione asks whether the sisters might stay. It has been so very long since they last saw her."}
]}
```

## The rules

- **The pieces are the line, exactly.** Joined back together in order, with
  single spaces, they must reproduce the narration word for word. Do not
  paraphrase, drop, add, or reorder anything. If you cannot cover the whole
  line this way, return it as one segment (see below).
- **Cut only on complete sentences.** A piece is one or more whole sentences,
  never a fragment.
- **A panel must genuinely depict its piece.** The people, place, or action the
  sentence names must be what that panel draws. A panel that only *loosely*
  fits is not a match — a wrong picture under the words is worse than a still
  one.
- **Each piece gets a different panel** from the piece before it. Showing the
  same drawing twice in a row is not movement.
- **Prefer panels not yet used** elsewhere in the video (you are told which are
  taken). Reusing the shot's own panel is fine; repeating another shot's is
  not.
- **Keep the reading order.** Later pieces should, as far as the pictures
  allow, use later panels — the page tells its story front to back.

## When not to split

**One segment is the normal, expected answer.** If the whole line really is one
image — a single moment described from a few angles, an inner thought, a beat
with no second panel that fits — return exactly one segment covering the entire
line. Do not invent a picture change to look thorough. A forced split is a
worse video than the still image it replaced.

Return only JSON, no prose and no markdown fence.
