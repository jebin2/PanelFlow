"""Sub-stage 1.5 — Synthesize story.

One text-only call over all analysed pages: synopsis, main characters, and the
whole-book judgments a sequential pass cannot make — beats and skip overrides.
"""
from custom_logger import logger_config

from .. import llm, prompts
from . import digest, roster, schemas

PROMPT_VERSION = "v1"


def is_done(assets):
    return bool(assets.load_book().get("story", {}).get("synopsis"))


def run(assets, model=None):
    if is_done(assets):
        return

    logger_config.info("1.5 synthesize story")
    characters = assets.load_characters()
    result = llm.ask_json(
        system_prompt=prompts.load("synthesize_story"),
        user_prompt="\n\n".join([
            f'Comic: {assets.load_book().get("title", assets.name)}',
            f"Character roster:\n{digest.roster_text(characters)}",
            f"Pages:\n{digest.pages_text(assets)}",
        ]),
        schema=schemas.STORY,
        model=model,
    )

    known_ids = roster.ids(characters)
    valid_pages = set(assets.page_indices())

    book = assets.load_book()
    book["story"] = {
        "synopsis": result.get("synopsis", ""),
        "main_characters": [r for r in result.get("main_characters", []) if r in known_ids],
        "beats": [
            {"beat": b["beat"], "pages": sorted(p for p in b.get("pages", []) if p in valid_pages)}
            for b in result.get("beats", []) if b.get("beat")
        ],
        "skip_overrides": [
            o for o in result.get("skip_overrides", [])
            if _panel_exists(assets, o.get("page"), o.get("panel"), valid_pages)
        ],
    }
    book["analysis"] = {"model": model or "default", "prompt_version": PROMPT_VERSION}
    assets.save_book(book)


def _panel_exists(assets, page_index, panel_id, valid_pages):
    if page_index not in valid_pages:
        return False
    return any(p["id"] == panel_id for p in assets.load_page(page_index).get("panels", []))
