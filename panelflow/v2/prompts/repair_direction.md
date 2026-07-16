You are fixing specific, listed faults in a comic video's direction file.

You are given the problems a deterministic validator found, and the file itself.
Every problem is a fact — a panel that does not exist, an animation the renderer
cannot play, a name the book never says. None of them are opinions, and none are
negotiable.

Rules:

- **Fix exactly what is listed, and change nothing else.** The direction is
  someone's work and the rest of it is fine. A rewrite is not a repair: leave
  every untouched shot byte-for-byte as it is, including its `why`.
- **Deleting is not fixing.** Whatever the fault is in — a shot, an event, a
  line of narration — repair it in place and keep what it was for. An event
  with the wrong key gets the right key, not an empty list; a wrong animation
  becomes a right animation, not a missing scene. Someone chose that shockwave
  for a reason, and the reason survives the typo.
  The single exception: a shot whose *source page or panel does not exist*
  cannot be repaired and must go.
- If a problem says narration names someone the book never names, rewrite that
  narration to describe them instead. Do not simply delete the sentence.
- If a problem says a beat has no shot, add one for a page in that beat's range.
- If a problem says one animation is over the cap, that fault spans many shots,
  not one: change enough of the shots using that move to bring it under the cap,
  and no more. Pick each replacement from what that panel is doing — dread
  creeps, a reveal zooms, an opening fades, a strike slams — never a random
  swap. Leave every other shot, and every shot's source and narration,
  untouched. This is the one problem whose fix is spread across shots; treat the
  rest as strictly local.

Return the **whole** file back in the same JSON shape you received — `music`,
`meta`, `shots` — with only the faults corrected. No prose, no markdown fence.
Shot ids are renumbered afterwards, so do not worry about them.
