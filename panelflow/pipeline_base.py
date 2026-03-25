from abc import ABC, abstractmethod
import json
import os
import pickle
from custom_logger import logger_config
from jebin_lib import utils
from .categories.base import CategoryBase
from . import config
from panelflow.pipeline import gemini_history_processor


class PipelineBase(ABC):
    def __init__(self, folder, category):
        self.folder = folder
        self.category = CategoryBase.get_category(category, self)
        self.set_all_paths()

    def set_all_paths(self):
        self.folder_name = os.path.basename(self.folder)

        # ── AI state: three clean JSON files ──────────────────────────────
        # 1. Per-page narrations only
        self.review_responses_json_path = os.path.join(self.folder, "review_responses.json")
        # 2. Recap text + YouTube title + Twitter post
        self.recap_title_desc_path = os.path.join(self.folder, "recap_title_desc.json")
        # 3. Sentence → comic page mapping (with duration + img_path added later)
        self.recap_match_path = os.path.join(self.folder, "recap_match.json")

        # CBZ source + extracted panels
        self.cbz_path = os.path.join(self.folder, f"{self.folder_name}.cbz")
        self.panels_dir = os.path.join(self.folder, "Panels")
        utils.create_directory(self.panels_dir)

        # Gemini conversation history (pickles)
        self.review_history_pkl_path = os.path.join(self.folder, "review_history.pkl")
        self.recap_history_pkl_path = os.path.join(self.folder, "recap_history.pkl")

        # Per-sentence clip dirs
        self.sentence_media_dir = os.path.join(self.folder, "sentence_media")
        utils.create_directory(self.sentence_media_dir)

        self.shorts_media_dir = os.path.join(self.folder, "shorts_media")
        utils.create_directory(self.shorts_media_dir)

        # Audio
        self.shorts_recap_audio_path = os.path.join(self.folder, "shorts_recap_audio.wav")

        # Music (shared by review + shorts)
        self.musicgen_path = os.path.join(self.folder, "musicgen.wav")

        # Thumbnail (cover page resized to 1920x1080)
        self.thumbnail_path = os.path.join(self.folder, "thumbnail.jpg")

        # Final videos
        self.output_no_music_path = os.path.join(self.folder, "output_no_music.mp4")
        self.final_video_path = os.path.join(self.folder, "output.mp4")

        self.shorts_output_no_music_path = os.path.join(self.folder, "shorts_output_no_music.mp4")
        self.shorts_final_video_path = os.path.join(self.folder, "shorts_output.mp4")

        # Progress
        self.progress_path = os.path.join(self.folder, "progress.json")

    # ------------------------------------------------------------------ review_responses

    def load_review_responses_json_path(self):
        data = []
        if os.path.exists(self.review_responses_json_path):
            with open(self.review_responses_json_path, 'r') as f:
                data = json.load(f)

        return data

    def load_review_history_pkl(self):
        data = []
        if os.path.exists(self.review_history_pkl_path):
            with open(self.review_history_pkl_path, 'rb') as f:
                data = pickle.load(f)

        return gemini_history_processor.deduplicate_history(data)

    def save_review_responses(self, data):
        with open(self.review_responses_json_path, 'w') as f:
            json.dump([
                {**entry, "key_moment": utils.to_rel(entry["key_moment"], config.BASE_PATH)} if "key_moment" in entry else entry
                for entry in data
            ], f, indent=4, ensure_ascii=False)

    # ------------------------------------------------------------------ recap_history

    def load_recap_history_pkl(self):
        data = []
        if os.path.exists(self.recap_history_pkl_path):
            with open(self.recap_history_pkl_path, 'rb') as f:
                data = pickle.load(f)
        return gemini_history_processor.deduplicate_history(data)

    def save_recap_history_pkl(self, data):
        with open(self.recap_history_pkl_path, 'wb') as f:
            pickle.dump(data, f)

    # ------------------------------------------------------------------ recap_title_desc

    def load_recap_title_desc(self):
        data = {}
        if os.path.exists(self.recap_title_desc_path):
            with open(self.recap_title_desc_path, 'r') as f:
                data = json.load(f)
        return data

    def save_recap_title_desc(self, data):
        with open(self.recap_title_desc_path, 'w') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

    # ------------------------------------------------------------------ recap_match

    def load_recap_match(self):
        data = []
        if os.path.exists(self.recap_match_path):
            with open(self.recap_match_path, 'r') as f:
                raw = f.read()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                logger_config.warning(f"recap_match JSON malformed, attempting repair: {self.recap_match_path}")
                data = utils.extract_json(raw)
                if isinstance(data, list):
                    self.save_recap_match(data)
        return data

    def save_recap_match(self, data):
        with open(self.recap_match_path, 'w') as f:
            json.dump([
                {**entry, "img_path": utils.to_rel(entry["img_path"], config.BASE_PATH)} if "img_path" in entry else entry
                for entry in data
            ], f, indent=4, ensure_ascii=False)

    # ------------------------------------------------------------------ progress

    def _get_progress(self):
        data = {}
        if os.path.exists(self.progress_path):
            with open(self.progress_path, 'r') as f:
                data = json.load(f)
        return data

    def _save_progress(self, data):
        with open(self.progress_path, 'w') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

    # ------------------------------------------------------------------ misc

    def allowed_create(self):
        return self.category.allowed_create()

    def is_processed(self):
        progress_json = self._get_progress()
        return progress_json.get("PROCESSED", False)

    @abstractmethod
    def process(self):
        pass
