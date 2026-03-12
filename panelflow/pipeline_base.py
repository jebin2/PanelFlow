from abc import ABC, abstractmethod
import json
import os
from custom_logger import logger_config
from jebin_lib import utils
from .categories.base import CategoryBase
from . import config  # needed for BASE_PATH in _to_rel


def _to_rel(path):
    """Convert an absolute path to relative (relative to BASE_PATH) for JSON storage."""
    if path and os.path.isabs(path):
        return os.path.relpath(path, config.BASE_PATH)
    return path


class PipelineBase(ABC):
    def __init__(self, folder, category, sync_callback=None):
        self.folder = folder
        self.category = CategoryBase.get_category(category, self)
        self.sync_callback = sync_callback
        self._wrap_methods()
        self.set_all_paths()

    def set_all_paths(self):
        self.folder_name = os.path.basename(self.folder)

        # ── AI state: three clean JSON files ──────────────────────────────
        # 1. Per-page narrations only
        self.review_responses_path = os.path.join(self.folder, "review_responses.json")
        # 2. Recap text + YouTube title + Twitter post
        self.recap_title_desc_path = os.path.join(self.folder, "recap_title_desc.json")
        # 3. Sentence → comic page mapping (with duration + img_path added later)
        self.recap_match_path = os.path.join(self.folder, "recap_match.json")

        # CBZ source + extracted panels
        self.cbz_path = os.path.join(self.folder, f"{self.folder_name}.cbz")
        self.panels_dir = os.path.join(self.folder, "Panels")
        utils.create_directory(self.panels_dir)

        # Gemini conversation history (pickles)
        self.review_history_path = os.path.join(self.folder, "review_history.pkl")
        self.recap_history_path = os.path.join(self.folder, "recap_history.pkl")

        # Per-sentence clip dirs
        self.sentence_media_dir = os.path.join(self.folder, "sentence_media")
        utils.create_directory(self.sentence_media_dir)

        self.shorts_media_dir = os.path.join(self.folder, "shorts_media")
        utils.create_directory(self.shorts_media_dir)

        # Audio
        self.shorts_recap_audio_path = os.path.join(self.folder, "shorts_recap_audio.wav")

        # Music (shared by review + shorts)
        self.musicgen_path = os.path.join(self.folder, "musicgen.wav")

        # Final videos
        self.output_no_music_path = os.path.join(self.folder, "output_no_music.mp4")
        self.final_video_path = os.path.join(self.folder, "output.mp4")

        self.shorts_output_no_music_path = os.path.join(self.folder, "shorts_output_no_music.mp4")
        self.shorts_final_video_path = os.path.join(self.folder, "shorts_output.mp4")

        # Progress
        self.progress_path = os.path.join(self.folder, "progress.json")

    # ------------------------------------------------------------------ review_responses

    def load_review_responses(self):
        if not os.path.exists(self.review_responses_path):
            return []
        with open(self.review_responses_path, 'r') as f:
            return json.load(f)

    def save_review_responses(self, data):
        with open(self.review_responses_path, 'w') as f:
            json.dump([
                {**entry, "key_moment": _to_rel(entry["key_moment"])} if "key_moment" in entry else entry
                for entry in data
            ], f, indent=4, ensure_ascii=False)

    # ------------------------------------------------------------------ recap_title_desc

    def load_recap_title_desc(self):
        if not os.path.exists(self.recap_title_desc_path):
            return {}
        with open(self.recap_title_desc_path, 'r') as f:
            return json.load(f)

    def save_recap_title_desc(self, data):
        with open(self.recap_title_desc_path, 'w') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

    # ------------------------------------------------------------------ recap_match

    def load_recap_match(self):
        if not os.path.exists(self.recap_match_path):
            return []
        with open(self.recap_match_path, 'r') as f:
            return json.load(f)

    def save_recap_match(self, data):
        with open(self.recap_match_path, 'w') as f:
            json.dump([
                {**entry, "img_path": _to_rel(entry["img_path"])} if "img_path" in entry else entry
                for entry in data
            ], f, indent=4, ensure_ascii=False)

    # ------------------------------------------------------------------ progress

    def _get_progress(self):
        if not os.path.exists(self.progress_path):
            return {}
        with open(self.progress_path, 'r') as f:
            return json.load(f)

    def _save_progress(self, data):
        with open(self.progress_path, 'w') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

    # ------------------------------------------------------------------ misc

    def allowed_create(self):
        return self.category.allowed_create()

    def is_processed(self):
        progress_json = self._get_progress()
        return progress_json.get("PROCESSED", False)

    def _wrap_methods(self):
        if not self.sync_callback:
            return
        for attr_name in dir(self.__class__):
            if attr_name.startswith('_') or attr_name in [
                "set_all_paths", "allowed_create"
            ]:
                continue
            attr = getattr(self, attr_name)
            if callable(attr):
                setattr(self, attr_name, self._create_sync_wrapper(attr))

    def _create_sync_wrapper(self, func):
        def wrapper(*args, **kwargs):
            result = func(*args, **kwargs)
            if self.sync_callback:
                logger_config.info(f"Sync callback for {func.__name__}")
                self.sync_callback()
            return result
        return wrapper

    @abstractmethod
    def process(self):
        pass
