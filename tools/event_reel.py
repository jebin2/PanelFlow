"""Render a labeled sample reel of every panel event, for eyeballing them.

One panel per event in `schemas.EVENTS` — the list the director composes from —
so a new event lands in the reel the moment it lands in the schema. Each panel
names its event on screen via the subtitle track and fires it once, mid-shot.

    python tools/event_reel.py                # newest book, ./event_reel.mp4
    python tools/event_reel.py <book> [out]   # a specific book / output path
"""
import glob
import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from panelflow.v2.stage2.schemas import EVENTS
from panelflow.v2.stage3.compile import EVENT_SECONDS, EVENT_SECONDS_BY_TYPE
from panelflow.v2.stage3.render import REMOTION_DIR

PANEL_SECONDS = 2.5
BOOKS = os.path.join(os.path.dirname(REMOTION_DIR), "content_to_be_processed")


def _book(argv):
    if len(argv) > 1:
        return os.path.abspath(argv[1])
    rendered = glob.glob(os.path.join(BOOKS, "*", "render", "*", "images"))
    if not rendered:
        sys.exit(f"no rendered book under {BOOKS} — pass a book folder")
    newest = max(rendered, key=os.path.getmtime)
    return os.path.dirname(os.path.dirname(os.path.dirname(newest)))


def _image(book):
    """Any rendered shot image, as a path relative to the book (the manifest's
    imageSrc convention: render_assets/ + that path)."""
    hits = sorted(glob.glob(os.path.join(book, "render", "*", "images", "*.jpg")))
    if not hits:
        sys.exit(f"{book} has no rendered shot images — render it once first")
    return os.path.relpath(hits[0], book)


def _manifest(image_rel):
    panels = []
    for name in EVENTS:
        seconds = EVENT_SECONDS_BY_TYPE.get(name, EVENT_SECONDS)
        panels.append({
            "imageSrc": f"render_assets/{image_rel}",
            "audioSrc": "",
            "durationInSeconds": PANEL_SECONDS,
            "narrationText": "",
            "sceneCaption": "",
            "animation": "ken_burns",
            "events": [{"type": name, "startSeconds": 0.6, "durationSeconds": seconds}],
            "wordTimings": [{"word": name, "start": 0.05, "end": PANEL_SECONDS - 0.05}],
        })
    return {"manifest": {
        "fps": 24, "width": 1920, "height": 1080,   # landscape: no title card
        "comicTitle": "Event reel", "panels": panels,
    }}


def main():
    book = _book(sys.argv)
    out = os.path.abspath(sys.argv[2] if len(sys.argv) > 2 else "event_reel.mp4")
    props = _manifest(_image(book))

    link = os.path.join(REMOTION_DIR, "public", "render_assets")
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(props, f)
    try:
        if os.path.islink(link):
            os.unlink(link)
        os.symlink(book, link)
        subprocess.run(
            ["npx", "remotion", "render", "ComicVideo", out,
             f"--props={f.name}", "--log=error"],
            cwd=REMOTION_DIR, check=True)
    finally:
        if os.path.islink(link):
            os.unlink(link)
        os.unlink(f.name)
    print(f"{len(EVENTS)} events x {PANEL_SECONDS}s -> {out}")


if __name__ == "__main__":
    main()
