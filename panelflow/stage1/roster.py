"""characters.json read/write helpers. Owns roster shape, nothing else."""
from custom_logger import logger_config

ROLES = ("protagonist", "antagonist", "supporting", "background")


def ids(characters):
    return {c["id"] for c in characters.get("characters", [])}


def describe_for_prompt(characters):
    """The roster as the analyser sees it: id, name, and what they look like.

    The visual is the whole point — without it there is nothing to match a face
    on the next page against, and the analyser can only register duplicates."""
    entries = characters.get("characters", [])
    if not entries:
        return "(empty — every character you see is new)"
    lines = []
    for c in entries:
        name = f' name="{c["name"]}"' if c.get("name") else " (unnamed in story)"
        visual = f' looks like: {c["visual"]}' if c.get("visual") else " (no description recorded)"
        lines.append(f'- {c["id"]}{name}{visual}')
    return "\n".join(lines)


def add_new(characters, new_entries, page_index):
    """Append characters registered by a page analysis. Existing ids win."""
    known = ids(characters)
    for entry in new_entries:
        slug = entry.get("id")
        if not slug or slug in known:
            continue
        if not entry.get("visual"):
            # Later pages match against this description; without one the
            # analyser can only keep registering the same character again.
            logger_config.warning(
                f"1.3 page {page_index}: character {slug!r} registered with no visual "
                f"description — it cannot be matched on later pages")
        named_by_panel = entry.get("named_by_panel") or 0
        # Panels are 1-indexed on disk (panel_01.jpg …). first_panel is 0 when
        # the analyser named a character it could not pin to a drawn panel — one
        # spoken of, off-panel. That earns no crop: panel_00 never exists, and a
        # fallback crop would put the wrong face on her. No reference is honest,
        # and Stage 3 already drops the nametag for a face it does not have.
        first_panel = entry.get("first_panel", 1)
        has_panel = isinstance(first_panel, int) and first_panel >= 1
        characters.setdefault("characters", []).append({
            "id": slug,
            "name": entry.get("name") or None,
            "aliases": [],
            "named_in_story": bool(entry.get("name")),
            "named_by": {"page": page_index, "panel": named_by_panel} if named_by_panel else None,
            "visual": entry.get("visual", ""),
            "first_seen": {"page": page_index, "panel": first_panel if has_panel else None},
            "reference_images": (
                [f"pages/{page_index:04d}/panels/panel_{first_panel:02d}.jpg"]
                if has_panel else []),
            "inferred_identity": entry.get("inferred_identity") or None,
            "role_in_story": None,
            "source": "dialogue" if entry.get("name") else "visual-only",
        })
        known.add(slug)
    return characters


def apply_merges(characters, merges):
    """Retire from_id into into_id. Returns {retired_id: surviving_id}."""
    valid = ids(characters)
    merge_map = {m["from_id"]: m["into_id"] for m in merges
                 if m.get("from_id") in valid and m.get("into_id") in valid
                 and m["from_id"] != m["into_id"]}
    # Collapse chains (a→b, b→c  ⇒  a→c)
    for retired in list(merge_map):
        seen = {retired}
        target = merge_map[retired]
        while target in merge_map and target not in seen:
            seen.add(target)
            target = merge_map[target]
        merge_map[retired] = target

    survivors = []
    for c in characters.get("characters", []):
        if c["id"] in merge_map:
            _absorb(next(s for s in characters["characters"] if s["id"] == merge_map[c["id"]]), c)
        else:
            survivors.append(c)
    characters["characters"] = survivors
    return merge_map


def _absorb(survivor, retired):
    """Keep the retired entry's grounded facts on the surviving entry."""
    survivor["reference_images"] = list(dict.fromkeys(
        survivor.get("reference_images", []) + retired.get("reference_images", [])))
    if retired.get("name") and not survivor.get("name"):
        survivor["name"] = retired["name"]
        survivor["named_in_story"] = True
        survivor["named_by"] = retired.get("named_by")
    if _earlier(retired.get("first_seen"), survivor.get("first_seen")):
        survivor["first_seen"] = retired["first_seen"]


def _earlier(a, b):
    if not a:
        return False
    if not b:
        return True
    return (a["page"], a.get("panel", 0)) < (b["page"], b.get("panel", 0))


def apply_updates(characters, updates):
    by_id = {c["id"]: c for c in characters.get("characters", [])}
    for update in updates:
        character = by_id.get(update.get("id"))
        if not character:
            continue
        if update.get("name"):
            character["name"] = update["name"]
            character["named_in_story"] = True
            if update.get("named_by_page"):
                character["named_by"] = {"page": update["named_by_page"], "panel": update.get("named_by_panel", 0)}
            if character.get("source") == "visual-only":
                character["source"] = "dialogue"
        if update.get("aliases"):
            character["aliases"] = list(dict.fromkeys(character.get("aliases", []) + update["aliases"]))
        # Providers without schema enforcement answer this freely
        # ("fugitive pursued by guards"); only the enum may land on disk.
        if update.get("role_in_story") in ROLES:
            character["role_in_story"] = update["role_in_story"]
        if "inferred_identity" in update:
            character["inferred_identity"] = update["inferred_identity"] or None
        if update.get("relationships"):
            # Grounded like names: only relations to someone actually in the
            # roster survive, so the narration can never lean on a phantom.
            character["relationships"] = [
                {"to_id": r["to_id"], "relation": r["relation"],
                 "evidence": r.get("evidence", "")}
                for r in update["relationships"]
                if r.get("to_id") in by_id and (r.get("relation") or "").strip()]
    return characters
