"""Sub-stage 1.2 — Split.

Runs comic-panel-extractor on every page, orders panels by reading direction,
and records panel bboxes + speech-bubble text_regions in page.json.

All geometry, no meaning: the panel boxes come from the extractor and the text
boxes from OCR, so 1.3 is never asked for a pixel coordinate — asked for one it
invents it (a real run returned a text region 200px below the bottom of the
page).
"""
import os
import re
import shlex
import shutil
import subprocess
import tempfile

from custom_logger import logger_config

from panelflow import config
from .. import jsonio
from ..paths import EXTRACTED, SPLIT, status_at_least
from ..providers import ocr
from .ordering import sort_panels

REPO_URL = "https://github.com/jebin2/comic-panel-extractor.git"
REPO_PATH = "/tmp/comic-panel-extractor"
BINARY = os.path.expanduser("~/.pyenv/versions/comic-panel-extractor_env/bin/comic-panel-extractor")
# The extractor encodes each panel's bbox in its filename, but the prefix
# differs by code path: "0016_panel_(56, 74, 759, 1200).jpg" from the LLM
# extractor, "panel_1_(1006, 176, 1757, 1085).jpg" from the CV one. Match the
# "panel_...(x1, y1, x2, y2)" part and ignore whatever wraps it — debris like
# panels_visualization.jpg has no coordinates and cannot match.
BBOX_IN_NAME = re.compile(r'panel_(?:\d+_)?\((\d+),\s*(\d+),\s*(\d+),\s*(\d+)\)')


def is_done(assets):
    pages = assets.pages()
    return bool(pages) and all(status_at_least(p.get("status", ""), SPLIT) for _, p in pages)


def run(assets, model=None):
    if is_done(assets):
        return

    # Once per book, and loudly: a missing extractor is systemic, not a
    # per-page hiccup. Without this, every page would quietly fall back to a
    # single whole-page panel and Stage 1 would report success on a book that
    # can never produce panel-level camera work.
    _ensure_installed()

    reading_direction = assets.load_book().get("reading_direction", "ltr")
    indices = assets.page_indices()
    crashes = 0
    attempted = 0
    for index in indices:
        page = assets.load_page(index)
        if status_at_least(page.get("status", ""), SPLIT):
            continue
        logger_config.info(f"1.2 split page {index}/{len(indices)}", overwrite=True)
        attempted += 1
        crashes += _split_page(assets, index, page, reading_direction)

    # One page defeating the extractor is a page problem; every page defeating
    # it is a broken tool, and 19 whole-page "panels" would sail through 1.6 and
    # quietly produce a video with no panel-level camera work at all.
    if attempted > 1 and crashes == attempted:
        raise RuntimeError(
            f"comic-panel-extractor crashed on all {attempted} pages — it is broken, "
            f"not the book. Check the extractor env (a CUDA/cudnn mismatch crashes it; "
            f"USE_CPU_IF_POSSIBLE=true avoids the GPU path)."
        )
    if crashes:
        logger_config.warning(f"1.2 extractor crashed on {crashes}/{attempted} page(s)")
    assets.rebuild_index()


def _split_page(assets, index, page, reading_direction):
    """Returns 1 when the extractor crashed on this page, else 0."""
    panels_dir = assets.panels_dir(index)
    shutil.rmtree(panels_dir, ignore_errors=True)
    os.makedirs(panels_dir, exist_ok=True)

    crashed = 0
    try:
        raw_dir = _run_extractor(assets.page_image(index))
        bboxes = _parse_bboxes(raw_dir)
    except Exception as e:
        logger_config.warning(f"1.2 extractor failed on page {index}, using whole page: {e}")
        raw_dir, bboxes, crashed = None, [], 1

    if bboxes:
        panels = _place_panels(raw_dir, bboxes, panels_dir, reading_direction)
    else:
        # Normal for covers and splashes: the extractor drops panels covering
        # ~the whole page, so it legitimately returns nothing for them.
        logger_config.info(f"1.2 page {index}: no panels found, using the whole page")
        panels = [_whole_page_panel(assets, index, page, panels_dir)]

    ocr_lines = _ocr_lines(assets, index)
    regions = ocr.group([line["box"] for line in ocr_lines])
    for panel in panels:
        panel["text_regions"] = [r for r in regions if _inside(r, panel["bbox"])]

    if raw_dir:
        shutil.rmtree(raw_dir, ignore_errors=True)

    page["panels"] = panels
    # Kept for 1.3, which matches these boxes to the dialogue the vision model
    # read correctly. The text is too mangled to use for anything else.
    page["ocr_lines"] = ocr_lines
    page["extraction"] = {"tool": "comic-panel-extractor", "panel_count": len(panels)}
    page["status"] = SPLIT
    assets.save_page(index, page)
    return crashed


