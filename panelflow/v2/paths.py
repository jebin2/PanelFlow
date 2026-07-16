import hashlib
import os

from . import jsonio

SCHEMA_VERSION = 1

# page.json status progression
EXTRACTED = "extracted"
SPLIT = "split"
ANALYZED = "analyzed"
_STATUS_ORDER = [EXTRACTED, SPLIT, ANALYZED]


def status_at_least(status, minimum):
    return status in _STATUS_ORDER and _STATUS_ORDER.index(status) >= _STATUS_ORDER.index(minimum)


class Assets:
    """All Stage 1 paths + JSON access for one comic folder. Nothing else."""

    def __init__(self, comic_folder):
        self.folder = os.path.abspath(comic_folder)
        self.name = os.path.basename(self.folder)
        self.assets_dir = os.path.join(self.folder, "assets")
        self.pages_dir = os.path.join(self.assets_dir, "pages")
        self.book_path = os.path.join(self.assets_dir, "book.json")
        self.characters_path = os.path.join(self.assets_dir, "characters.json")
        self.cbz_path = os.path.join(self.folder, f"{self.name}.cbz")
        self.direction_dir = os.path.join(self.folder, "direction")
        self.render_dir = os.path.join(self.folder, "render")
        # The handoff to pub_yt_x, and the tombstone it leaves behind — see 3.4.
        self.progress_path = os.path.join(self.folder, "progress.json")
        self.thumbnail_path = os.path.join(self.folder, "thumbnail.jpg")

    def page_dir(self, index):
        return os.path.join(self.pages_dir, f"{index:04d}")

    def page_image(self, index):
        return os.path.join(self.page_dir(index), "page.jpg")

    def page_json_path(self, index):
        return os.path.join(self.page_dir(index), "page.json")

    def panels_dir(self, index):
        return os.path.join(self.page_dir(index), "panels")

    # ------------------------------------------------------------------ json access

    def load_book(self):
        return jsonio.read(self.book_path, {})

    def save_book(self, data):
        jsonio.write(self.book_path, data)

    def load_characters(self):
        return jsonio.read(self.characters_path, {})

    def save_characters(self, data):
        jsonio.write(self.characters_path, data)

    def load_page(self, index):
        return jsonio.read(self.page_json_path(index), {})

    def save_page(self, index, data):
        jsonio.write(self.page_json_path(index), data)

    # ------------------------------------------------------------------ stage 2

    def direction_path(self, target):
        return os.path.join(self.direction_dir, f"{target}.json")

    def load_direction(self, target):
        return jsonio.read(self.direction_path(target), {})

    def save_direction(self, target, data):
        jsonio.write(self.direction_path(target), data)

    # ------------------------------------------------------------------ stage 3

    def target_dir(self, target):
        return os.path.join(self.render_dir, target)

    def audio_dir(self, target):
        return os.path.join(self.target_dir(target), "audio")

    def shot_audio_path(self, target, shot_id, narration):
        """Keyed by what is spoken, not just by position: a re-directed or
        repaired shot 3 must not find the audio of the *old* shot 3 and play
        the old script over the new cut. New words, new file — the old one
        stays behind as a dead cache entry, which costs bytes and nothing else.
        """
        spoken = hashlib.md5(narration.encode("utf-8")).hexdigest()[:8]
        return os.path.join(self.audio_dir(target), f"shot_{shot_id:03d}_{spoken}.wav")

    def manifest_path(self, target):
        return os.path.join(self.target_dir(target), "manifest.json")

    def video_path(self, target):
        return os.path.join(self.target_dir(target), f"{target}.mp4")

    def rel_to_book(self, path):
        """A path as the renderer sees it.

        Stage 3 symlinks remotion-comic/public/render_assets at this comic
        folder, so `staticFile("render_assets/<this>")` resolves to `path`.
        """
        return "render_assets/" + os.path.relpath(os.path.abspath(path), self.folder)

    def load_progress(self):
        return jsonio.read(self.progress_path, {})

    def save_progress(self, data):
        jsonio.write(self.progress_path, data)

    def published(self):
        """The publisher has uploaded this book and wiped the folder behind it.

        progress.json is all that is left — no cbz, no assets, nothing to
        re-make. Every stage checks this before touching a folder, because the
        honest answer to "re-run me" here is that there is nothing to run.
        """
        return bool(self.load_progress().get("PUBLISHED"))

    def stage2_complete(self, target):
        """The gate Stage 3 checks: 2.3 passed, so the direction is playable."""
        return bool(self.load_direction(target).get("validated"))

    def stage1_complete(self):
        """The gate Stage 2 checks: 1.6 passed, so the assets are consistent."""
        return bool(self.load_book().get("analysis", {}).get("completed_at"))

    def page_indices(self):
        """Discovered from disk — page dirs are the source of truth, book.json's
        pages[] is only a derived index."""
        if not os.path.isdir(self.pages_dir):
            return []
        return sorted(int(name) for name in os.listdir(self.pages_dir)
                      if name.isdigit() and os.path.isdir(os.path.join(self.pages_dir, name)))

    def pages(self):
        return [(i, self.load_page(i)) for i in self.page_indices()]

    # ------------------------------------------------------------------ book index sync

    def rebuild_index(self):
        """Refresh book.json's lightweight pages[] index from each page.json."""
        book = self.load_book()
        index = []
        for i in self.page_indices():
            page = self.load_page(i)
            index.append({
                "index": i,
                "dir": f"pages/{i:04d}",
                "page_type": page.get("page_type", "story"),
                "status": page.get("status", ""),
                "panel_count": len(page.get("panels", [])),
            })
        book["pages"] = index
        self.save_book(book)


def invalidate_downstream(assets, include_roster=False):
    """An earlier sub-stage changed data: clear later done-markers (1.4/1.5/1.6)."""
    book = assets.load_book()
    if book.get("story") or book.get("analysis"):
        book["story"] = {}
        book["analysis"] = {}
        assets.save_book(book)
    if include_roster:
        characters = assets.load_characters()
        if characters.get("reconciled"):
            characters["reconciled"] = False
            assets.save_characters(characters)
