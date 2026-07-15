import os

import pytest

from panelflow.v2.paths import Assets
from panelflow.v2.stage1 import extract, split, validate


# ---------------------------------------------------------------- 1.1 extract

def test_extract_builds_pages_and_seeds_roster_from_comicinfo(comic_folder):
    assets = Assets(comic_folder())
    extract.run(assets)

    book = assets.load_book()
    assert book["title"] == "Test Comic"
    assert book["page_count"] == 2
    assert book["reading_direction"] == "ltr"
    assert assets.page_indices() == [1, 2]
    assert [c["id"] for c in assets.load_characters()["characters"]] == ["wolverine", "sabretooth"]
    assert all(c["source"] == "comicinfo" for c in assets.load_characters()["characters"])
    assert extract.is_done(assets)


def test_extract_reads_right_to_left_manga_tag(comic_folder):
    assets = Assets(comic_folder(name="RTL Comic", manga="YesAndRightToLeft"))
    extract.run(assets)
    assert assets.load_book()["reading_direction"] == "rtl"


def test_extract_marks_first_page_as_cover_and_records_size(comic_folder):
    assets = Assets(comic_folder())
    extract.run(assets)
    assert assets.load_page(1)["page_type"] == "cover"
    assert assets.load_page(2)["page_type"] == "story"
    assert (assets.load_page(1)["width"], assets.load_page(1)["height"]) == (1000, 1500)
    assert assets.load_page(1)["is_spread"] is False


def test_extract_is_idempotent(comic_folder):
    assets = Assets(comic_folder())
    extract.run(assets)
    before = assets.load_page(1)
    extract.run(assets)
    assert assets.load_page(1) == before


def test_extract_without_cbz_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        extract.run(Assets(str(tmp_path)))


# ---------------------------------------------------------------- 1.2 split

def test_split_orders_panels_and_records_bboxes(comic_folder, fake_extractor):
    fake_extractor()
    assets = Assets(comic_folder())
    extract.run(assets)
    split.run(assets)

    panels = assets.load_page(1)["panels"]
    assert [p["id"] for p in panels] == [1, 2]
    assert panels[0]["bbox"] == [10, 10, 400, 400]      # ltr: left panel first
    assert panels[1]["bbox"] == [500, 10, 900, 400]
    assert os.path.exists(os.path.join(assets.panels_dir(1), "panel_01.jpg"))
    assert split.is_done(assets)


def test_split_honours_right_to_left_reading_direction(comic_folder, fake_extractor):
    fake_extractor()
    assets = Assets(comic_folder(name="RTL Comic", manga="YesAndRightToLeft"))
    extract.run(assets)
    split.run(assets)
    assert assets.load_page(1)["panels"][0]["bbox"] == [500, 10, 900, 400]  # rightmost first


def test_split_assigns_text_regions_to_the_panel_containing_them(comic_folder, fake_extractor):
    fake_extractor(text_regions=[(520, 20, 700, 120)])
    assets = Assets(comic_folder())
    extract.run(assets)
    split.run(assets)

    left, right = assets.load_page(1)["panels"]
    assert left["text_regions"] == []
    assert right["text_regions"] == [[520, 20, 700, 120]]


def test_split_falls_back_to_whole_page_when_no_panels_found(comic_folder, fake_extractor):
    fake_extractor(bboxes=())
    assets = Assets(comic_folder())
    extract.run(assets)
    split.run(assets)

    panels = assets.load_page(1)["panels"]
    assert len(panels) == 1
    assert panels[0]["bbox"] == [0, 0, 1000, 1500]


