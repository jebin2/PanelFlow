"""Sub-stage 2.1 — Direct longform.

One text call over the whole book: which panels to show, what the narrator says,
how the camera moves. No pixels — Stage 1 did the looking, and this pass is pure
reasoning over its JSON, so it can be re-run endlessly for free.
"""
from custom_logger import logger_config

from .. import llm, prompts
from . import digest, schemas

STYLE_VERSION = "v1"
TARGET = "longform"


def is_done(assets):
    direction = assets.load_direction(TARGET)
    return bool(direction.get("shots")) and direction.get("style_version") == STYLE_VERSION


def run(assets, model=None):
    if is_done(assets):
        return []
    if not assets.stage1_complete():
        raise ValueError(
            "Stage 1 is not complete (book.json.analysis.completed_at is unset). "
            "The director reads assets 1.6 has not validated."
        )

    logger_config.info("2.1 directing longform")
    book = assets.load_book()
    result = llm.ask_json(
        system_prompt=prompts.load("direct_longform"),
        user_prompt=_user_prompt(assets, book),
        schema=schemas.DIRECTION,
        model=model,
    )

    assets.save_direction(TARGET, _assemble(result, assets, book, model))
    return []


def _user_prompt(assets, book):
    story = book.get("story", {})
    return "\n\n".join([
        f'Comic: {book.get("title", assets.name)}',
        f'Story\n{"=" * 40}\n{story.get("synopsis", "")}',
        f'Beats — every one of these must be touched\n{"=" * 40}\n'
        f"{digest.beats_text(story)}",
        f'Characters\n{"=" * 40}\n{digest.roster_text(assets.load_characters())}',
        f'Pages\n{"=" * 40}\n{digest.book_text(assets)}',
    ])


def _assemble(result, assets, book, model):
    """The model's shots, with everything it does not own supplied here."""
    return {
        "schema_version": 1,
        "target": TARGET,
        "style_version": STYLE_VERSION,
        "direction_model": model or "default",
        "validated": False,      # 2.3 owns this, and it is Stage 3's gate
        "meta": result.get("meta", {}),
        "music": result.get("music", {}),
        "shots": _number(result.get("shots", [])),
    }


def _number(shots):
    """Shot ids are positions, so we assign them.

    A model asked to number a list off by one mid-way is a real failure mode,
    and the ids are what Stage 3 renders in order — there is nothing to gain by
    asking for something we can count.
    """
    numbered = []
    for shot_id, shot in enumerate(shots, start=1):
        shot["id"] = shot_id
        numbered.append(shot)
    return numbered
