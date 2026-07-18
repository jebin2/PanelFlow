"""Renders Stage 1's assets as the text the director reads.

Deliberately not stage1's digest. That one is built for 1.4 and 1.5, who judge
identity and story; the director judges shots, and needs different facts — every
panel's effective skippability, spreads, suspect ordering, content warnings —
and is actively harmed by others. It never sees pixels, so a character's
appearance is not context for it, except in the one place it *is*: what to call
someone the book never names.
"""


def roster_text(characters):
    """The roster as naming rules, not as descriptions.

    The director's only question about a character is "what may I call them",
    and that is decided here rather than in the prompt: a name is sayable when
    the book grounds it (1.3/1.4 recorded where), or when 1.4 settled on an
    inferred identity. Everyone else must be described, so the unnamed — and
    only the unnamed — carry their visual, which is what the narration has to
    reach for instead of a name.
    """
    names = {c["id"]: _sayable_name(c) or c["id"]
             for c in characters.get("characters", [])}
    lines = []
    for c in characters.get("characters", []):
        role = c.get("role_in_story") or "role unknown"
        name = _sayable_name(c)
        if name:
            line = f'- {c["id"]} | say "{name}" ({_why_sayable(c)}) | {role}'
        else:
            visual = c.get("visual") or "no description recorded"
            line = (f'- {c["id"]} | NOT named in this book — describe them, '
                    f"never invent a name | looks like: {visual} | {role}")
        # 1.4 grounded these in the book's own text, so the narration may say
        # them; a relationship absent here must not be spoken.
        rel = ", ".join(f'{r["relation"]} of {names.get(r["to_id"], r["to_id"])}'
                        for r in c.get("relationships") or [])
        lines.append(line + (f" | {rel}" if rel else ""))
    return "\n".join(lines) or "(no characters)"


def _sayable_name(character):
    if character.get("name"):
        return character["name"]
    return character.get("inferred_identity") or None


def _why_sayable(character):
    if character.get("name"):
        named_by = character.get("named_by")
        if named_by:
            return f'named on page {named_by.get("page")}'
        return "named in the book's metadata"
    return "identity settled in 1.4"


def book_text(assets):
    """Every page in reading order: what is on it, and what the director may do
    with it."""
    story = assets.load_book().get("story", {})
    overrides = _overrides_by_panel(story)
    blocks = []
    for index, page in assets.pages():
        blocks.append(_page_text(index, page, overrides))
    return "\n\n".join(blocks)


def _page_text(index, page, overrides):
    analysis = page.get("analysis", {})
    flags = []
    if page.get("is_spread"):
        flags.append("SPREAD — worth its moment, usually a slow pan")
    if analysis.get("reading_order_suspect"):
        flags.append("READING ORDER SUSPECT — no cross-panel pans on this page")
    if analysis.get("content_warnings"):
        flags.append(f'CONTENT WARNING: {", ".join(analysis["content_warnings"])} — '
                     f"do not linger")

    head = (f'## Page {index} ({page.get("page_type", "story")}) — '
            f'mood: {analysis.get("mood", "?")}')
    lines = [head]
    lines += [f"  ! {f}" for f in flags]
    if analysis.get("scene_summary"):
        lines.append(f'  {analysis["scene_summary"]}')
    for panel in page.get("panels", []):
        lines.append(_panel_text(index, panel, overrides))
    for entry in analysis.get("unassigned_dialogue", []):
        lines.append(f'  [page text] {entry.get("kind", "caption")}: "{entry.get("text", "")}"')
    return "\n".join(lines)


def _panel_text(page_index, panel, overrides):
    skippable, reason = _effective_skip(page_index, panel, overrides)
    bits = [f'  - page {page_index} panel {panel["id"]} '
            f'[{panel.get("role", "?")}, intensity {panel.get("intensity", "?")}'
            + (", SKIPPABLE" if skippable else "") + "]"]
    if reason:
        bits.append(f" ({reason})")
    bits.append(f': {panel.get("description", "")}')
    who = ", ".join(c.get("ref", "") for c in panel.get("characters", []))
    if who:
        bits.append(f" | who: {who}")
    for entry in panel.get("dialogue", []):
        speaker = entry.get("speaker") or "?"
        bits.append(f'\n      {entry.get("kind", "speech")} ({speaker}): "{entry.get("text", "")}"')
    return "".join(bits)


def _effective_skip(page_index, panel, overrides):
    """1.3's hint, as 1.5's whole-book context left it.

    1.3 marks a panel skippable seeing only the pages before it; 1.5 reads the
    whole book and overturns the ones that pay off later. Resolving that here
    means the director is told the answer instead of being handed two lists and
    trusted to cross-reference them — and a director that missed the override
    would cut the setup for the ending.
    """
    override = overrides.get((page_index, panel["id"]))
    if override is not None:
        return override.get("skippable", False), f'1.5: {override.get("reason", "")}'
    return bool(panel.get("skippable")), None


def _overrides_by_panel(story):
    return {(o.get("page"), o.get("panel")): o for o in story.get("skip_overrides", [])}


def beats_text(story):
    """The plot's spine. Longform must touch every one of these."""
    beats = story.get("beats", [])
    if not beats:
        return "(none recorded)"
    return "\n".join(f'- {b.get("beat")}: pages {b.get("pages")}' for b in beats)