def test_split_falls_back_when_the_extractor_crashes_on_one_page(comic_folder, fake_extractor,
                                                                 monkeypatch):
    """The tool works, but chokes on this one page: fall back for that page
    rather than blocking the book."""
    from panelflow.v2.stage1 import split as split_module
    fake_extractor()
    working = split_module._run_extractor

    def boom_on_first(image_path):
        if "0001" in image_path:
            raise RuntimeError("extractor exploded")
        return working(image_path)
    monkeypatch.setattr(split_module, "_run_extractor", boom_on_first)

    assets = Assets(comic_folder())
    extract.run(assets)
    split.run(assets)

    assert len(assets.load_page(1)["panels"]) == 1      # fell back
    assert len(assets.load_page(2)["panels"]) == 2      # unaffected
    assert split.is_done(assets)


def test_split_reruns_only_the_page_reset_in_page_json(comic_folder, fake_extractor):
    fake_extractor()
    assets = Assets(comic_folder())
    extract.run(assets)
    split.run(assets)

    page = assets.load_page(1)
    page["status"] = "extracted"
    assets.save_page(1, page)
    assert not split.is_done(assets)

    split.run(assets)
    assert split.is_done(assets)
    assert len(assets.load_page(1)["panels"]) == 2


def test_bbox_regex_matches_both_real_extractor_formats_and_ignores_debris(tmp_path):
    """Both prefixes are real: '0016_panel_(...)' comes from the extractor's LLM
    path, 'panel_1_(...)' from its CV path."""
    from PIL import Image
    for name in ["0016_panel_(56, 74, 759, 1200).jpg",     # LLM extractor
                 "panel_1_(10, 20, 30, 40).jpg",            # CV extractor
                 "panels_visualization.jpg",                # debris
                 "0000_convert_to_clahe.jpg",               # debris
                 "row_gutters.jpg"]:
        Image.new("RGB", (5, 5)).save(tmp_path / name)
    (tmp_path / "config.json").write_text("{}")

    found = split._parse_bboxes(str(tmp_path))
    assert set(found) == {(56, 74, 759, 1200), (10, 20, 30, 40)}


# ---------------------------------------------------------------- 1.6 validate

def _valid_book(assets):
    for index in assets.page_indices():
        page = assets.load_page(index)
        page["status"] = "analyzed"
        page["analysis"] = {"prompt_version": "v1", "scene_summary": "x"}
        for panel in page["panels"]:
            panel["characters"] = [{"ref": "wolverine", "confidence": "high", "evidence": "claws"}]
            panel["focal_point"] = [0.5, 0.5]
        assets.save_page(index, page)
    book = assets.load_book()
    book["story"] = {"synopsis": "s", "main_characters": ["wolverine"],
                     "beats": [{"beat": "climax", "pages": [2]}], "skip_overrides": []}
    assets.save_book(book)
    characters = assets.load_characters()
    characters["reconciled"] = True
    for character in characters["characters"]:
        character["reference_images"] = []
    assets.save_characters(characters)


@pytest.fixture
def analyzed(comic_folder, fake_extractor):
    fake_extractor()
    assets = Assets(comic_folder())
    extract.run(assets)
    split.run(assets)
    _valid_book(assets)
    return assets


def test_validate_passes_and_sets_completed_at(analyzed):
    assert validate.check(analyzed) == []
    assert validate.run(analyzed) == []
    assert analyzed.load_book()["analysis"]["completed_at"]
    assert validate.is_done(analyzed)


def test_validate_catches_dangling_character_ref(analyzed):
    page = analyzed.load_page(1)
    page["panels"][0]["characters"] = [{"ref": "ghost", "confidence": "high", "evidence": "x"}]
    analyzed.save_page(1, page)
    assert any("unknown character ref 'ghost'" in p for p in validate.check(analyzed))


def test_validate_catches_bbox_outside_page(analyzed):
    page = analyzed.load_page(1)
    page["panels"][0]["bbox"] = [10, 10, 99999, 400]
    analyzed.save_page(1, page)
    assert any("bbox out of page bounds" in p for p in validate.check(analyzed))


