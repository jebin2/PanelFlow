"""Render a labeled sample reel of every transition, for eyeballing them.

One panel per name in `schemas.TRANSITIONS` — the list the director composes
from — so a new transition lands in the reel the moment it lands in the schema.
Each panel *enters* with its transition and names it on screen via the subtitle
track. Panels run ken_burns, which downgrades nothing, so every transition
plays as itself.

    python tools/transition_reel.py                # newest book, ./transition_reel.mp4
    python tools/transition_reel.py <book> [out]   # a specific book / output path
"""
import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from panelflow.stage2.schemas import TRANSITIONS
from panelflow.stage3.render import REMOTION_DIR
from tools.event_reel import _book

PANEL_SECONDS = 2.5


def _images(book):
    """Two different shot images, so each seam visibly changes picture — a
    transition between two copies of the same image renders as nothing."""
    import glob
    hits = sorted(glob.glob(os.path.join(book, "render", "*", "images", "*.jpg")))
    if len(hits) < 2:
        sys.exit(f"{book} needs two rendered shot images — render it once first")
    return [os.path.relpath(p, book) for p in hits[:2]]


def _manifest(images_rel):
    panels = []
    for i, name in enumerate(TRANSITIONS):
        panels.append({
            "imageSrc": f"render_assets/{images_rel[i % 2]}",
            "audioSrc": "",
            "durationInSeconds": PANEL_SECONDS,
            "narrationText": "",
            "sceneCaption": "",
            "animation": "ken_burns",
            "transitionIn": name,
            "wordTimings": [{"word": name, "start": 0.05, "end": PANEL_SECONDS - 0.05}],
        })
    return {"manifest": {
        "fps": 24, "width": 1920, "height": 1080,   # landscape: no title card
        "comicTitle": "Transition reel", "panels": panels,
    }}


def main():
    book = _book(sys.argv)
    out = os.path.abspath(sys.argv[2] if len(sys.argv) > 2 else "transition_reel.mp4")
    props = _manifest(_images(book))

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
    print(f"{len(TRANSITIONS)} transitions x {PANEL_SECONDS}s -> {out}")


if __name__ == "__main__":
    main()
