"""Vision via the Gemini web UI, driven in a neko docker browser.

Needs no API key — it rides the browser's Google session. The browser is kept
open across pages (`chat_fresh`, not `quick_chat`, which starts and stops a
container on every call), and each page gets a fresh conversation so context is
exactly what we put in the prompt, never leftovers from earlier pages.

Gemini has no system-instructions field, so BaseUIChat concatenates our system
and user prompts into the chat box. That box swallows 1.3's ~7.5KB without
complaint, which is the whole reason this is the only handler left: Google
Search AI Mode is a *search query*, capped at 2048 bytes, and it silently ate
73% of the prompt — every rule from "## Characters" onward never arrived, so the
model was shown an image, half a rulebook, and no panel list. It answered in
prose because it never saw the output format, and left `visual` blank because it
never saw the rule requiring it. Nothing about that was visible from the output.

If output quality ever collapses again, measure the prompt against whatever box
it is being typed into before rewriting a word of it.
"""
from custom_logger import logger_config

HANDLER = "GeminiUIChat"

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

        cfg = BrowserConfig()
        cfg.additionl_docker_flag = " ".join(
            utils.get_docker_volume_mounts(cfg, config.BASE_PATH))
        _CHAT = getattr(chat_bot_ui_handler, HANDLER)(cfg)
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
