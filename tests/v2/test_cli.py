import os

import pytest

from panelflow.v2.cli import prepare_folder


def test_prepare_folder_wraps_a_bare_cbz(tmp_path):
    cbz = tmp_path / "My Comic (2026).cbz"
    cbz.write_bytes(b"PK")

    folder = prepare_folder(str(cbz))

    assert os.path.basename(folder) == "My Comic (2026)"
    assert os.path.exists(os.path.join(folder, "My Comic (2026).cbz"))
    assert cbz.exists(), "the original must be left alone"


def test_prepare_folder_is_idempotent(tmp_path):
    cbz = tmp_path / "My Comic.cbz"
    cbz.write_bytes(b"PK")
    first = prepare_folder(str(cbz))
    assert prepare_folder(str(cbz)) == first


def test_prepare_folder_passes_through_an_existing_folder(tmp_path):
    folder = tmp_path / "Prepared"
    folder.mkdir()
    assert prepare_folder(str(folder)) == str(folder)


def test_prepare_folder_rejects_other_files(tmp_path):
    other = tmp_path / "notes.txt"
    other.write_text("x")
    with pytest.raises(ValueError):
        prepare_folder(str(other))


def test_prepare_folder_reports_a_missing_cbz(tmp_path):
    with pytest.raises(FileNotFoundError):
        prepare_folder(str(tmp_path / "nope.cbz"))
