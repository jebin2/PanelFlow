"""Gemini via gemiwrap. Needs GEMINI_API_KEY; handles both text and vision."""
from panelflow import config
from .gemini_config import pre_model_wrapper


def generate(system_prompt, user_prompt, image_path=None, schema=None, model=None, **_):
    wrapper = pre_model_wrapper(
        model_name=model or config.MODEL_NAME,
        system_instruction=system_prompt,
        schema=schema,
    )
    responses = wrapper.send_message(user_prompt=user_prompt, file_path=image_path)
    if not responses or not responses[0]:
        raise RuntimeError("Gemini returned an empty response")
    return responses[0]
