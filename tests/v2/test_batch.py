"""The inbox loop: which books, in what order, and what one book's failure
costs the rest. Everything about *how* a book is made belongs to the CLI and is
stubbed here."""
import os

from panelflow.v2 import batch


def _inbox(tmp_path, folders=(), files=(), strays=()):
    """A prepared comic folder holds the .cbz it was made from; `strays` are
    folders that do not, which is what makes them not books."""
    for name in folders:
        os.makedirs(tmp_path / name)
        (tmp_path / name / f"{name}.cbz").write_text("x")
    for name in strays:
        os.makedirs(tmp_path / name)
    for name in files:
        (tmp_path / name).write_text("x")
    return str(tmp_path)


def test_folders_and_cbzs_are_both_books_in_name_order(tmp_path, monkeypatch):
    monkeypatch.setattr(batch, "COPY_SETTLE_SECONDS", 0)
    inbox = _inbox(tmp_path, folders=["B book"], files=["A book.cbz", "notes.txt"])

    assert [os.path.basename(p) for p in batch.books(inbox)] == ["A book.cbz", "B book"]


def test_a_cbz_already_prepared_is_not_queued_twice(tmp_path, monkeypatch):
    """The CLI copies a .cbz into its folder instead of moving it, so the
    original never leaves the inbox. The folder is the book from then on."""
    monkeypatch.setattr(batch, "COPY_SETTLE_SECONDS", 0)
    inbox = _inbox(tmp_path, folders=["Wonder Woman 035"],
                   files=["Wonder Woman 035.cbz", "Batwoman 005.cbz"])

    assert [os.path.basename(p) for p in batch.books(inbox)] == [
        "Batwoman 005.cbz", "Wonder Woman 035"]


def test_a_cbz_still_being_copied_waits_for_the_next_pass(tmp_path, monkeypatch):
    """Unpacking half a download fails in 1.1 for a reason that has nothing to
    do with the book."""
    monkeypatch.setattr(batch, "COPY_SETTLE_SECONDS", 0)
    inbox = _inbox(tmp_path, files=["growing.cbz"])
    path = os.path.join(inbox, "growing.cbz")

    sizes = iter([10, 20])
    monkeypatch.setattr(batch.os.path, "getsize", lambda p: next(sizes))

    assert batch.books(inbox) == []


def test_a_missing_inbox_is_a_warning_not_a_crash(tmp_path):
    assert batch.books(str(tmp_path / "nope")) == []


def test_a_folder_that_is_not_a_book_is_not_queued(tmp_path, monkeypatch):
    """A published book's leftovers, or any stray folder, has no .cbz of its
    own — queueing it would send Stage 1 hunting for one that never existed."""
    monkeypatch.setattr(batch, "COPY_SETTLE_SECONDS", 0)
    inbox = _inbox(tmp_path, folders=["real"], strays=["assets", "leftovers"])

    assert [os.path.basename(p) for p in batch.books(inbox)] == ["real"]


def test_naming_the_inbox_scans_it_instead_of_reading_it_as_a_book(tmp_path, monkeypatch):
    """`run_app.sh content_to_be_processed` used to look for
    content_to_be_processed.cbz inside itself and die in 1.1."""
    monkeypatch.setattr(batch, "COPY_SETTLE_SECONDS", 0)
    inbox = _inbox(tmp_path, folders=["One", "Two"])

    assert [os.path.basename(p) for p in batch.expand(inbox)] == ["One", "Two"]


def test_naming_a_comic_folder_runs_that_one_book(tmp_path):
    inbox = _inbox(tmp_path, folders=["One"])
    book = os.path.join(inbox, "One")

    assert batch.expand(book) == [book]


def test_every_book_runs_even_when_one_fails(tmp_path, monkeypatch):
    """A watcher that stops at the first bad book stops watching."""
    monkeypatch.setattr(batch, "COPY_SETTLE_SECONDS", 0)
    inbox = _inbox(tmp_path, folders=["one", "two", "three"])
    seen = []

    def fake_main(argv):
        seen.append(os.path.basename(argv[0]))
        if argv[0].endswith("three"):
            raise RuntimeError("not a comic folder")
        return 1 if argv[0].endswith("two") else 0    # 'two' failed its stages
    monkeypatch.setattr(batch.cli, "main", fake_main)

    failed = batch.run_once(inbox)

    assert seen == ["one", "three", "two"]
    assert failed == 2


def test_the_model_override_reaches_every_book(tmp_path, monkeypatch):
    monkeypatch.setattr(batch, "COPY_SETTLE_SECONDS", 0)
    inbox = _inbox(tmp_path, folders=["one"])
    seen = []
    monkeypatch.setattr(batch.cli, "main", lambda argv: seen.append(argv) or 0)

    batch.run_once(inbox, model="some-model")

    assert seen[0][1:] == ["--model", "some-model"]


def test_named_books_run_once_and_skip_the_inbox(tmp_path, monkeypatch):
    """`run_app.sh <one.cbz>` is a request for that book, not a queue to watch."""
    seen = []
    monkeypatch.setattr(batch.cli, "main", lambda argv: seen.append(argv[0]) or 0)
    monkeypatch.setattr(batch, "books", _never_scanned)

    assert batch.main(["content/One.cbz", "content/Two"]) == 0
    assert [os.path.basename(p) for p in seen] == ["One.cbz", "Two"]
    assert all(os.path.isabs(p) for p in seen)


def test_a_named_book_that_fails_is_a_nonzero_exit(tmp_path, monkeypatch):
    monkeypatch.setattr(batch.cli, "main", lambda argv: 1)
    monkeypatch.setattr(batch, "books", _never_scanned)

    assert batch.main(["content/One.cbz"]) == 1


def test_once_makes_a_single_pass(tmp_path, monkeypatch):
    monkeypatch.setattr(batch, "COPY_SETTLE_SECONDS", 0)
    inbox = _inbox(tmp_path, folders=["one"])
    passes = []
    monkeypatch.setattr(batch, "run_once", lambda i, model=None: passes.append(i))

    assert batch.main(["--once", "--inbox", inbox]) == 0
    assert len(passes) == 1


def test_a_broken_pass_does_not_stop_the_watcher(tmp_path, monkeypatch):
    """The pass itself breaking is not a reason to exit — only --once is."""
    monkeypatch.setattr(batch, "run_once", _raise)

    assert batch.main(["--once", "--inbox", str(tmp_path)]) == 0


def _raise(*a, **kw):
    raise OSError("inbox went away")


def _never_scanned(*a, **kw):
    raise AssertionError("named books must not trigger an inbox scan")
