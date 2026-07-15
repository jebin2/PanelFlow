from panelflow.v2.stage1 import roster


def _chars():
    return {"characters": [
        {"id": "hooded", "name": None, "named_in_story": False, "visual": "hood",
         "first_seen": {"page": 2, "panel": 1}, "reference_images": ["a.jpg"]},
        {"id": "scarred", "name": None, "named_in_story": False, "visual": "scar",
         "first_seen": {"page": 9, "panel": 3}, "reference_images": ["b.jpg"]},
        {"id": "marcus", "name": "Marcus", "named_in_story": True, "visual": "scar",
         "named_by": {"page": 15, "panel": 4}, "first_seen": {"page": 15, "panel": 1},
         "reference_images": ["c.jpg"]},
    ]}


def test_merge_chain_collapses_to_final_target():
    chars = _chars()
    merge_map = roster.apply_merges(chars, [
        {"from_id": "hooded", "into_id": "scarred"},
        {"from_id": "scarred", "into_id": "marcus"},
    ])
    assert merge_map == {"hooded": "marcus", "scarred": "marcus"}
    assert [c["id"] for c in chars["characters"]] == ["marcus"]


def test_merge_keeps_earliest_first_seen_and_all_reference_images():
    chars = _chars()
    roster.apply_merges(chars, [{"from_id": "hooded", "into_id": "marcus"}])
    survivor = next(c for c in chars["characters"] if c["id"] == "marcus")
    assert survivor["first_seen"] == {"page": 2, "panel": 1}
    assert set(survivor["reference_images"]) == {"a.jpg", "c.jpg"}


def test_merge_ignores_unknown_and_self_targets():
    chars = _chars()
    merge_map = roster.apply_merges(chars, [
        {"from_id": "ghost", "into_id": "marcus"},
        {"from_id": "marcus", "into_id": "marcus"},
        {"from_id": "hooded", "into_id": "nobody"},
    ])
    assert merge_map == {}
    assert len(chars["characters"]) == 3


def test_merge_promotes_name_from_retired_entry():
    chars = {"characters": [
        {"id": "unnamed", "name": None, "named_in_story": False, "reference_images": [],
         "first_seen": {"page": 1, "panel": 1}},
        {"id": "named", "name": "Marcus", "named_in_story": True, "reference_images": [],
         "named_by": {"page": 5, "panel": 2}, "first_seen": {"page": 5, "panel": 1}},
    ]}
    roster.apply_merges(chars, [{"from_id": "named", "into_id": "unnamed"}])
    survivor = chars["characters"][0]
    assert survivor["name"] == "Marcus" and survivor["named_in_story"] is True
    assert survivor["named_by"] == {"page": 5, "panel": 2}


def test_updates_apply_name_alias_role_and_clear_inferred_identity():
    chars = _chars()
    roster.apply_updates(chars, [
        {"id": "hooded", "name": "Kade", "named_by_page": 7, "named_by_panel": 2},
        {"id": "marcus", "aliases": ["The Scar"], "role_in_story": "antagonist", "inferred_identity": ""},
    ])
    hooded = next(c for c in chars["characters"] if c["id"] == "hooded")
    marcus = next(c for c in chars["characters"] if c["id"] == "marcus")
    assert hooded["name"] == "Kade" and hooded["named_in_story"] is True
    assert hooded["named_by"] == {"page": 7, "panel": 2}
    assert marcus["aliases"] == ["The Scar"] and marcus["role_in_story"] == "antagonist"
    assert marcus["inferred_identity"] is None


def test_add_new_skips_ids_already_in_roster():
    chars = _chars()
    roster.add_new(chars, [
        {"id": "hooded", "visual": "dup", "first_panel": 1},
        {"id": "guard_1", "visual": "bald guard", "first_panel": 2, "name": ""},
    ], page_index=4)
    assert [c["id"] for c in chars["characters"]] == ["hooded", "scarred", "marcus", "guard_1"]
    guard = chars["characters"][-1]
    assert guard["named_in_story"] is False and guard["source"] == "visual-only"
    assert guard["first_seen"] == {"page": 4, "panel": 2}
