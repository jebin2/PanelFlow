"""Sub-stages 2.1 and 2.2 — Direct.

One text call per target over the whole book: which panels to show, what the
narrator says, how the camera moves. No pixels — Stage 1 did the looking, so
this is pure reasoning over its JSON and can be re-run endlessly for free.

Longform and shorts are separate calls, not one call answering twice. Their
philosophies are opposed — longform covers the story at an even pace, shorts is
hook-first and cuts to the bone — and a prompt asked to do both does both worse.
They read exactly the same book, though, so the difference lives entirely in the
system prompt and nothing here needs to know which is running.
"""
from custom_logger import logger_config

from .. import llm, prompts
from . import digest, normalize, schemas

STYLE_VERSION = "v1"

# target -> the prompt that gives it its philosophy.
TARGETS = {
    "longform": "direct_longform",
    "shorts": "direct_shorts",
}


def is_done(assets, target):
    direction = assets.load_direction(target)
    return bool(direction.get("shots")) and direction.get("style_version") == STYLE_VERSION


def run(assets, target, model=None):
    if is_done(assets, target):
        return []
    if not assets.stage1_complete():
        raise ValueError(
            "Stage 1 is not complete (book.json.analysis.completed_at is unset). "
            "The director reads assets 1.6 has not validated."
        )

    logger_config.info(f"directing {target}")
    result = llm.ask_json(
        system_prompt=prompts.load(TARGETS[target]),
        user_prompt=_user_prompt(assets),
        schema=schemas.DIRECTION,
        model=model,
        label=f"directing {target}",
    )

    assets.save_direction(target, _assemble(result, target, model))
    return []


def _user_prompt(assets):
    """The same book for both targets — what to do with it is the prompt's job."""
    book = assets.load_book()
    story = book.get("story", {})
    return "\n\n".join([
        f'Comic: {book.get("title", assets.name)}',
        f'Story\n{"=" * 40}\n{story.get("synopsis", "")}',
        f'Beats\n{"=" * 40}\n{digest.beats_text(story)}',
        f'Characters\n{"=" * 40}\n{digest.roster_text(assets.load_characters())}',
        f'Pages\n{"=" * 40}\n{digest.book_text(assets)}',
    ])


def _assemble(result, target, model):
    """The model's shots, with everything it does not own supplied here."""
    return {
        "schema_version": 1,
        "target": target,
        "style_version": STYLE_VERSION,
        "direction_model": model or "default",
        "validated": False,      # 2.3 owns this, and it is Stage 3's gate
        "meta": result.get("meta", {}),
        "music": result.get("music", {}),
        "shots": normalize.normalize_shots(result.get("shots", [])),
    }
