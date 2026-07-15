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

PROMPT_VERSION = "v1"
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
    page["status"] = ANALYZED
    assets.save_page(index, page)


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
        if not panel.get("text_regions"):
            panel["text_regions"] = _clip_regions(found.get("text_regions", []), panel["bbox"], page)
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


def _clip_regions(regions, bbox, page):
    """Keep only well-formed page-space boxes that sit inside this panel."""
    kept = []
    for region in regions:
        if not (isinstance(region, list) and len(region) == 4):
            continue
        x1, y1, x2, y2 = (int(v) for v in region)
        if not (0 <= x1 < x2 <= page["width"] and 0 <= y1 < y2 <= page["height"]):
            continue
        if bbox[0] <= (x1 + x2) / 2 <= bbox[2] and bbox[1] <= (y1 + y2) / 2 <= bbox[3]:
            kept.append([x1, y1, x2, y2])
    return kept


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
