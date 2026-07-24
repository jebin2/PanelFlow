"""3.2 compile — the parts that are arithmetic rather than orchestration.

The fill crop is where a wide panel stops being a thin strip over a blurred bar.
Its geometry is pinned in test_geometry; here we check the wiring around it: that
a cropped panel's text regions and focal point are rebased onto the cut, and
that a region cut away by the crop is dropped rather than left off-screen.
"""
import pytest
from PIL import Image

from panelflow.stage3 import compile as compile_


def test_clip_keeps_the_visible_part_and_drops_what_is_wholly_outside():
    kept, straddling, gone = ((0.2, 0.2, 0.4, 0.4),
                              (-0.1, 0.5, 0.3, 0.7),
                              (1.2, 0.5, 1.4, 0.7))
    clipped = compile_._clip([kept, straddling, gone])

    assert kept in clipped
    assert (0.0, 0.5, 0.3, 0.7) in clipped     # the off-edge corner is clamped
    assert all(region[0] < region[2] <= 1.0 for region in clipped)
    assert len(clipped) == 2                    # the wholly-outside one is gone


class _Assets:
    def __init__(self, page_dir, target_dir):
        self._page_dir, self._target_dir = page_dir, target_dir

    def page_dir(self, index):
        return self._page_dir

    def target_dir(self, target):
        return self._target_dir


def test_a_wide_panel_is_cropped_and_its_regions_rebased_onto_the_cut(tmp_path):
    page_dir = tmp_path / "page"
    page_dir.mkdir()
    Image.new("RGB", (2000, 1000), (128, 128, 128)).save(page_dir / "panel.jpg")
    assets = _Assets(str(page_dir), str(tmp_path / "target"))

    panel = {
        "id": 1,
        "bbox": [0, 0, 2000, 1000],
        "image": "panel.jpg",
        "focal_point": [0.5, 0.5],
        # one region near the centre, one out at the far right edge
        "text_regions": [[900, 400, 1100, 600], [1850, 400, 1980, 600]],
    }
    shot = {"id": 3, "source": {"page": 1}}

    image_path, regions, camera, focal = compile_._panel_source(
        assets, "shorts", shot, panel, (1080, 1920), aim=True)

    assert camera is None
    # A wide panel in a portrait frame is cropped, so we show the cut, not the
    # whole panel image.
    assert image_path.endswith("shot_003.jpg")
    assert Image.open(image_path).size[0] < 2000        # narrower than the panel
    # The centred region survives inside the cut; the far-right one is gone.
    assert len(regions) == 1
    assert all(0.0 <= v <= 1.0 for v in regions[0])
    # Focal was centred, and the crop is centred on it, so it stays centred.
    assert focal[0] == pytest.approx(0.5, abs=0.02)


def test_longform_leaves_a_wide_panel_whole(tmp_path):
    """Only the portrait short crops. In longform the same wide panel keeps all
    its artwork — its letterbox is mild and cropping would cost height."""
    page_dir = tmp_path / "page"
    page_dir.mkdir()
    Image.new("RGB", (2000, 1000), (128, 128, 128)).save(page_dir / "panel.jpg")
    assets = _Assets(str(page_dir), str(tmp_path / "target"))

    panel = {"id": 1, "bbox": [0, 0, 2000, 1000], "image": "panel.jpg",
             "focal_point": [0.5, 0.5], "text_regions": []}
    shot = {"id": 3, "source": {"page": 1}}

    image_path, _, _, _ = compile_._panel_source(
        assets, "longform", shot, panel, (1920, 1080), aim=True)

    assert image_path.endswith("panel.jpg")             # uncut


def test_a_panel_that_already_fits_is_shown_whole(tmp_path):
    page_dir = tmp_path / "page"
    page_dir.mkdir()
    Image.new("RGB", (1000, 1500), (128, 128, 128)).save(page_dir / "panel.jpg")
    assets = _Assets(str(page_dir), str(tmp_path / "target"))

    panel = {"id": 1, "bbox": [0, 0, 1000, 1500], "image": "panel.jpg",
             "focal_point": [0.5, 0.5], "text_regions": []}
    shot = {"id": 3, "source": {"page": 1}}

    image_path, _, _, _ = compile_._panel_source(
        assets, "shorts", shot, panel, (1080, 1920), aim=True)

    assert image_path.endswith("panel.jpg")             # the panel itself, uncut
