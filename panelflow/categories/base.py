from abc import ABC, abstractmethod
import json
import os
from .. import config


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
        if name == config.COMIC_REVIEW:
            from .comic_review import ComicReview
            return ComicReview(processor_obj)
        elif name == config.COMIC_SHORTS:
            from .comic_shorts_review import ComicShortsReview
            return ComicShortsReview(processor_obj)
        else:
            raise ValueError(f"Invalid category: {name}")

    @abstractmethod
    def get_cred_token_file_name(self):
        pass

    def get_yt_title(self):
        return "watch now"

    def get_yt_description(self):
        return "watch now"

    def get_yt_tags(self):
        return []

    def create_progress_file(self):
        rtd = self.processor_obj.load_recap_title_desc()
        youtube_title = rtd.get("youtube_title", self.get_yt_title())
        twitter_post = rtd.get("twitter_post", self.get_yt_description())

        progress = self.processor_obj._get_progress()
        progress.update({
            "FINAL_VIDEO_PATH": os.path.relpath(
                self.processor_obj.final_video_path, config.PANELS_TO_BE_PROCESSED
            ),
            "SHORTS_VIDEO_PATH": os.path.relpath(
                self.processor_obj.shorts_final_video_path, config.PANELS_TO_BE_PROCESSED
            ),
            "CREDENTIAL_NAME": self.get_cred_token_file_name()[0],
            "TOKEN_NAME": self.get_cred_token_file_name()[1],
            "YOUTUBE_TITLE": youtube_title,
            "TWITTER_POST": twitter_post,
            "PROCESSED": True
        })
        self.processor_obj._save_progress(progress)
