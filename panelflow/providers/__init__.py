"""LLM providers. Each exposes generate(system_prompt, user_prompt, **kw) -> str.

Text work goes to TTT (our own box, free); vision work needs a model that can
see, which TTT (Qwen3.5:4b via Ollama) cannot.

  PANELFLOW_TEXT_PROVIDER    ttt (default) | gemini

Vision is not selectable: it is always the Gemini web UI, which needs no API
key. Note that `gemini` as a *text* provider means the Gemini API and does need
GEMINI_API_KEY — a different thing entirely from the browser UI.
"""
import os

TEXT_PROVIDER = os.environ.get("PANELFLOW_TEXT_PROVIDER", "ttt")


def text():
    if TEXT_PROVIDER == "gemini":
        from . import gemini
        return gemini
    from . import ttt
    return ttt


def vision():
    from . import browser_ui
    return browser_ui
