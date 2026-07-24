"""Sub-stage 1.6 — Validate.

Deterministic consistency pass over all Stage 1 output. This is what marks
Stage 1 complete, so a bug in any earlier sub-stage cannot silently poison
the director. No LLM.
"""
import os
from datetime import datetime, timezone

from ..paths import ANALYZED


def is_done(assets):
    return bool(assets.load_book().get("analysis", {}).get("completed_at"))


def run(assets, model=None):
    if is_done(assets):
        return []

    problems = check(assets)
    if problems:
        return problems

    book = assets.load_book()
    book.setdefault("analysis", {})["completed_at"] = datetime.now(timezone.utc).isoformat()
    assets.save_book(book)
    return []


def check(assets):
    """Every violation as a 'where: what' string. Empty list == valid."""
    problems = []
    book = assets.load_book()
    characters = assets.load_characters()
    roster = {c["id"] for c in characters.get("characters", [])}

    problems += _check_pages_contiguous(book)
    if not characters.get("reconciled"):
        problems.append("characters.json: not reconciled")

    for index, page in assets.pages():
        where = f"pages/{index:04d}"
        problems += _check_page(assets, index, page, where, roster)

    problems += _check_story_refs(assets, book)
    problems += _check_reference_images(assets, characters)
    return problems


def _check_pages_contiguous(book):
    indices = [p["index"] for p in book.get("pages", [])]
    if not indices:
        return ["book.json: no pages"]
    if indices != list(range(1, len(indices) + 1)):
        return [f"book.json: page index not contiguous from 1: {indices}"]
    return []


def _check_page(assets, index, page, where, roster):
    problems = []
    if page.get("status") != ANALYZED:
        problems.append(f"{where}: status is {page.get('status')!r}, expected {ANALYZED}")
    if not page.get("panels"):
        problems.append(f"{where}: no panels")

    width, height = page.get("width", 0), page.get("height", 0)
    for panel in page.get("panels", []):
        panel_where = f"{where} panel {panel.get('id')}"
        image = os.path.join(assets.page_dir(index), panel.get("image", ""))
        if not os.path.exists(image):
            problems.append(f"{panel_where}: image missing: {panel.get('image')}")
        problems += _check_bbox(panel.get("bbox"), width, height, panel_where, "bbox")
        for region in panel.get("text_regions", []):
            problems += _check_bbox(region, width, height, panel_where, "text_region")
        problems += _check_focal_point(panel.get("focal_point"), panel_where)
        for character in panel.get("characters", []):
            if character.get("ref") not in roster:
                problems.append(f"{panel_where}: unknown character ref {character.get('ref')!r}")
    return problems


def _check_bbox(bbox, width, height, where, label):
    if not (isinstance(bbox, list) and len(bbox) == 4):
        return [f"{where}: {label} malformed: {bbox!r}"]
    x1, y1, x2, y2 = bbox
    if not (0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height):
        return [f"{where}: {label} out of page bounds ({width}x{height}): {bbox}"]
    return []


def _check_focal_point(point, where):
    if point is None:
        return []
    if not (isinstance(point, list) and len(point) == 2 and all(0 <= v <= 1 for v in point)):
        return [f"{where}: focal_point not two values in [0,1]: {point!r}"]
    return []


def _check_story_refs(assets, book):
    problems = []
    pages = {i: page for i, page in assets.pages()}
    roster = {c["id"] for c in assets.load_characters().get("characters", [])}
    story = book.get("story", {})
    if not story:
        return ["book.json: story missing (1.5 did not run)"]

    for ref in story.get("main_characters", []):
        if ref not in roster:
            problems.append(f"book.json story.main_characters: unknown ref {ref!r}")
    for beat in story.get("beats", []):
        for index in beat.get("pages", []):
            if index not in pages:
                problems.append(f"book.json beat {beat.get('beat')!r}: unknown page {index}")
    for override in story.get("skip_overrides", []):
        page = pages.get(override.get("page"))
        if page is None:
            problems.append(f"book.json skip_overrides: unknown page {override.get('page')}")
        elif not any(p["id"] == override.get("panel") for p in page.get("panels", [])):
            problems.append(
                f"book.json skip_overrides: page {override.get('page')} has no panel {override.get('panel')}"
            )
    return problems


def _check_reference_images(assets, characters):
    problems = []
    for character in characters.get("characters", []):
        for ref_image in character.get("reference_images", []):
            if not os.path.exists(os.path.join(assets.assets_dir, ref_image)):
                problems.append(f"characters.json {character['id']}: reference image missing: {ref_image}")
    return problems
