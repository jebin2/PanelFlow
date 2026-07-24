"""3.4 publish: a finished book becomes a handoff the publisher can read.

Mechanical, like the rest of Stage 3 — the director already wrote the titles
and chose the thumbnail panel; this hands them over. What it writes is
`progress.json` at the comic folder root, which is the entire contract with
pub_yt_x: that tool walks any directory tree looking for that filename, so the
comic folder can live wherever it likes and no folder convention is needed.

**Paths are written absolute, deliberately.** pub_yt_x resolves relative paths
against whatever scan root it was invoked with, and we cannot know that root
from in here. Its `to_abs` returns an absolute path untouched, so absolute is
the one answer that is correct for every root.

**This file is a tombstone.** Once the upload succeeds, the publisher deletes
everything beside progress.json — cbz, assets, direction, render, all of it —
and sets `PUBLISHED`. That is the intended lifecycle: a book is disposable
once it is on the channel. `Assets.published()` is what stops Stage 1 from
walking into the wreckage and trying to re-extract from a cbz that is gone.
"""
import os
import random
from datetime import datetime, timedelta, timezone

from PIL import Image
from custom_logger import logger_config

from .. import jsonio
from . import geometry

TARGETS = ("longform", "shorts")

# YouTube's own thumbnail spec, and not related to the video's frame size —
# a short's thumbnail is this shape too.
THUMBNAIL_SIZE = (1920, 1080)
THUMBNAIL_QUALITY = 95

# Which channel this lands on. Filenames, not paths: the publisher resolves
# them against its own credential store.
YT_CREDENTIAL_FILE = "ytcrcredentials.json"
YT_TOKEN_FILE = "ytcrtoken.json"
YT_TAGS = ["ComicBreakdown", "ComicAnalysis", "ComicReview", "ComicNarration",
           "ComicStorytelling", "comics"]

# Twitter is off for comics, as it was in v1 — no credentials are configured
# for this category, and the publisher only posts text anyway. The direction's
# twitter_post rides along so that turning this on is a one-line change.
PUBLISH_IN_TWITTER = False

# The schedule: Wed/Fri/Sun, at one of two times, UTC.
PUBLISH_DAYS = {2, 4, 6}
PUBLISH_TIMES = [(3, 30), (14, 30)]
PUBLISH_HORIZON_DAYS = 30
SLOT_FORMAT = "%Y-%m-%d %H:%M:%S"


def run(assets):
    """Write progress.json and the thumbnail. Returns the progress dict."""
    for target in TARGETS:
        if not os.path.exists(assets.video_path(target)):
            raise ValueError(
                f"3.4: {target} has no video ({assets.video_path(target)}). A handoff "
                f"means the whole book is ready; render both targets first.")

    longform = assets.load_direction("longform")
    shorts = assets.load_direction("shorts")
    _thumbnail(assets, longform)

    # Whatever the publisher has already written here is its own — PUBLISHED
    # above all, which is the one flag we must never clear.
    progress = assets.load_progress()
    progress.update({
        "LONG_VIDEO_PATH": os.path.abspath(assets.video_path("longform")),
        "SHORTS_VIDEO_PATH": os.path.abspath(assets.video_path("shorts")),
        "THUMBNAIL_PATH": os.path.abspath(assets.thumbnail_path),
        "YOUTUBE_TITLE": _meta(longform, "youtube_title"),
        "YT_DESCRIPTION": _meta(longform, "description"),
        "YT_TAGS": YT_TAGS,
        # The short is its own video with its own hook — 2.2 wrote it a title
        # for a reason, and it is not the longform's.
        "SHORTS_YOUTUBE_TITLE": _meta(shorts, "youtube_title"),
        "SHORTS_YT_DESCRIPTION": _meta(shorts, "description"),
        "TWITTER_POST": _meta(shorts, "twitter_post"),
        "PROCESSED": True,
        "NEXT_ALLOWED_PUBLISH_DATETIME": _slot(assets, progress),
        "PUBLISH_IN_YT": True,
        "PUBLISH_IN_TWITTER": PUBLISH_IN_TWITTER,
        "YT_CREDENTIAL_FILE": YT_CREDENTIAL_FILE,
        "YT_TOKEN_FILE": YT_TOKEN_FILE,
        "TWITTER_CREDENTIAL_FILE": None,
        "TWITTER_TOKEN_FILE": None,
    })
    assets.save_progress(progress)
    logger_config.info(
        f'3.4: ready to publish — "{progress["YOUTUBE_TITLE"]}" at '
        f'{progress["NEXT_ALLOWED_PUBLISH_DATETIME"] or "no free slot"}')
    return progress


