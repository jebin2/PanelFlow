"""Sub-stage 1.2 — Split.

Runs comic-panel-extractor on every page, orders panels by reading direction,
and records panel bboxes + every line of lettering OCR found in page.json.

All geometry, no meaning. The panel boxes come from the extractor and the text
boxes from OCR, so 1.3 is never asked for a pixel coordinate — asked for one it
invents it (a real run returned a text region 200px below the bottom of the
page). But the reverse holds too: which lines share a speech bubble is a
question about meaning, so 1.2 does not answer it. It records the lines and
leaves the grouping to 1.3, which can ask.
"""
import os
import re
import shlex
import shutil
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor

from custom_logger import logger_config

from panelflow import config
from .. import jsonio
from ..paths import EXTRACTED, SPLIT, status_at_least
from ..providers import ocr
from .ordering import sort_panels

REPO_URL = "https://github.com/jebin2/comic-panel-extractor.git"
# Volatile on purpose, and cheap to lose: a wiped /tmp costs one re-clone,
# which _ensure_installed does on its own. What it must not cost is a silent
# fallback — see _ensure_installed for why the binary alone cannot tell us.
REPO_PATH = "/tmp/comic-panel-extractor"
BINARY = os.path.expanduser("~/.pyenv/versions/comic-panel-extractor_env/bin/comic-panel-extractor")
# The extractor encodes each panel's bbox in its filename, but the prefix
# differs by code path: "0016_panel_(56, 74, 759, 1200).jpg" from the LLM
# extractor, "panel_1_(1006, 176, 1757, 1085).jpg" from the CV one. Match the
# "panel_...(x1, y1, x2, y2)" part and ignore whatever wraps it — debris like
# panels_visualization.jpg has no coordinates and cannot match.
BBOX_IN_NAME = re.compile(r'panel_(?:\d+_)?\((\d+),\s*(\d+),\s*(\d+),\s*(\d+)\)')
# Above this, two boxes are one panel found twice. Below it they are two panels,
# even when one sits wholly inside the other — see _drop_duplicates.
DUPLICATE_IOU = 0.7
# A panel this far inside another counts as "contained" by it; a panel that
# contains this many others is a wrapper; a wrapper the rest of the page covers
# this fully is redundant, and safe to drop. See _drop_redundant_wrappers.
CONTAINED_FRACTION = 0.8
WRAPPER_MIN_CHILDREN = 2
COVERED_FRACTION = 0.95


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

    assets.rebuild_index()

    # Any crash is fatal, because a crashed page now saves nothing: carrying on
    # would only fail in 1.3 with "page N is not split yet" and the real cause a
    # sub-stage behind it. A rerun retries exactly the pages that failed.
    if crashes:
        every = crashes == attempted and attempted > 1
        raise RuntimeError(
            f"1.2: comic-panel-extractor crashed on {crashes}/{attempted} page(s). "
            + ("That is every page it was given — the extractor is broken, not the "
               "book. Check its env (a CUDA/cudnn mismatch crashes it; "
               "USE_CPU_IF_POSSIBLE=true avoids the GPU path). " if every else "")
            + "Those pages are left unsplit rather than faked as one whole-page "
              "panel; rerun to retry them."
        )


