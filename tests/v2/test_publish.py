"""3.4 — the handoff to pub_yt_x.

progress.json is a contract with another program, so these tests pin the parts
that program reads. It resolves paths against whatever root it was scanned
with, deletes the folder once it has uploaded, and reads one title per video —
none of which is visible from inside this repo.
"""
import os
from datetime import datetime, timedelta, timezone

import pytest
from PIL import Image

from panelflow.v2.paths import Assets
from panelflow.v2.stage3 import publish

WED_FRI_SUN = {2, 4, 6}


def _meta(title, page=1, panel=2):
    return {"youtube_title": title, "description": f"{title} — description",
            "twitter_post": f"{title} — tweet", "thumbnail": {"page": page, "panel": panel}}


@pytest.fixture
def book(tmp_path):
    """A book as 3.3 leaves it: two validated directions and two videos.

    Written directly rather than by running Stages 1–3: 3.4 consumes their
    output, so the output is the fixture. Neighbouring books share a parent,
    which is where the publish schedule is read from.
    """
    def build(name="Test Comic"):
        folder = tmp_path / "content" / name
        panels_dir = folder / "assets" / "pages" / "0001" / "panels"
        panels_dir.mkdir(parents=True)
        assets = Assets(str(folder))

        # Portrait panels, so a cover crop to 16:9 has to cut something. The
        # red channel names the panel, which is how the thumbnail test knows
        # which one it got.
        for panel_id in (1, 2):
            Image.new("RGB", (400, 800), (10 * panel_id, 20, 30)).save(
                str(panels_dir / f"panel_{panel_id:02d}.jpg"))

        assets.save_page(1, {"page_index": 1, "status": "analyzed", "panels": [
            {"id": 1, "image": "panels/panel_01.jpg", "bbox": [0, 0, 400, 800],
             "focal_point": [0.5, 0.5]},
            {"id": 2, "image": "panels/panel_02.jpg", "bbox": [0, 0, 400, 800],
             "focal_point": [0.5, 0.1]},
        ]})
        assets.save_book({"title": name})

        for target in ("longform", "shorts"):
            assets.save_direction(target, {
                "target": target, "validated": True, "shots": [],
                "meta": _meta(f"{target} title"), "music": {"mood": "tense"},
            })
            target_dir = folder / "render" / target
            target_dir.mkdir(parents=True)
            (target_dir / f"{target}.mp4").write_bytes(b"video")
        return assets
    return build


def test_the_publisher_is_given_both_videos_and_the_thumbnail(book):
    assets = book()

    progress = publish.run(assets)

    assert progress["LONG_VIDEO_PATH"] == assets.video_path("longform")
    assert progress["SHORTS_VIDEO_PATH"] == assets.video_path("shorts")
    assert progress["THUMBNAIL_PATH"] == assets.thumbnail_path
    assert progress["PROCESSED"] is True


def test_every_path_is_absolute(book):
    """pub_yt_x resolves a relative path against whichever root it was pointed
    at, and we cannot know that root here. An absolute path survives any root."""
    progress = publish.run(book())

    for key in ("LONG_VIDEO_PATH", "SHORTS_VIDEO_PATH", "THUMBNAIL_PATH"):
        assert os.path.isabs(progress[key])


def test_the_short_keeps_its_own_title(book):
    """2.2 wrote the short a hook-first title on purpose; handing the publisher
    only the longform's would throw that work away."""
    progress = publish.run(book())

    assert progress["YOUTUBE_TITLE"] == "longform title"
    assert progress["SHORTS_YOUTUBE_TITLE"] == "shorts title"
    assert progress["SHORTS_YT_DESCRIPTION"] == "shorts title — description"
    assert progress["TWITTER_POST"] == "shorts title — tweet"


def test_a_missing_video_is_refused(book):
    assets = book()
    os.remove(assets.video_path("shorts"))

    with pytest.raises(ValueError, match="shorts has no video"):
        publish.run(assets)


def test_the_thumbnail_is_the_panel_the_director_chose(book):
    """Panel 2, not panel 1 — v1 always took the first panel of the book."""
    assets = book()

    publish.run(assets)

    with Image.open(assets.thumbnail_path) as image:
        assert image.size == publish.THUMBNAIL_SIZE
        assert image.getpixel((960, 540))[0] == pytest.approx(20, abs=2)


def test_publishing_never_clears_what_the_publisher_wrote(book):
    """PUBLISHED is the publisher's flag and the folder's tombstone. 3.4
    rewrites this file and must not resurrect a book by dropping it."""
    assets = book()
    assets.save_progress({"PUBLISHED": True, "YOUTUBE_TITLE": "old"})

    progress = publish.run(assets)

    assert progress["PUBLISHED"] is True
    assert assets.published()


def test_a_slot_is_a_future_wednesday_friday_or_sunday(book):
    progress = publish.run(book())

    slot = datetime.strptime(progress["NEXT_ALLOWED_PUBLISH_DATETIME"],
                             publish.SLOT_FORMAT).replace(tzinfo=timezone.utc)
    assert slot.weekday() in WED_FRI_SUN
    assert slot > datetime.now(timezone.utc)
    assert (slot.hour, slot.minute) in publish.PUBLISH_TIMES


def test_a_slot_already_booked_is_kept(book):
    """Re-running 3.4 after a re-render must not move a video someone is
    already expecting on Sunday."""
    assets = book()
    booked = publish.run(assets)["NEXT_ALLOWED_PUBLISH_DATETIME"]

    assert publish.run(assets)["NEXT_ALLOWED_PUBLISH_DATETIME"] == booked


def test_a_slot_in_the_past_is_replaced(book):
    assets = book()
    stale = (datetime.now(timezone.utc) - timedelta(days=7)).strftime(publish.SLOT_FORMAT)
    assets.save_progress({"NEXT_ALLOWED_PUBLISH_DATETIME": stale})

    assert publish.run(assets)["NEXT_ALLOWED_PUBLISH_DATETIME"] != stale


def test_a_date_a_neighbour_booked_is_left_alone(book):
    """progress.json *is* the schedule — nothing else knows what is queued, so
    the neighbours are read to avoid two videos landing on one day."""
    taken = publish.run(book("Other Comic"))["NEXT_ALLOWED_PUBLISH_DATETIME"]

    mine = publish.run(book())["NEXT_ALLOWED_PUBLISH_DATETIME"]

    assert mine[:10] != taken[:10]
