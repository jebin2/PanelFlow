"""LLM providers. Each exposes generate(system_prompt, user_prompt, **kw) -> str.

Text work goes to TTT (our own box, free); vision work needs a model that can
see, which TTT (Qwen3.5:4b via Ollama) cannot.

  PANELFLOW_TEXT_PROVIDER    ttt (default) | gemini
  PANELFLOW_VISION_PROVIDER  google_ai (default) | aistudio | gemini
"""
import os

TEXT_PROVIDER = os.environ.get("PANELFLOW_TEXT_PROVIDER", "ttt")
VISION_PROVIDER = os.environ.get("PANELFLOW_VISION_PROVIDER", "google_ai")


def text():
    if TEXT_PROVIDER == "gemini":
        from . import gemini
        return gemini
    from . import ttt
    return ttt


def vision():
    if VISION_PROVIDER == "gemini":
        from . import gemini
        return gemini
    from . import browser_ui
    return browser_ui
