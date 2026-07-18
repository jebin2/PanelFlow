"""Single entry point for LLM calls. Stage code never touches provider details.

Only Gemini enforces a response schema; the browser UIs and TTT return free
text, so the prompts spell out their JSON shape and every caller filters what it
gets back.

Google Search AI Mode will not emit raw JSON at all — it renders structured
answers as formatted text. Its *content* is good (it follows the schema field by
field), so rather than fight it, a prose answer is handed to TTT to transcribe
into JSON. Seeing and serialising are different jobs.
"""
import json_repair
from custom_logger import logger_config

from . import prompts, providers

RETRIES = 3


def ask_json(system_prompt, user_prompt, schema=None, image_path=None, model=None, label=None):
    """One stateless JSON call. Vision work (image_path) goes to the vision
    provider, everything else to the text provider. `label` is a human name for
    what is being processed, shown in the provider's progress line. Raises after
    RETRIES."""
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
                label=label,
            )
            try:
                return _parse(raw)
            except ValueError:
                return reshape(system_prompt, raw)
        except Exception as e:
            last_error = e
            logger_config.warning(f"llm attempt {attempt + 1}/{RETRIES} failed: {e}")

    raise RuntimeError(f"LLM call failed after {RETRIES} attempts: {last_error}")


def reshape(system_prompt, answer):
    """Transcribe a prose answer into the JSON its instructions asked for.

    The original instructions go along for the ride because they carry the
    required shape, so there is nothing extra to keep in sync.
    """
    logger_config.info("answer was not JSON; reshaping via TTT")
    from .providers import ttt

    raw = ttt.generate(
        system_prompt=prompts.load("reshape_to_json"),
        user_prompt=(
            f"INSTRUCTIONS THE ANALYST WAS GIVEN\n{'=' * 40}\n{system_prompt}\n\n"
            f"THE ANSWER THEY WROTE\n{'=' * 40}\n{answer}"
        ),
        label="reshaping to JSON",
    )
    return _parse(raw)


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
