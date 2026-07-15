"""Sub-stage 1.3 — Analyze.

One vision call per page, in reading order, carrying previous pages' summaries
and the growing character roster as context. Sends the full page image only;
panels are described by bbox in the prompt text (cheaper than uploading crops,
and the model sees each panel in page context).
"""
from custom_logger import logger_config

from .. import llm, prompts
from ..paths import ANALYZED, SPLIT, invalidate_downstream, status_at_least
from . import roster, schemas

# Bump whenever analyze_page.md changes in a way that would alter its output.
# Pages carry the version they were analyzed under, so a bump re-analyzes them
# instead of leaving a book half-described by the old prompt.
PROMPT_VERSION = "v2"
CONTEXT_PAGES = 3


def is_done(assets):
    pages = assets.pages()
    return bool(pages) and all(_is_current(p) for _, p in pages)


def run(assets, model=None):
    if is_done(assets):
        return

    system_prompt = prompts.load("analyze_page")
    indices = assets.page_indices()
    for index in indices:
        page = assets.load_page(index)
        if _is_current(page):
            continue
        if not status_at_least(page.get("status", ""), SPLIT):
            raise ValueError(f"page {index} is not split yet")
        logger_config.info(f"1.3 analyze page {index}/{len(indices)}", overwrite=True)
        _analyze_page(assets, index, page, system_prompt, model)

    assets.rebuild_index()
    invalidate_downstream(assets, include_roster=True)


def _is_current(page):
    return (page.get("status") == ANALYZED
            and page.get("analysis", {}).get("prompt_version") == PROMPT_VERSION)


def _analyze_page(assets, index, page, system_prompt, model):
    characters = assets.load_characters()
    result = llm.ask_json(
        system_prompt=system_prompt,
        user_prompt=_user_prompt(assets, index, page, characters),
        schema=schemas.PAGE_ANALYSIS,
        image_path=assets.page_image(index),
        model=model,
    )

    roster.add_new(characters, result.get("new_characters", []), index)
    known = roster.ids(characters)
    assets.save_characters(characters)

    page["page_type"] = result.get("page_type", page.get("page_type", "story"))
    page["analysis"] = {
        "model": model or "default",
        "prompt_version": PROMPT_VERSION,
        "scene_summary": result.get("scene_summary", ""),
        "mood": result.get("mood", ""),
        "continuity_note": result.get("continuity_note", ""),
        "reading_order_suspect": bool(result.get("reading_order_suspect")),
        "content_warnings": result.get("content_warnings", []),
        "unassigned_dialogue": result.get("unassigned_dialogue", []),
    }
    page["panels"] = _merge_panels(page["panels"], result.get("panels", []), known, page)
    _locate_dialogue(page, model)
    page["status"] = ANALYZED
    assets.save_page(index, page)


def _locate_dialogue(page, model):
    """Give every line of dialogue the box of the bubble it is written in.

    OCR knows where the lettering is but mangles it; the vision model reads it
    correctly but cannot measure. Only a text match joins the two — and the
    vision model's split into bubbles drives the grouping, which a rule about
    pixel gaps cannot do: two speakers trading one-liners sit as close together
    as two lines of one bubble.
    """
    lines = page.get("ocr_lines") or []
    dialogue = [d for panel in page["panels"] for d in panel.get("dialogue", [])]
    if not lines or not dialogue:
        return

    try:
        result = llm.ask_json(
            system_prompt=prompts.load("match_dialogue"),
            user_prompt=_match_prompt(dialogue, lines),
            model=model,
        )
    except Exception as e:
        logger_config.warning(f"1.3 page {page['page_index']}: dialogue not located: {e}")
        return

    for match in result.get("matches", []):
        entry = _nth(dialogue, match.get("dialogue_index"))
        boxes = [lines[i]["box"] for i in match.get("lines", [])
                 if isinstance(i, int) and 0 <= i < len(lines)]
        if entry is not None and boxes:
            entry["region"] = [min(b[0] for b in boxes), min(b[1] for b in boxes),
                               max(b[2] for b in boxes), max(b[3] for b in boxes)]


def _nth(dialogue, index):
    return dialogue[index] if isinstance(index, int) and 0 <= index < len(dialogue) else None


def _match_prompt(dialogue, lines):
    said = "\n".join(f'{i}: {d.get("text", "")!r}' for i, d in enumerate(dialogue))
    found = "\n".join(f'{i}: {l["text"]!r} box {l["box"]}' for i, l in enumerate(lines))
    return f"DIALOGUE\n{said}\n\nOCR LINES\n{found}"


def _merge_panels(panels, analysed, known_ids, page):
    """Keep 1.2's geometry as truth; fold in 1.3's description per panel id."""
    by_id = {a.get("id"): a for a in analysed}
    merged = []
    for panel in panels:
        found = by_id.get(panel["id"], {})
        panel["role"] = found.get("role", "dialogue")
        panel["description"] = found.get("description", "")
        panel["intensity"] = _clamp(found.get("intensity", 3), 1, 5)
        panel["skippable"] = bool(found.get("skippable"))
        panel["focal_point"] = _focal_point(found.get("focal_point"))
        panel["dialogue"] = found.get("dialogue", [])
        panel["characters"] = [c for c in found.get("characters", []) if c.get("ref") in known_ids]
        # text_regions stay exactly as 1.2's OCR measured them.
        merged.append(panel)
    return merged


def _clamp(value, low, high):
    try:
        return max(low, min(high, int(value)))
    except (TypeError, ValueError):
        return (low + high) // 2


def _focal_point(point):
    if not (isinstance(point, list) and len(point) == 2):
        return [0.5, 0.5]
    try:
        return [max(0.0, min(1.0, float(point[0]))), max(0.0, min(1.0, float(point[1])))]
    except (TypeError, ValueError):
        return [0.5, 0.5]


def _user_prompt(assets, index, page, characters):
    panels = "\n".join(
        f'- panel {p["id"]}: bbox [{p["bbox"][0]}, {p["bbox"][1]}, {p["bbox"][2]}, {p["bbox"][3]}]'
        for p in page["panels"]
    )
    book = assets.load_book()
    return "\n\n".join([
        f'Comic: {book.get("title", assets.name)}',
        f'Page {index} of {book.get("page_count", "?")} — image is {page["width"]}x{page["height"]} px'
        + (" — this is a double-page spread." if page.get("is_spread") else ""),
        f'Panels on this page (reading order, {book.get("reading_direction", "ltr")}):\n{panels}',
        f'Character roster so far:\n{roster.describe_for_prompt(characters)}',
        f'Story so far:\n{_story_so_far(assets, index)}',
    ])


def _story_so_far(assets, index):
    lines = []
    for i in range(max(1, index - CONTEXT_PAGES), index):
        summary = assets.load_page(i).get("analysis", {}).get("scene_summary")
        if summary:
            lines.append(f"- page {i}: {summary}")
    if lines:
        return "\n".join(lines)
    # Earlier pages can exist but have no summary — a cover, or an analysis that
    # came back thin. Saying "this is the first page" then is simply false.
    return "(this is the first page)" if index == 1 else "(nothing recorded from earlier pages)"
