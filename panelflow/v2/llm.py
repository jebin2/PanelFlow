"""Single entry point for LLM calls. Stage code never touches provider details."""
import json_repair
from custom_logger import logger_config

from panelflow import config
from panelflow.pipeline.gemini_config import pre_model_wrapper

RETRIES = 3


def ask_json(system_prompt, user_prompt, schema, image_path=None, model=None):
    """One stateless JSON call. Returns the parsed dict, raises after RETRIES."""
    last_error = None
    for attempt in range(RETRIES):
        try:
            wrapper = pre_model_wrapper(
                model_name=model or config.MODEL_NAME,
                system_instruction=system_prompt,
                schema=schema,
            )
            responses = wrapper.send_message(user_prompt=user_prompt, file_path=image_path)
            if not responses or not responses[0]:
                raise ValueError("empty response")
            parsed = json_repair.loads(responses[0])
            if not isinstance(parsed, dict):
                raise ValueError(f"expected a JSON object, got {type(parsed).__name__}")
            return parsed
        except Exception as e:
            last_error = e
            logger_config.warning(f"llm attempt {attempt + 1}/{RETRIES} failed: {e}")
    raise RuntimeError(f"LLM call failed after {RETRIES} attempts: {last_error}")
