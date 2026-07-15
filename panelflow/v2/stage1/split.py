"""Sub-stage 1.2 — Split.

Runs comic-panel-extractor on every page, orders panels by reading direction,
records bboxes (+ text_regions when the extractor produced them) in page.json.
Deterministic/ML, no LLM.
"""
import json
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
from .ordering import sort_panels

REPO_URL = "https://github.com/jebin2/comic-panel-extractor.git"
REPO_PATH = "/tmp/comic-panel-extractor"
BINARY = os.path.expanduser("~/.pyenv/versions/comic-panel-extractor_env/bin/comic-panel-extractor")
# Extractor writes: panel_<n>_(x1, y1, x2, y2).jpg
BBOX_IN_NAME = re.compile(r'^panel_\d+_\((\d+),\s*(\d+),\s*(\d+),\s*(\d+)\)\.\w+$')


def is_done(assets):
    pages = assets.pages()
    return bool(pages) and all(status_at_least(p.get("status", ""), SPLIT) for _, p in pages)


def run(assets, model=None):
    if is_done(assets):
        return

    reading_direction = assets.load_book().get("reading_direction", "ltr")
    indices = assets.page_indices()
    for index in indices:
        page = assets.load_page(index)
        if status_at_least(page.get("status", ""), SPLIT):
            continue
        logger_config.info(f"1.2 split page {index}/{len(indices)}", overwrite=True)
        _split_page(assets, index, page, reading_direction)
    assets.rebuild_index()


def _split_page(assets, index, page, reading_direction):
    panels_dir = assets.panels_dir(index)
    shutil.rmtree(panels_dir, ignore_errors=True)
    os.makedirs(panels_dir, exist_ok=True)

    try:
        raw_dir = _run_extractor(assets.page_image(index))
        bboxes = _parse_bboxes(raw_dir)
    except Exception as e:
        logger_config.warning(f"1.2 extractor failed on page {index}, using whole page: {e}")
        raw_dir, bboxes = None, []

    if bboxes:
        panels = _place_panels(raw_dir, bboxes, panels_dir, reading_direction)
    else:
        # Normal for covers and splashes: the extractor drops panels covering
        # ~the whole page, so it legitimately returns nothing for them.
        logger_config.info(f"1.2 page {index}: no panels found, using the whole page")
        panels = [_whole_page_panel(assets, index, page, panels_dir)]

    text_regions = _load_text_regions(raw_dir)
    for panel in panels:
        panel["text_regions"] = [r for r in text_regions if _inside(r, panel["bbox"])]

    if raw_dir:
        shutil.rmtree(raw_dir, ignore_errors=True)

    page["panels"] = panels
    page["extraction"] = {"tool": "comic-panel-extractor", "panel_count": len(panels)}
    page["status"] = SPLIT
    assets.save_page(index, page)


def _run_extractor(image_path):
    _ensure_installed()
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
    if os.path.isdir(REPO_PATH):
        return
    from jebin_lib import utils
    utils.setup_git_repo_get_install_pip(
        repo_url=REPO_URL, target_path=REPO_PATH, pip_name="comic-panel-extractor",
    )


def _parse_bboxes(raw_dir):
    """{[x1,y1,x2,y2]: source_file} for every panel image the extractor wrote."""
    found = {}
    for name in os.listdir(raw_dir):
        match = BBOX_IN_NAME.match(name)
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


def _load_text_regions(raw_dir):
    """Speech-bubble bboxes, when the extractor's text detector ran (it is
    disabled upstream today; 1.3's vision model fills these in otherwise)."""
    if not raw_dir:
        return []
    path = next((os.path.join(raw_dir, n) for n in os.listdir(raw_dir)
                 if "text" in n.lower() and n.endswith(".json")), None)
    if not path:
        return []
    try:
        return [entry["bbox"] for entry in json.load(open(path, encoding="utf-8")) if "bbox" in entry]
    except (json.JSONDecodeError, KeyError, TypeError):
        return []


def _inside(region, bbox):
    """Region's centre falls within the panel bbox."""
    cx, cy = (region[0] + region[2]) / 2, (region[1] + region[3]) / 2
    return bbox[0] <= cx <= bbox[2] and bbox[1] <= cy <= bbox[3]
