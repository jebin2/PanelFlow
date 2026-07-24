"""Where the lettering is, via our OCR service (jebin2-ocr.hf.space, PaddleOCR).

Same async job queue as TTT: upload an image, poll until it completes.

We take the **boxes and ignore the text**. PaddleOCR's geometry is ground truth,
but it mangles stylised comic lettering ("THE SANCTUM SANCTORUM" comes back as
"THESANGTOMSANGTORUM"), so transcription stays with the vision model, which
reads it well. Boxes are the thing a vision model cannot do: asked for pixel
coordinates it invents them, off the page as often as not.

Measuring is all this does. It reports one box per *line*, and does not try to
say which lines share a bubble: that is a question about who is speaking, not
about pixels, and it lives in 1.3 where a model can be asked. This module once
guessed at it with a gap threshold — 70% of a line's height — and on a real page
it welded two characters' bubbles into one box, because two speakers trading
one-liners sit exactly as close as two lines of one speech.
"""
import json
import os
import time

import requests
from custom_logger import logger_config

BASE_URL = os.environ.get("OCR_API_URL", "https://jebin2-ocr.hf.space").rstrip("/")
MIN_CONFIDENCE = 0.5
POLL_SECONDS = 3
TIMEOUT_SECONDS = 300


def lines(image_path):
    """[{"text": ..., "box": [x1, y1, x2, y2]}, ...] — one entry per line of
    text, as OCR found it.

    The text is kept only so 1.3 can match these boxes to the dialogue the
    vision model read correctly; it is too mangled to use as transcription.
    """
    task_id = _submit(image_path)
    return [{"text": text, "box": _to_bbox(box)} for text, box in _await_result(task_id)]


def _submit(image_path):
    with open(image_path, "rb") as f:
        response = requests.post(
            f"{BASE_URL}/api/tasks/upload",
            files={"image": (os.path.basename(image_path), f, "image/jpeg")},
            timeout=60,
        )
    response.raise_for_status()
    return response.json()["id"]


def _await_result(task_id):
    deadline = time.monotonic() + TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        time.sleep(POLL_SECONDS)
        task = requests.get(f"{BASE_URL}/api/tasks/{task_id}", timeout=30).json()
        status = task.get("status")
        if status == "completed":
            return _entries(task.get("result"))
        if status == "failed":
            raise RuntimeError(f"OCR task failed: {task.get('error')}")
    raise TimeoutError(f"OCR task {task_id} timed out after {TIMEOUT_SECONDS}s")


def _entries(result):
    """[(text, quad), ...] for every confident text run."""
    if not result:
        return []
    payload = json.loads(result) if isinstance(result, str) else result
    return [
        (entry.get("text", ""), entry["box"]) for entry in payload.get("results", [])
        if entry.get("box") and entry.get("confidence", 0) >= MIN_CONFIDENCE
    ]


def _to_bbox(box):
    """PaddleOCR gives four corners; we want [x1, y1, x2, y2]."""
    xs = [int(point[0]) for point in box]
    ys = [int(point[1]) for point in box]
    return [min(xs), min(ys), max(xs), max(ys)]


def available():
    try:
        return requests.get(f"{BASE_URL}/health", timeout=10).json().get("status") == "healthy"
    except Exception as e:
        logger_config.warning(f"OCR service unreachable: {e}")
        return False
