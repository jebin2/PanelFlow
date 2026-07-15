"""Sub-stage 1.4 — Reconcile characters.

One text-only call over the whole book: merge duplicate entries, promote names
grounded by late dialogue, link aliases, settle one inferred_identity per
character, infer roles. Then rewrite every panel ref through the merge map.
"""
from custom_logger import logger_config

from .. import llm, prompts
from ..paths import invalidate_downstream
from . import digest, roster, schemas


def is_done(assets):
    return bool(assets.load_characters().get("reconciled"))


def run(assets, model=None):
    if is_done(assets):
        return

    characters = assets.load_characters()
    if not characters.get("characters"):
        characters["reconciled"] = True
        assets.save_characters(characters)
        return

    logger_config.info("1.4 reconcile characters")
    result = llm.ask_json(
        system_prompt=prompts.load("reconcile_characters"),
        user_prompt="\n\n".join([
            f'Comic: {assets.load_book().get("title", assets.name)}',
            f"Character roster:\n{digest.roster_text(characters)}",
            f"Drawn together in one panel — almost never the same character:\n"
            f"{digest.distinct_pairs_text(assets)}",
            f"Pages:\n{digest.pages_text(assets, with_evidence=True)}",
        ]),
        schema=schemas.RECONCILE,
        model=model,
    )

    merge_map = roster.apply_merges(characters, result.get("merges", []))
    roster.apply_updates(characters, result.get("updates", []))
    characters["reconciled"] = True
    assets.save_characters(characters)

    if merge_map:
        _rewrite_panel_refs(assets, merge_map)
        logger_config.info(f"1.4 merged {len(merge_map)} character(s): {merge_map}")

    invalidate_downstream(assets)


def _rewrite_panel_refs(assets, merge_map):
    for index, page in assets.pages():
        changed = False
        for panel in page.get("panels", []):
            seen = set()
            kept = []
            for character in panel.get("characters", []):
                ref = merge_map.get(character.get("ref"), character.get("ref"))
                if ref != character.get("ref"):
                    character["ref"] = ref
                    changed = True
                if ref in seen:          # merge collapsed two refs into one panel
                    changed = True
                    continue
                seen.add(ref)
                kept.append(character)
            panel["characters"] = kept
        if changed:
            assets.save_page(index, page)