def test_validate_catches_focal_point_out_of_range(analyzed):
    page = analyzed.load_page(1)
    page["panels"][0]["focal_point"] = [1.7, 0.2]
    analyzed.save_page(1, page)
    assert any("focal_point" in p for p in validate.check(analyzed))


def test_validate_catches_unreconciled_roster(analyzed):
    characters = analyzed.load_characters()
    characters["reconciled"] = False
    analyzed.save_characters(characters)
    assert any("not reconciled" in p for p in validate.check(analyzed))


def test_validate_catches_bad_story_refs(analyzed):
    book = analyzed.load_book()
    book["story"] = {"synopsis": "s", "main_characters": ["nobody"],
                     "beats": [{"beat": "climax", "pages": [99]}],
                     "skip_overrides": [{"page": 1, "panel": 42, "skippable": False, "reason": "x"}]}
    analyzed.save_book(book)
    problems = validate.check(analyzed)
    assert any("unknown ref 'nobody'" in p for p in problems)
    assert any("unknown page 99" in p for p in problems)
    assert any("no panel 42" in p for p in problems)


def test_validate_catches_missing_panel_image(analyzed):
    os.remove(os.path.join(analyzed.panels_dir(1), "panel_01.jpg"))
    assert any("image missing" in p for p in validate.check(analyzed))


def test_validate_withholds_completed_at_when_invalid(analyzed):
    characters = analyzed.load_characters()
    characters["reconciled"] = False
    analyzed.save_characters(characters)
    assert validate.run(analyzed)
    assert not analyzed.load_book().get("analysis", {}).get("completed_at")


def test_extract_resumes_after_a_crash_without_losing_reading_direction(comic_folder, monkeypatch):
    """A half-extracted folder must not look done: 1.2 needs reading_direction."""
    from panelflow.v2.stage1 import extract as extract_module

    folder = comic_folder(name="RTL Comic", manga="YesAndRightToLeft")
    assets = Assets(folder)
    real_extract_page = extract_module._extract_page

    def crash_on_second(zipf, member, assets_, index):
        if index == 2:
            raise RuntimeError("disk full")
        return real_extract_page(zipf, member, assets_, index)
    monkeypatch.setattr(extract_module, "_extract_page", crash_on_second)

    with pytest.raises(RuntimeError):
        extract.run(assets)
    assert not extract.is_done(assets)

    monkeypatch.setattr(extract_module, "_extract_page", real_extract_page)
    extract.run(assets)
    assert extract.is_done(assets)
    assert assets.load_book()["reading_direction"] == "rtl"
    assert assets.page_indices() == [1, 2]


def test_extract_builds_a_title_from_series_when_title_tag_is_absent(tmp_path):
    """Real-world files often carry Series+Number but no Title; the filename is
    usually scene-release junk."""
    import zipfile
    from PIL import Image
    folder = tmp_path / "Strange Scales 006 (2026) (digital-mobile-Empire)"
    folder.mkdir()
    page = tmp_path / "p.jpg"
    Image.new("RGB", (800, 1280)).save(page)
    xml = """<?xml version='1.0'?><ComicInfo>
      <Series>Strange Scales Infinity Comic</Series><Number>6</Number><Volume>2026</Volume>
      <Summary>Anton and Aleister's impersonator is revealed.</Summary>
      <Publisher>Marvel</Publisher></ComicInfo>"""
    with zipfile.ZipFile(folder / f"{folder.name}.cbz", "w") as z:
        z.writestr("ComicInfo.xml", xml)
        z.write(page, "000.jpg")

    assets = Assets(str(folder))
    extract.run(assets)

    book = assets.load_book()
    assert book["title"] == "Strange Scales Infinity Comic #6 (2026)"
    assert book["publisher"] == "Marvel"
    assert book["publisher_summary"].startswith("Anton and Aleister")
    assert assets.load_characters()["characters"] == []


