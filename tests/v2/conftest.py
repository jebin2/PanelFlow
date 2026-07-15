"""Stubs for project libs that live outside this repo, so Stage 1's pure logic
is testable anywhere. Real runs use the installed packages."""
import sys
import types
import zipfile

import pytest

COMIC_INFO = """<?xml version="1.0"?>
<ComicInfo>
  <Title>Test Comic</Title><Series>Test Series</Series>
  <Characters>Wolverine, Sabretooth</Characters>
  <Manga>{manga}</Manga>
</ComicInfo>"""


def _stub(name, **attrs):
    if name in sys.modules:
        return
    module = types.ModuleType(name)
    module.__dict__.update(attrs)
    sys.modules[name] = module


class _Logger:
    def info(self, message, **kwargs): pass
    def warning(self, message, **kwargs): pass
    def error(self, message, **kwargs): pass


_stub("custom_logger", logger_config=_Logger())
_stub("json_repair", loads=__import__("json").loads)


class _Type:
    OBJECT = ARRAY = STRING = INTEGER = NUMBER = BOOLEAN = "T"


class _Schema:
    def __init__(self, **kwargs): self.__dict__.update(kwargs)


_stub("google")
_stub("google.genai", types=types.SimpleNamespace(Type=_Type, Schema=_Schema))
sys.modules["google"].genai = sys.modules["google.genai"]


@pytest.fixture(autouse=True)
def no_live_services(monkeypatch):
    """No test may reach the real TTT or OCR services. Tests that need them stub
    them themselves; their patch is applied after this one."""
    def blocked_ttt(*args, **kwargs):
        raise RuntimeError("TTT was called but not stubbed in this test")

    def blocked_ocr(*args, **kwargs):
        raise RuntimeError("OCR was called but not stubbed in this test")

    monkeypatch.setattr("panelflow.v2.providers.ttt.generate", blocked_ttt)
    monkeypatch.setattr("panelflow.v2.providers.ocr.lines", blocked_ocr)


@pytest.fixture
def comic_folder(tmp_path):
    """A folder with a two-page CBZ. `manga` marks it right-to-left."""
    def build(name="Test Comic", manga="No"):
        from PIL import Image
        folder = tmp_path / name
        folder.mkdir()
        pages = []
        for i in range(2):
            page = tmp_path / f"src_{i}.jpg"
            Image.new("RGB", (1000, 1500), (200, 200, 200)).save(page)
            pages.append(page)
        with zipfile.ZipFile(folder / f"{name}.cbz", "w") as z:
            z.writestr("ComicInfo.xml", COMIC_INFO.format(manga=manga))
            for i, page in enumerate(pages):
                z.write(page, f"{i:03d}.jpg")
        return str(folder)
    return build


@pytest.fixture
def fake_extractor(monkeypatch, tmp_path):
    """Replace the panel extractor with output in its real filename format."""
    def install(bboxes=((500, 10, 900, 400), (10, 10, 400, 400)), text_regions=None):
        from PIL import Image
        from panelflow.v2.stage1 import split
        counter = {"n": 0}
        monkeypatch.setattr(split, "_ensure_installed", lambda: None)
        # 1.2 gets text lines from the OCR service, not the extractor.
        monkeypatch.setattr(
            "panelflow.v2.providers.ocr.lines",
            lambda image_path: [{"text": f"line {i}", "box": list(r)}
                                for i, r in enumerate(text_regions or [])])

        def fake_run(image_path):
            counter["n"] += 1
            raw = tmp_path / f"raw_{counter['n']}"
            raw.mkdir()
            for i, bbox in enumerate(bboxes, start=1):
                Image.new("RGB", (50, 50)).save(raw / f"panel_{i}_{tuple(bbox)}.jpg")
            Image.new("RGB", (50, 50)).save(raw / "panels_visualization.jpg")
            return str(raw)

        monkeypatch.setattr(split, "_run_extractor", fake_run)
    return install
