"""Single entry point for LLM calls. Stage code never touches provider details.

Only Gemini enforces a response schema. TTT and the AI Studio UI return free
text, so `schema` is best-effort there and every caller filters what it gets
back — which is why the prompts spell out their JSON shape.
"""
import json_repair
from custom_logger import logger_config

from . import providers

RETRIES = 3


def ask_json(system_prompt, user_prompt, schema=None, image_path=None, model=None):
    """One stateless JSON call. Vision work (image_path) goes to the vision
    provider, everything else to the text provider. Raises after RETRIES."""
    provider = providers.vision() if image_path else providers.text()
    last_error = None

    for attempt in range(RETRIES):
        try:
            raw = provider.generate(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                image_path=image_path,
                schema=schema,
                model=model,
            )
            return _parse(raw)
        except Exception as e:
            last_error = e
            logger_config.warning(f"llm attempt {attempt + 1}/{RETRIES} failed: {e}")

    raise RuntimeError(f"LLM call failed after {RETRIES} attempts: {last_error}")


def _parse(raw):
    text = _strip_fence(raw)
    parsed = _loads(text)
    if parsed is not None:
        return parsed

    # Chat UIs answer conversationally even when told not to ("Here's the
    # analysis: {...} Would you like me to..."), so dig the object out.
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        parsed = _loads(text[start:end + 1])
        if parsed is not None:
            return parsed

    raise ValueError(f"no JSON object in response: {text[:200]!r}")


def _loads(text):
    """A non-empty dict, or None. Never raises: parsers disagree about garbage
    — json_repair salvages what it can, json.loads throws."""
    try:
        parsed = json_repair.loads(text)
    except Exception:
        return None
    return parsed if isinstance(parsed, dict) and parsed else None


def _strip_fence(raw):
    """Models that answer in chat form wrap JSON in ```json fences."""
    text = (raw or "").strip()
    if not text.startswith("```"):
        return text
    body = text.split("```")[1] if "```" in text[3:] else text[3:]
    if body.startswith("json"):
        body = body[4:]
    return body.strip()