def _run_extractor(image_path):
    out_dir = tempfile.mkdtemp(prefix="panelsplit_")
    cfg_path = os.path.join(out_dir, "config.json")
    jsonio.write(cfg_path, {"input_path": image_path, "output_folder": out_dir})

    result = subprocess.run(
        ["bash", "-c", f"{shlex.quote(BINARY)} --config {shlex.quote(cfg_path)}"],
        cwd=REPO_PATH, text=True, capture_output=True, env=config.SUBPROCESS_ENV,
    )
    if result.returncode != 0:
        raise RuntimeError(f"comic-panel-extractor exited {result.returncode}: {result.stderr[-400:]}")
    return out_dir


def _ensure_installed():
    """Clone and pip-install the extractor on first use. Checks for the binary
    we actually invoke, so a half-finished install is not mistaken for success."""
    if os.path.exists(BINARY):
        return
    from jebin_lib import utils
    utils.setup_git_repo_get_install_pip(
        repo_url=REPO_URL, target_path=REPO_PATH, pip_name="comic-panel-extractor",
    )
    if not os.path.exists(BINARY):
        raise RuntimeError(
            f"comic-panel-extractor is unavailable after install: {BINARY} not found. "
            f"Splitting every page into one whole-page panel would silently ruin the "
            f"video, so Stage 1.2 stops here."
        )


def _parse_bboxes(raw_dir):
    """{[x1,y1,x2,y2]: source_file} for every panel image the extractor wrote."""
    found = {}
    for name in os.listdir(raw_dir):
        match = BBOX_IN_NAME.search(name)
        if match:
            found[tuple(int(g) for g in match.groups())] = os.path.join(raw_dir, name)
    return found


def _place_panels(raw_dir, bboxes, panels_dir, reading_direction):
    ordered = sort_panels([list(b) for b in bboxes.keys()], reading_direction)
    panels = []
    for panel_id, bbox in enumerate(ordered, start=1):
        filename = f"panel_{panel_id:02d}.jpg"
        shutil.copy2(bboxes[tuple(bbox)], os.path.join(panels_dir, filename))
        panels.append({"id": panel_id, "image": f"panels/{filename}", "bbox": list(bbox)})
    return panels


def _whole_page_panel(assets, index, page, panels_dir):
    """Cover/splash/failed extraction: the page itself is its single panel."""
    filename = "panel_01.jpg"
    shutil.copy2(assets.page_image(index), os.path.join(panels_dir, filename))
    return {"id": 1, "image": f"panels/{filename}", "bbox": [0, 0, page["width"], page["height"]]}


def _ocr_lines(assets, index):
    """Every line of text OCR found, with its box, once per page.

    Not fatal when it fails: without them the director has no lettering to avoid
    cropping through, which makes for worse video, not wrong data.
    """
    try:
        return ocr.lines(assets.page_image(index))
    except Exception as e:
        logger_config.warning(f"1.2 OCR failed on page {index}, no text regions: {e}")
        return []


def _inside(region, bbox):
    """Region's centre falls within the panel bbox."""
    cx, cy = (region[0] + region[2]) / 2, (region[1] + region[3]) / 2
    return bbox[0] <= cx <= bbox[2] and bbox[1] <= cy <= bbox[3]
