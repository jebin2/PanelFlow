"""Text-region detection via our OCR service (jebin2-ocr.hf.space, PaddleOCR).

Same async job queue as TTT: upload an image, poll until it completes.

We take the **boxes and ignore the text**. PaddleOCR's geometry is ground truth,
but it mangles stylised comic lettering ("THE SANCTUM SANCTORUM" comes back as
"THESANGTOMSANGTORUM"), so transcription stays with the vision model, which
reads it well. Boxes are the thing a vision model cannot do: asked for pixel
coordinates it invents them, off the page as often as not.
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


def text_regions(image_path):
    """[[x1, y1, x2, y2], ...] for every text run found on the page."""
    task_id = _submit(image_path)
    boxes = _await_result(task_id)
    return [_to_bbox(b) for b in boxes]


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
            return _boxes(task.get("result"))
        if status == "failed":
            raise RuntimeError(f"OCR task failed: {task.get('error')}")
    raise TimeoutError(f"OCR task {task_id} timed out after {TIMEOUT_SECONDS}s")


def _boxes(result):
    if not result:
        return []
    payload = json.loads(result) if isinstance(result, str) else result
    return [
        entry["box"] for entry in payload.get("results", [])
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