def test_split_stops_loudly_when_the_extractor_cannot_be_installed(comic_folder, monkeypatch):
    """A missing tool is systemic: silently splitting every page into one
    whole-page panel would ruin the video with no error anywhere."""
    from panelflow.v2.stage1 import split as split_module

    def unavailable():
        raise RuntimeError("comic-panel-extractor is unavailable after install")
    monkeypatch.setattr(split_module, "_ensure_installed", unavailable)

    assets = Assets(comic_folder())
    extract.run(assets)
    with pytest.raises(RuntimeError, match="unavailable"):
        split.run(assets)
    assert not split.is_done(assets)


def test_split_stops_when_the_extractor_crashes_on_every_page(comic_folder, monkeypatch):
    """The binary exists but is broken (e.g. a CUDA/cudnn mismatch). Falling
    back on all 19 pages would pass 1.6 and silently produce a video with no
    panel-level camera work."""
    from panelflow.v2.stage1 import split as split_module
    monkeypatch.setattr(split_module, "_ensure_installed", lambda: None)
    monkeypatch.setattr(split_module, "_run_extractor",
                        lambda image_path: (_ for _ in ()).throw(RuntimeError("core dumped")))

    assets = Assets(comic_folder())
    extract.run(assets)
    with pytest.raises(RuntimeError, match="crashed on all"):
        split.run(assets)


def _cbz_without_metadata(tmp_path, name):
    """A CBZ with no ComicInfo.xml at all — nothing but the filename to go on."""
    import zipfile
    from PIL import Image
    folder = tmp_path / name
    folder.mkdir()
    page = tmp_path / "p.jpg"
    Image.new("RGB", (800, 1280)).save(page)
    with zipfile.ZipFile(folder / f"{name}.cbz", "w") as z:
        z.write(page, "000.jpg")
    return str(folder)


def test_title_is_parsed_from_a_scene_release_name_when_metadata_is_missing(tmp_path, monkeypatch):
    monkeypatch.setattr("panelflow.v2.llm.ask_json",
                        lambda **kw: {"title": "X-Men United #1 (2026)"})
    folder = _cbz_without_metadata(tmp_path, "X-Men United 001 (2026) (Digital) (Zone-Empire)")

    assets = Assets(folder)
    extract.run(assets)
    assert assets.load_book()["title"] == "X-Men United #1 (2026)"


def test_comicinfo_beats_the_filename_parser(tmp_path, monkeypatch):
    """Metadata is ground truth; a model can only add risk to it."""
    called = []
    monkeypatch.setattr("panelflow.v2.llm.ask_json",
                        lambda **kw: called.append(1) or {"title": "Wrong"})

    assets = Assets(comic_folder_with_series(tmp_path))
    extract.run(assets)
    assert assets.load_book()["title"] == "Strange Scales Infinity Comic #6 (2026)"
    assert called == [], "no model call when ComicInfo already answers"


def comic_folder_with_series(tmp_path):
    import zipfile
    from PIL import Image
    folder = tmp_path / "Strange Scales 006 (2026) (digital-mobile-Empire)"
    folder.mkdir()
    page = tmp_path / "s.jpg"
    Image.new("RGB", (800, 1280)).save(page)
    xml = """<?xml version='1.0'?><ComicInfo>
      <Series>Strange Scales Infinity Comic</Series><Number>6</Number>
      <Volume>2026</Volume></ComicInfo>"""
    with zipfile.ZipFile(folder / f"{folder.name}.cbz", "w") as z:
        z.writestr("ComicInfo.xml", xml)
        z.write(page, "000.jpg")
    return str(folder)


def test_title_falls_back_to_the_folder_name_when_the_parser_is_unreachable(tmp_path, monkeypatch):
    def boom(**kw):
        raise RuntimeError("TTT down")
    monkeypatch.setattr("panelflow.v2.llm.ask_json", boom)
    name = "Some Indie Book (2021)"
    folder = _cbz_without_metadata(tmp_path, name)

    assets = Assets(folder)
    extract.run(assets)
    assert assets.load_book()["title"] == name
