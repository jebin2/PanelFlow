"""Speaker name tags: a model finds the face, the crop is arithmetic here.
These pin the crop geometry, the box convention, and that a missing face
costs nothing but the tag.
"""
import json
import os

import pytest
from PIL import Image

from panelflow.stage2 import validate
from panelflow.stage3 import nametags


class _Assets:
    def __init__(self, folder, characters):
        self.folder = str(folder)
        self.assets_dir = os.path.join(self.folder, "assets")
        self._characters = characters

    def load_characters(self):
        return {"characters": self._characters}


def _book(tmp_path, box_result):
    ref = "pages/0001/panels/panel_01.jpg"
    os.makedirs(tmp_path / "assets" / os.path.dirname(ref), exist_ok=True)
    Image.new("RGB", (1000, 800), "#446688").save(tmp_path / "assets" / ref)
    assets = _Assets(tmp_path, [{
        "id": "sid", "name": "Sid", "visual": "a brain in a jar",
        "reference_images": [ref],
    }])
    return assets


def test_a_found_face_becomes_a_square_avatar(tmp_path, monkeypatch):
    assets = _book(tmp_path, None)
    monkeypatch.setattr(nametags.llm, "ask_json",
                        lambda **kw: {"box": [200, 300, 400, 500]})  # ymin xmin ymax xmax, 0-1000

    found = nametags.avatars(assets, ["sid"])

    assert "sid" in found
    with Image.open(found["sid"]) as avatar:
        assert avatar.size == (nametags.AVATAR_SIZE, nametags.AVATAR_SIZE)


def test_avatars_are_cached_by_fingerprint(tmp_path, monkeypatch):
    assets = _book(tmp_path, None)
    calls = {"n": 0}

    def fake(**kw):
        calls["n"] += 1
        return {"box": [200, 300, 400, 500]}

    monkeypatch.setattr(nametags.llm, "ask_json", fake)
    nametags.avatars(assets, ["sid"])
    nametags.avatars(assets, ["sid"])
    assert calls["n"] == 1


def test_no_face_means_no_tag_not_a_failure(tmp_path, monkeypatch):
    assets = _book(tmp_path, None)
    monkeypatch.setattr(nametags.llm, "ask_json", lambda **kw: {"box": None})
    assert nametags.avatars(assets, ["sid"]) == {}


def test_an_unknown_speaker_is_a_validation_problem(tmp_path):
    assets = _Assets(tmp_path, [{"id": "sid", "name": "Sid"}])
    shots = [{"id": 1, "speaker": "sid"}, {"id": 2, "speaker": "someone_invented"},
             {"id": 3, "speaker": None}]
    problems = validate._check_speakers(assets, shots)
    assert problems == ["shot 2: unknown speaker 'someone_invented'"]
