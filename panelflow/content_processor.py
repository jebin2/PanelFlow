import time
from custom_logger import logger_config
from panelflow import databasecon
from panelflow import config as custom_env
from panelflow.pipeline.audio_generator import AudioGenerator
from panelflow.pipeline.video_generator import VideoGenerator
from panelflow import common
from pathlib import Path

class ContentProcessor:
    type_instance = None

    def __init__(self, type_instance):
        self.type_instance = type_instance

    def _get_unprocessed_data(self):
        filter_clause = ''
        filter_values = []

        values = tuple([self.type_instance.get_type()] + filter_values)

        order = 'ORDER BY CASE WHEN audioPath LIKE \'%audio%\' THEN 1 ELSE 0 END, id DESC'

        query = (f"SELECT * FROM {custom_env.TABLE_NAME} WHERE type = ?"
                 f" AND (video_processed is NULL or video_processed != 1)"
                 f" {filter_clause} {order}")
        return databasecon.execute(query, values, type='get')

    def process_content(self, db_entry):
        db_entry = self._get_unprocessed_data() if not db_entry else db_entry

        if not db_entry:
            logger_config.error(f"Content for {self.type_instance.get_type()}. No old data available to create.")
            return False

        is_success = False
        
        logger_config.warning(f"Truncating... {custom_env.TEMP_OUTPUT}")
        common.remove_all_files_and_dirs(custom_env.TEMP_OUTPUT)
        common.create_directory(custom_env.TEMP_OUTPUT)

        db_entry = self.type_instance.set_db_entry(db_entry)
        logger_config.success(f"Starting to process db_entry :: {str(db_entry)[:100]}")

        videoPath = self.type_instance.get_db_entry()[databasecon.getId("videoPath")]
        if videoPath:
            custom_env.REUSE_SPECIFIC_PATH = f'{custom_env.REUSE_PATH}/{self.type_instance.get_type()}_{Path(videoPath).stem}'
        else:
            custom_env.REUSE_SPECIFIC_PATH = f'{custom_env.REUSE_PATH}/{self.type_instance.get_type()}'
        common.create_directory(custom_env.REUSE_SPECIFIC_PATH)

        audioGenerator = AudioGenerator(self.type_instance)
        failed_type = None
        is_success = audioGenerator.process()
        if is_success:
            self.type_instance.refresh_db_entry()

            videoGenerator = VideoGenerator(self.type_instance)
            is_success = videoGenerator.process()
            db_entry = self.type_instance.refresh_db_entry()

            if not is_success:
                failed_type = 'video'

        self._post_process(db_entry, failed_type)

        return is_success

    def _post_process(self, db_entry, failed_type):
        id = db_entry[0]

        if failed_type == 'audio':
            logger_config.error(f'Invalid audio: {db_entry[0]}')
            databasecon.execute(
                f"""UPDATE {custom_env.TABLE_NAME}
                SET audioPath = NULL,
                generatedVideoPath = NULL,
                generatedThumbnailPath = NULL, lastModifiedTime = {int(time.time() * 1000)}
                WHERE id = ?""",
                (db_entry[0],)
            )

        elif failed_type == 'video':
            logger_config.error(f"Issue in creating video for {self.type_instance.get_type()} id:: {db_entry[0]}")
            databasecon.execute(
                f"""UPDATE {custom_env.TABLE_NAME}
                SET generatedVideoPath = NULL,
                    generatedThumbnailPath = NULL, lastModifiedTime = {int(time.time() * 1000)}
                WHERE id = ?""",
                (db_entry[0],)
            )