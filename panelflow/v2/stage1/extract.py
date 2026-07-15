"""Sub-stage 1.1 — Extract.

CBZ → pages/NNNN/page.jpg + minimal page.json + skeleton book.json + seeded
characters.json. Deterministic, no LLM, no network.
"""
import os
import re
import zipfile

from PIL import Image
from custom_logger import logger_config

from .. import comicinfo
from ..paths import EXTRACTED, SCHEMA_VERSION, status_at_least

IMAGE_EXT = ('.jpg', '.jpeg', '.png', '.webp')
SPREAD_ASPECT_RATIO = 1.3


def is_done(assets):
    # Every page the CBZ promised must be on disk and extracted. book.json is
    # required too: it carries reading_direction, which 1.2 needs, and a crash
    # mid-extract leaves fewer page dirs than page_count.
    expected = assets.load_book().get("page_count")
    pages = assets.pages()
    return (bool(expected) and len(pages) == expected
            and all(status_at_least(p.get("status", ""), EXTRACTED) for _, p in pages))


def run(assets, model=None):
    if is_done(assets):
        return

    if not os.path.exists(assets.cbz_path):
        raise FileNotFoundError(f"CBZ not found: {assets.cbz_path}")

    info = comicinfo.parse(assets.cbz_path) or {}
    members = _image_members(assets.cbz_path)
    if not members:
        raise ValueError(f"No images inside CBZ: {assets.cbz_path}")

    # Book metadata first: a crash mid-extract must not lose reading_direction,
    # which would silently re-split an RTL book left-to-right on resume.
    assets.save_book({
        "schema_version": SCHEMA_VERSION,
        "title": info.get("title") or _title_from_filename(assets.name),
        "series": info.get("series", ""),
        "publisher": info.get("publisher", ""),
        # The publisher's own blurb. Kept as book metadata for later stages to
        # use deliberately — it is marketing copy, not an observation.
        "publisher_summary": info.get("summary", ""),
        "category": "comic",
        "source": os.path.basename(assets.cbz_path),
        "page_count": len(members),
        "reading_direction": info.get("reading_direction", "ltr"),
        "pages": [],
        "story": {},
        "analysis": {},
    })
    _seed_characters(assets, info)

    with zipfile.ZipFile(assets.cbz_path) as z:
        for index, member in enumerate(members, start=1):
            _extract_page(z, member, assets, index)
            logger_config.info(f"1.1 extract page {index}/{len(members)}", overwrite=True)

    assets.rebuild_index()


def _image_members(cbz_path):
    with zipfile.ZipFile(cbz_path) as z:
        names = [n for n in z.namelist()
                 if n.lower().endswith(IMAGE_EXT) and not os.path.basename(n).startswith('.')]
    return sorted(names)


def _extract_page(zipf, member, assets, index):
    page = assets.load_page(index)
    if status_at_least(page.get("status", ""), EXTRACTED):
        return

    image_path = assets.page_image(index)
    os.makedirs(assets.page_dir(index), exist_ok=True)
    with zipf.open(member) as src:
        data = src.read()
    with open(image_path, 'wb') as dst:
        dst.write(data)

    with Image.open(image_path) as img:
        width, height = img.size
        if img.format != "JPEG":
            img.convert("RGB").save(image_path, "JPEG", quality=95)

    assets.save_page(index, {
        "schema_version": SCHEMA_VERSION,
        "page_index": index,
        "image": "page.jpg",
        "width": width,
        "height": height,
        "page_type": "cover" if index == 1 else "story",
        "is_spread": width / height > SPREAD_ASPECT_RATIO,
        "status": EXTRACTED,
        "extraction": {},
        "analysis": {},
        "panels": [],
    })


def _title_from_filename(name):
    """Last resort when the CBZ carries no usable metadata.

    Scene-release names ("... 006 (2026) (digital-mobile-Empire)") defeat tidy
    pattern rules, and the title goes into every page's prompt, so let TTT read
    it. ComicInfo always wins when present — it is ground truth, and a model can
    only add risk to it.
    """
    from .. import llm, prompts

    try:
        parsed = llm.ask_json(
            system_prompt=prompts.load("parse_title"),
            user_prompt=f"Filename: {name}",
        )
        title = (parsed.get("title") or "").strip()
        if title:
            logger_config.info(f"1.1 title from filename: {title!r}")
            return title
    except Exception as e:
        logger_config.warning(f"1.1 could not parse a title from {name!r}: {e}")
    return name


def _seed_characters(assets, info):
    if assets.load_characters().get("characters"):
        return

    seeded = [
        {
            "id": _slug(name),
            "name": name,
            "aliases": [],
            "named_in_story": True,
            "named_by": None,
            "visual": "",
            "first_seen": None,
            "reference_images": [],
            "inferred_identity": None,
            "role_in_story": None,
            "source": "comicinfo",
        }
        for name in info.get("characters", [])
    ]
    assets.save_characters({
        "schema_version": SCHEMA_VERSION,
        "seeded_from": "ComicInfo.xml" if info else None,
        "reconciled": False,
        "characters": seeded,
    })


def _slug(name):
    return re.sub(r'[^a-z0-9]+', '_', name.lower()).strip('_') or "unknown"