def _split_page(assets, index, page, reading_direction):
    """Returns 1 when the extractor crashed on this page, else 0.

    A crash writes nothing at all. The page keeps its old status so a rerun
    retries it — banking a whole-page panel here would be indistinguishable
    from a legitimate cover, `is_done` would call the page finished, and the
    retry that could have fixed it would never happen.
    """
    panels_dir = assets.panels_dir(index)
    shutil.rmtree(panels_dir, ignore_errors=True)
    os.makedirs(panels_dir, exist_ok=True)

    # OCR only needs the page image, same as the extractor, and neither uses the
    # other's answer — they meet below, where each panel claims the boxes inside
    # it. So start OCR first and let it wait on the network while the extractor
    # has the CPU: its ~18s hides inside the extractor's ~30s instead of being
    # added to it.
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending_ocr = pool.submit(_ocr_lines, assets, index)

        try:
            raw_dir = _run_extractor(assets.page_image(index))
            bboxes = _parse_bboxes(raw_dir)
        except Exception as e:
            logger_config.warning(f"1.2 extractor failed on page {index}: {e}")
            return 1

        if bboxes:
            panels = _place_panels(raw_dir, bboxes, panels_dir, reading_direction)
        else:
            # Normal for covers and splashes: the extractor drops panels covering
            # ~the whole page, so it legitimately returns nothing for them. This
            # is the whole-page fallback's only remaining job — a page the
            # extractor *read* and found no panels in, not one it choked on.
            logger_config.info(f"1.2 page {index}: no panels found, using the whole page")
            panels = [_whole_page_panel(assets, index, page, panels_dir)]

        # _ocr_lines swallows its own failures, so this cannot raise.
        ocr_lines = pending_ocr.result()

    shutil.rmtree(raw_dir, ignore_errors=True)

    page["panels"] = panels
    # Where the lettering is, one box per line. 1.3 turns these into panel
    # text_regions once the model has said which lines share a bubble — a
    # question 1.2 cannot answer, having only the geometry. The text rides along
    # for that matching and is too mangled to use for anything else.
    page["ocr_lines"] = ocr_lines
    page["extraction"] = {"tool": "comic-panel-extractor", "panel_count": len(panels)}
    page["status"] = SPLIT
    assets.save_page(index, page)
    return 0


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
    """Clone and pip-install the extractor on first use.

    Both halves are checked, because either alone lies. The install is
    *editable*: site-packages holds only a .pth pointing back at REPO_PATH, so
    the repo is the package and the binary is a 285-byte stub that cannot
    import it. REPO_PATH lives in /tmp and does not survive a reboot — while
    the binary, over in its pyenv, does. Checking the binary alone therefore
    reports a healthy install for a tool that cannot start, which is exactly
    how a book once split into 22 whole-page panels.
    """
    if os.path.exists(BINARY) and os.path.isdir(REPO_PATH):
        return
    from jebin_lib import utils
    utils.setup_git_repo_get_install_pip(
        repo_url=REPO_URL, target_path=REPO_PATH, pip_name="comic-panel-extractor",
    )
    if not (os.path.exists(BINARY) and os.path.isdir(REPO_PATH)):
        raise RuntimeError(
            f"comic-panel-extractor is unavailable after install: needs both {BINARY} "
            f"and {REPO_PATH} (the editable install's source). Splitting every page "
            f"into one whole-page panel would silently ruin the video, so 1.2 stops."
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
    kept = _drop_redundant_wrappers(_drop_duplicates(bboxes))
    ordered = sort_panels([list(b) for b in kept], reading_direction)
    panels = []
    for panel_id, bbox in enumerate(ordered, start=1):
        filename = f"panel_{panel_id:02d}.jpg"
        shutil.copy2(bboxes[tuple(bbox)], os.path.join(panels_dir, filename))
        panels.append({"id": panel_id, "image": f"panels/{filename}", "bbox": list(bbox)})
    return panels


def _drop_duplicates(bboxes):
    """Drop boxes that are two detections of one panel, keeping the larger.

    Real case, page 6: 710x1132 and 613x1097 nested on top of each other, the
    same drawing found twice. Left in, the page is described twice, and the
    video shows the same panel twice in a row.

    Overlap alone cannot decide this — an inset panel sits *entirely* inside its
    parent and is a real, separate panel. IoU tells them apart, because it asks
    how much of the *union* is shared rather than how much of the smaller box
    is: the duplicate scores 0.84, while page 4's inset scores 0.13 despite
    being 100% contained.

    The larger box wins. It may carry some gutter, but the smaller one risks
    cutting the art.
    """
    kept = []
    for bbox in sorted(bboxes, key=_area, reverse=True):
        if any(_iou(bbox, other) > DUPLICATE_IOU for other in kept):
            logger_config.info(f"1.2 dropped a duplicate detection of one panel: {list(bbox)}")
            continue
        kept.append(bbox)
    return kept


def _drop_redundant_wrappers(bboxes):
    """Drop a panel that only frames others, when the others still cover it.

    The extractor sometimes returns the page border, or a tall gutter-spanning
    column, as its own "panel" — page 7 of the Harley book came back with a
    box covering 97% of the page and wrapping seven real panels inside it. A
    shot built from that box is the whole page at once, every bubble too small
    to read.

    A box is dropped only when it *contains at least two other panels* and the
    panels left behind still cover its area. That second test is the safety
    catch: a badly split page can hold content that exists *only* inside a
    wrapper — a panel the extractor never cut out on its own — and dropping
    that wrapper would lose it. Covered by the rest means redundant, and
    redundant is the only thing safe to drop.

    Largest first, re-checking after each drop, because the wrappers nest.
    """
    kept = [tuple(b) for b in bboxes]
    while len(kept) > 1:
        wrappers = [b for b in kept
                    if sum(_contained(o, b) for o in kept if o != b) >= WRAPPER_MIN_CHILDREN]
        redundant = next(
            (b for b in sorted(wrappers, key=_area, reverse=True)
             if _covered_fraction(b, [o for o in kept if o != b]) >= COVERED_FRACTION),
            None)
        if redundant is None:
            break
        logger_config.info(f"1.2 dropped a wrapper framing other panels: {list(redundant)}")
        kept.remove(redundant)
    return kept


def _contained(child, parent):
    """Most of `child` lies inside `parent`, and `child` is the smaller box."""
    child_area = _area(child)
    if not child_area or child_area >= _area(parent):
        return False
    return _intersection(child, parent) / child_area >= CONTAINED_FRACTION


def _covered_fraction(box, others, grid=60):
    """What fraction of `box` the union of `others` covers, by grid sampling.

    Sampling rather than exact rectangle union: the panels overlap arbitrarily
    on a mis-split page, and a fraction of a percent either way never changes
    the drop decision.
    """
    x1, y1, x2, y2 = box
    if x2 <= x1 or y2 <= y1:
        return 1.0
    covered = 0
    for i in range(grid):
        px = x1 + (x2 - x1) * (i + 0.5) / grid
        for j in range(grid):
            py = y1 + (y2 - y1) * (j + 0.5) / grid
            if any(o[0] <= px <= o[2] and o[1] <= py <= o[3] for o in others):
                covered += 1
    return covered / (grid * grid)


def _area(bbox):
    return max(0, bbox[2] - bbox[0]) * max(0, bbox[3] - bbox[1])


def _intersection(a, b):
    return _area((max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])))


def _iou(a, b):
    union = _area(a) + _area(b) - _intersection(a, b)
    return _intersection(a, b) / union if union else 0


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
