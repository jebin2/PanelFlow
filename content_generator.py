from custom_logger import logger_config
import custom_env
import os

class ContentGenerator:
    type_instance = None

    def __init__(self, type_instance):
        self.type_instance = type_instance

    def get_new_content(self):
        if not self.type_instance.allowed_to_create_new_content():
            return None

        db_entry = None
        if self.type_instance.get_type() == custom_env.COMIC_REVIEW:
            db_entry = self._process_review()

        if db_entry:
            logger_config.success(f"New content created for {self.type_instance.get_type()} :: {str(db_entry)[:100]}")
        else:
            logger_config.success(f"No New content available to created for {self.type_instance.get_type()}")

        return db_entry

    def _process_review(self):
        content = {}
        content["videoPath"] = self.type_instance.get_source_path()
        if content['videoPath']:
            full_name = content['videoPath'].split("/")[-1]
            file_name, _ = os.path.splitext(full_name)
            content["title"] = file_name
            return self.type_instance.save_to_database(content)

        return None