"""Vision via a chatbot web UI, driven in a neko docker browser.

Needs no API key — it rides the browser's Google session. The browser is kept
open across pages (`chat_fresh`, not `quick_chat`, which starts and stops a
container on every call), and each page gets a fresh conversation so context is
exactly what we put in the prompt, never leftovers from earlier pages.

Handlers, selected with PANELFLOW_VISION_PROVIDER:

  google_ai  Google Search AI Mode. The default. It has no system-instructions
             field, so BaseUIChat prepends the whole system prompt into a search
             textarea (~4.3k chars for 1.3) — if answers start coming back
             truncated or as prose, that is the first thing to suspect.
  aistudio   AI Studio on gemini-3.1-pro-preview. Fills the real System
             Instructions box and takes long prompts comfortably.
"""
import os

from custom_logger import logger_config

HANDLERS = {
    "google_ai": "GoogleAISearchChat",
    "aistudio": "AIStudioUIChat",
}
HANDLER = os.environ.get("PANELFLOW_VISION_PROVIDER", "google_ai")

_CHAT = None


def generate(system_prompt, user_prompt, image_path=None, **_):
    try:
        response = _chat().chat_fresh(
            user_prompt=user_prompt, system_prompt=system_prompt, file_path=image_path)
    except Exception:
        close()
        raise
    if not response:
        # chat_bot_ui_handler swallows its own exceptions and returns None, so a
        # dead browser looks like an empty answer. Drop the session rather than
        # let every retry hit the same corpse.
        close()
        raise RuntimeError(f"{HANDLER} returned nothing (browser/session issue)")
    return response


def _chat():
    global _CHAT
    if _CHAT is None:
        import chat_bot_ui_handler
        from browser_manager.browser_config import BrowserConfig
        from jebin_lib import utils

        from panelflow import config

        if HANDLER not in HANDLERS:
            raise ValueError(f"Unknown vision handler {HANDLER!r}; pick one of {list(HANDLERS)}")

        cfg = BrowserConfig()
        cfg.additionl_docker_flag = " ".join(
            utils.get_docker_volume_mounts(cfg, config.BASE_PATH))
        _CHAT = getattr(chat_bot_ui_handler, HANDLERS[HANDLER])(cfg)
        logger_config.info(f"{HANDLER} browser session started")
    return _CHAT


def close():
    global _CHAT
    if _CHAT is not None:
        try:
            _CHAT.cleanup()
        except Exception as e:
            logger_config.warning(f"{HANDLER} session cleanup failed: {e}")
        _CHAT = None
