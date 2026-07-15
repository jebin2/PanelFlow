"""Vision via the AI Studio web UI, driven in a neko docker browser.

Needs no API key — it rides the browser's Google session. The browser is kept
open across pages (`chat`, not `quick_chat`, which starts and stops a container
on every call), and each page gets a fresh conversation so context is exactly
what we put in the prompt, never leftovers from earlier pages.
"""
from custom_logger import logger_config

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
        raise RuntimeError("AI Studio returned nothing (browser/session issue)")
    return response


def _chat():
    global _CHAT
    if _CHAT is None:
        from browser_manager.browser_config import BrowserConfig
        from chat_bot_ui_handler import AIStudioUIChat
        from jebin_lib import utils

        from panelflow import config

        cfg = BrowserConfig()
        cfg.additionl_docker_flag = " ".join(
            utils.get_docker_volume_mounts(cfg, config.BASE_PATH))
        _CHAT = AIStudioUIChat(cfg)
        logger_config.info("AI Studio browser session started")
    return _CHAT


def close():
    global _CHAT
    if _CHAT is not None:
        try:
            _CHAT.cleanup()
        except Exception as e:
            logger_config.warning(f"AI Studio session cleanup failed: {e}")
        _CHAT = None
