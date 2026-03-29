from abc import ABC, abstractmethod
import json
import os
from .. import config
from jebin_lib import utils


class CategoryBase(ABC):
    def __init__(self, name, processor_obj):
        self.name = name
        self.processor_obj = processor_obj

    def __str__(self):
        return self.name

    def __eq__(self, other):
        if isinstance(other, str):
            return self.name == other
        return super().__eq__(other)

    def allowed_create(self):
        return True

    @staticmethod
    def get_category(name, processor_obj):
        if name == config.COMIC:
            from .comic import Comic
            return Comic(processor_obj)
        else:
            raise ValueError(f"Invalid category: {name}")

    def allowed_to_publish_in_twitter(self):
        return False

    def allowed_to_publish_in_yt(self):
        return True

    @abstractmethod
    def get_cred_token_file_name(self):
        pass

    def get_yt_description(self):
        return ""

    def get_yt_tags(self):
        return []

    def get_twitter_cred_token_file_name(self):
        return None, None

    def _get_used_publish_dates(self):
        """Return set of dates (YYYY-MM-DD UTC) already scheduled in this category."""
        used = set()
        category_folder = os.path.dirname(self.processor_obj.file_parent_dir_path)
        if not os.path.isdir(category_folder):
            return used
        for entry in os.scandir(category_folder):
            if not entry.is_dir() or entry.path == self.processor_obj.file_parent_dir_path:
                continue
            progress_file = os.path.join(entry.path, "progress.json")
            if not utils.file_exists(progress_file):
                continue
            try:
                import json_repair
                with open(progress_file) as f:
                    p = json_repair.loads(f.read())
                publish_at = p.get("NEXT_ALLOWED_PUBLISH_DATETIME", "")
                if publish_at:
                    used.add(publish_at[:10])  # YYYY-MM-DD
            except Exception:
                pass
        return used

    def next_allowed_publish_datetime(self):
        from datetime import datetime, timedelta, timezone
        import random

        WED, FRI, SUN = 2, 4, 6
        TARGET_DAYS = {WED, FRI, SUN}
        TIMES = [(3, 30), (14, 30)]
        hour, minute = random.choice(TIMES)

        used_dates = self._get_used_publish_dates()
        now_utc = datetime.now(timezone.utc)
        candidate = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)

        for _ in range(30):
            if candidate.weekday() in TARGET_DAYS:
                slot = candidate.replace(hour=hour, minute=minute)
                date_str = slot.strftime("%Y-%m-%d")
                if slot > now_utc and date_str not in used_dates:
                    return slot.strftime("%Y-%m-%d %H:%M:%S")
            candidate += timedelta(days=1)

        return None

    def create_progress_file(self):
        rtd = self.processor_obj.load_recap_title_desc()
        youtube_title = rtd.get("youtube_title", "")
        twitter_post = rtd.get("twitter_post", "")

        final_video_exists = os.path.exists(self.processor_obj.final_video_path)

        cred_file, token_file = self.get_cred_token_file_name()
        twitter_cred_file, twitter_token_file = self.get_twitter_cred_token_file_name()

        progress = self.processor_obj._get_progress()
        progress.update({
            "FINAL_VIDEO_PATH": utils.to_rel(
                self.processor_obj.final_video_path, config.CONTENT_TO_BE_PROCESSED
            ),
            "SHORTS_VIDEO_PATH": utils.to_rel(
                self.processor_obj.shorts_final_video_path, config.CONTENT_TO_BE_PROCESSED
            ),
            "THUMBNAIL_PATH": utils.to_rel(
                self.processor_obj.thumbnail_path, config.CONTENT_TO_BE_PROCESSED
            ) if os.path.exists(self.processor_obj.thumbnail_path) else None,
            "YOUTUBE_TITLE": youtube_title,
            "TWITTER_POST": twitter_post,
            "PROCESSED": final_video_exists,
            "NEXT_ALLOWED_PUBLISH_DATETIME": self.next_allowed_publish_datetime(),
            "PUBLISH_IN_YT": self.allowed_to_publish_in_yt(),
            "PUBLISH_IN_TWITTER": self.allowed_to_publish_in_twitter(),
            "YT_CREDENTIAL_FILE": cred_file,
            "YT_TOKEN_FILE": token_file,
            "YT_DESCRIPTION": self.get_yt_description(),
            "YT_TAGS": self.get_yt_tags(),
            "TWITTER_CREDENTIAL_FILE": twitter_cred_file,
            "TWITTER_TOKEN_FILE": twitter_token_file,
        })
        self.processor_obj._save_progress(progress)