def _meta(direction, field):
    return ((direction.get("meta") or {}).get(field) or "").strip()


def _thumbnail(assets, direction):
    """The panel the director chose, filling a 1920x1080 frame.

    Not the first panel of the book, which is what v1 used — 2.1 picked this
    one, and 2.3 checked that it exists. Framed on the panel's focal point,
    since a cover crop always cuts something and the subject is what must
    survive.
    """
    choice = (direction.get("meta") or {}).get("thumbnail") or {}
    page_index, panel_id = choice.get("page"), choice.get("panel")
    panel = _find_panel(assets, page_index, panel_id)
    source = os.path.join(assets.page_dir(page_index), panel["image"])

    with Image.open(source) as image:
        image = image.convert("RGB")
        box = geometry.cover_box(image.size, THUMBNAIL_SIZE,
                                 panel.get("focal_point") or [0.5, 0.5])
        cropped = image.crop(box).resize(THUMBNAIL_SIZE, Image.LANCZOS)
    cropped.save(assets.thumbnail_path, "JPEG", quality=THUMBNAIL_QUALITY)
    logger_config.info(f"3.4: thumbnail from page {page_index} panel {panel_id}")


def _find_panel(assets, page_index, panel_id):
    for panel in assets.load_page(page_index).get("panels", []):
        if panel["id"] == panel_id:
            return panel
    raise ValueError(
        f"3.4: meta.thumbnail points at page {page_index} panel {panel_id}, which does "
        f"not exist. 2.3 validates this, so a direction reaching here cannot say it.")


def _slot(assets, progress):
    """When this video goes live.

    A slot already booked and still ahead of us is kept: re-running 3.4 after
    a re-render must not quietly move a video someone is expecting on Sunday.
    """
    booked = progress.get("NEXT_ALLOWED_PUBLISH_DATETIME")
    return booked if _ahead(booked) else _next_slot(assets)


def _next_slot(assets):
    """The next free Wed/Fri/Sun slot, or None inside the horizon.

    Sibling folders are read to find the taken dates, because progress.json
    *is* the schedule — nothing else knows what is already queued, and two
    videos landing the same day only compete with each other.
    """
    used = _booked_dates(assets)
    hour, minute = random.choice(PUBLISH_TIMES)
    now = datetime.now(timezone.utc)
    candidate = now.replace(hour=0, minute=0, second=0, microsecond=0)

    for _ in range(PUBLISH_HORIZON_DAYS):
        if candidate.weekday() in PUBLISH_DAYS:
            slot = candidate.replace(hour=hour, minute=minute)
            if slot > now and slot.strftime("%Y-%m-%d") not in used:
                return slot.strftime(SLOT_FORMAT)
        candidate += timedelta(days=1)
    return None


def _booked_dates(assets):
    parent = os.path.dirname(assets.folder)
    used = set()
    if not os.path.isdir(parent):
        return used
    for entry in os.scandir(parent):
        if not entry.is_dir() or os.path.abspath(entry.path) == assets.folder:
            continue
        try:
            booked = jsonio.read(os.path.join(entry.path, "progress.json"), {}).get(
                "NEXT_ALLOWED_PUBLISH_DATETIME")
        except Exception:
            continue        # a neighbour's broken file is not our problem
        if booked:
            used.add(booked[:10])
    return used


def _ahead(slot):
    try:
        return datetime.strptime(slot, SLOT_FORMAT).replace(
            tzinfo=timezone.utc) > datetime.now(timezone.utc)
    except (TypeError, ValueError):
        return False
