"""Face-crop avatars for speaker name tags.

A shot whose narration is one character's spoken line carries that character's
tag — a small face beside their name, chat-popup style. The face is not in the
data: Stage 1 recorded whole reference *panels*, usually crowd shots, so a
model finds the right face in the panel (judgement: the panel may hold ten
characters and only the `visual` description says which one) and the crop is
arithmetic, done here.

Tags are an enhancement, never a gate — a character whose face cannot be found
simply goes untagged.
"""
import hashlib
import json
import os

from PIL import Image
from custom_logger import logger_config

from .. import jsonio, llm

AVATAR_SIZE = 256
# Around the model's face box: enough to breathe (hair, chin) without pulling
# a neighbouring face into the circle.
MARGIN = 0.3

_PROMPT = """Find ONE character's face in this comic panel.

The character to find: {who}

Not every character has a human face — for those, the box is whatever stands
for their head: a mask, a helmet, a muzzle, a brain in a jar. The box is what
a viewer would recognise the character by.

Return only JSON — the bounding box normalized to 0-1000:
{{"box": [ymin, xmin, ymax, xmax]}}

Tight around the face (or its equivalent) and hair. If the character is not
visible in this panel, return {{"box": null}}."""


def avatars(assets, ids, model=None):
    """Face crops for these character ids. Returns {id: absolute jpg path};
    an id whose face cannot be produced is simply absent."""
    roster = {c["id"]: c for c in assets.load_characters().get("characters", [])}
    out_dir = os.path.join(assets.folder, "render", "characters")
    found = {}
    for cid in sorted(set(ids)):
        character = roster.get(cid)
        refs = (character or {}).get("reference_images") or []
        if not refs:
            continue
        out = os.path.join(out_dir, f"{cid}.jpg")
        meta_path = os.path.join(out_dir, f"{cid}.json")
        fingerprint = _fingerprint(character, refs)
        if os.path.exists(out) and jsonio.read(meta_path, {}).get("fingerprint") == fingerprint:
            found[cid] = out
            continue
        try:
            # Any reference may hold the recognisable view — the first is just
            # the earliest sighting, not the best one.
            for ref in refs:
                source = os.path.join(assets.assets_dir, ref)
                box = _face_box(source, character, model)
                if box:
                    os.makedirs(out_dir, exist_ok=True)
                    _crop(source, box, out)
                    jsonio.write(meta_path, {"fingerprint": fingerprint})
                    found[cid] = out
                    logger_config.info(f"3.2 nametags: cropped {cid} avatar from {ref}")
                    break
            else:
                logger_config.info(f"3.2 nametags: {cid} not visible in any reference — untagged")
        except Exception as e:
            logger_config.warning(f"3.2 nametags: {cid} failed ({e}) — untagged")
    return found


def _face_box(source, character, model):
    who = character.get("visual") or character.get("name") or character["id"]
    if character.get("name"):
        who = f'{character["name"]} — {who}'
    result = llm.ask_json(
        system_prompt=_PROMPT.format(who=who),
        user_prompt="Find the face and return its box.",
        image_path=source,
        model=model,
    )
    box = result.get("box")
    if not box or len(box) != 4:
        return None
    # Gemini's native box convention: [ymin, xmin, ymax, xmax], 0-1000.
    y0, x0, y1, x1 = [max(0.0, min(1.0, float(v) / 1000)) for v in box]
    if x1 <= x0 or y1 <= y0:
        return None
    return x0, y0, x1, y1


def _crop(source, box, out):
    """The model's face box, squared and padded, as an AVATAR_SIZE jpg."""
    with Image.open(source) as image:
        image = image.convert("RGB")
        width, height = image.size
        x0, y0, x1, y1 = box[0] * width, box[1] * height, box[2] * width, box[3] * height
        side = max(x1 - x0, y1 - y0) * (1 + MARGIN)
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        half = side / 2
        left = max(0, min(cx - half, width - side))
        top = max(0, min(cy - half, height - side))
        crop = image.crop((round(left), round(top),
                           round(min(left + side, width)), round(min(top + side, height))))
        crop.resize((AVATAR_SIZE, AVATAR_SIZE), Image.LANCZOS).save(out, "JPEG", quality=90)


def _fingerprint(character, refs):
    payload = json.dumps([refs, character.get("visual"), character.get("name")], sort_keys=True)
    return hashlib.md5(payload.encode("utf-8")).hexdigest()
