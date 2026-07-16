"""Text generation via our own TTT service (opencode.voidall.com).

An async job queue: submit a task, poll until it completes. Text only — no
image support, which is why vision stages use a different provider.
"""
import json
import os
import time

import requests
from custom_logger import logger_config

BASE_URL = os.environ.get("TTT_API_URL", "https://opencode.voidall.com").rstrip("/")
# "opencode" reasons far better than "qwen" (Qwen3.5:4b), which fails even the
# character-merge task, and it answers faster. Override per call if needed.
MODEL = os.environ.get("TTT_MODEL", "opencode")
POLL_SECONDS = 3
# A whole-book reconcile or director pass is a large prompt, and opencode takes
# ~5 minutes on one. This must clear the server's own opencode timeout plus time
# spent queued behind another task, or the client abandons a task the server is
# about to finish. Kept in step with the server's 600s cap.
TIMEOUT_SECONDS = 900


def generate(system_prompt, user_prompt, model=None, **_):
    task_id = _submit(system_prompt, user_prompt, model or MODEL)
    return _await_result(task_id)


def _submit(system_prompt, user_prompt, model):
    response = requests.post(
        f"{BASE_URL}/api/tasks/upload",
        json={"text": user_prompt, "system_prompt": system_prompt,
              "model": model, "hide_from_ui": True},
        timeout=30,
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
            return _unwrap(task.get("result"))
        if status == "failed":
            raise RuntimeError(f"TTT task failed: {task.get('error')}")
        logger_config.info(f"TTT {status}…", overwrite=True)
    raise TimeoutError(f"TTT task {task_id} timed out after {TIMEOUT_SECONDS}s")


def _unwrap(result):
    """The envelope differs by model: qwen returns {"text": ...}, opencode
    returns {"response": ...} and often fences the JSON in markdown."""
    if not result:
        raise RuntimeError("TTT returned an empty result")
    payload = json.loads(result) if isinstance(result, str) else result
    body = payload.get("response") or payload.get("text") or ""
    if not body:
        raise RuntimeError(f"TTT result had no text: {str(payload)[:200]}")
    return body
