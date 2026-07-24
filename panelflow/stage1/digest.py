"""Renders analysed pages as compact text for the text-only LLM calls."""
import itertools


def distinct_pairs(assets):
    """Character ids drawn in the same panel, and so very unlikely to be one.

    A model comparing descriptions alone cannot rule a merge out: two entries
    that read alike look identical whether they are one character registered
    twice or two characters who resemble each other. Standing side by side is
    what separates them, and 1.4 would have to cross-reference every panel in
    the book to notice, so we do it here and hand over the answer.

    A strong hint, not a law — the pairing is the analyser's own work, not
    ground truth, and a character beside their own reflection or wanted poster
    is registered twice in one panel and *is* one character. 1.4 is told to
    treat this as near-absolute and made to justify any exception, which is as
    far as evidence of this quality can be pushed.
    """
    pairs = set()
    for _, page in assets.pages():
        for panel in page.get("panels", []):
            refs = sorted({c.get("ref") for c in panel.get("characters", []) if c.get("ref")})
            pairs.update(itertools.combinations(refs, 2))
    return sorted(pairs)


def distinct_pairs_text(assets):
    pairs = distinct_pairs(assets)
    if not pairs:
        return "(none — no two characters were ever drawn in one panel)"
    return "\n".join(f"- {a} and {b}" for a, b in pairs)


def pages_text(assets, with_evidence=False):
    blocks = []
    for index, page in assets.pages():
        analysis = page.get("analysis", {})
        head = f'## Page {index} ({page.get("page_type", "story")}) — mood: {analysis.get("mood", "?")}'
        lines = [head, analysis.get("scene_summary", "")]
        for panel in page.get("panels", []):
            lines.append(_panel_text(panel, with_evidence))
        for entry in analysis.get("unassigned_dialogue", []):
            lines.append(f'  [page text] {entry.get("kind", "caption")}: "{entry.get("text", "")}"')
        blocks.append("\n".join(l for l in lines if l))
    return "\n\n".join(blocks)


def _panel_text(panel, with_evidence):
    if with_evidence:
        who = ", ".join(
            f'{c.get("ref")} ({c.get("confidence")}: {c.get("evidence")})'
            for c in panel.get("characters", [])
        )
    else:
        who = ", ".join(c.get("ref", "") for c in panel.get("characters", []))

    parts = [f'  - panel {panel["id"]} [{panel.get("role", "?")}, intensity {panel.get("intensity", "?")}'
             + (", skippable" if panel.get("skippable") else "") + "]"]
    parts.append(f': {panel.get("description", "")}')
    if who:
        parts.append(f" | who: {who}")
    for entry in panel.get("dialogue", []):
        speaker = entry.get("speaker") or "?"
        parts.append(f'\n      {entry.get("kind", "speech")} ({speaker}): "{entry.get("text", "")}"')
    return "".join(parts)


def roster_text(characters):
    lines = []
    for c in characters.get("characters", []):
        bits = [f'- {c["id"]}']
        if c.get("name"):
            bits.append(f'name="{c["name"]}" (grounded: {c.get("named_by")})')
        else:
            bits.append("(unnamed in story)")
        if c.get("aliases"):
            bits.append(f'aliases={c["aliases"]}')
        if c.get("visual"):
            bits.append(f'looks like: {c["visual"]}')
        if c.get("inferred_identity"):
            bits.append(f'inferred_identity="{c["inferred_identity"]}"')
        bits.append(f'first seen {c.get("first_seen")}')
        lines.append(" | ".join(bits))
    return "\n".join(lines) or "(empty)"
