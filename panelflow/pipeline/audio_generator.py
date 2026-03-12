from custom_logger import logger_config
from panelflow import databasecon
from panelflow import common
from panelflow import config as custom_env
import gc
import traceback
from panelflow.pipeline import merge_audio
import json
import time

class AudioGenerator:
    type_instance = None
    _generatedAudioPath = None

    def __init__(self, type_instance):
        self.type_instance = type_instance
        self._generated_key_moment = False
        self._generatedAudioPath = None

    def _validate(self, audioPath=None):
        type = self.type_instance.get_type()
        if not self.type_instance.is_audio_allowed():
            return True

        if not self.type_instance.is_audio_creation_allowed():
            return self._generated_key_moment

        audioPath = audioPath if audioPath else self.type_instance.get_db_entry()[databasecon.getId("audioPath")]
        if audioPath and "audio/" in audioPath:
            audioPath = f'audio/{audioPath.split("audio/")[-1]}'
        
        if not common.file_exists(audioPath):
            logger_config.warning("""Audio File not exists.""")
            return False

        duration, _, _, _ = common.get_media_metadata(audioPath)
        if duration <= 0 or (duration > 150 and type == custom_env.COMIC_SHORTS):
            logger_config.warning(f"""Not a valid audio length for the {type}: {duration}""")
            return False

        self._generatedAudioPath = audioPath
        return True

    def process(self):
        try:
            status = self._validate()
            if not status:
                status = self._generate()

            if status:
                self._post_success_process()
            else:
                id = self.type_instance.get_db_entry()[databasecon.getId("id")]
                databasecon.execute(f"UPDATE {custom_env.TABLE_NAME} SET audioPath = NULL, lastModifiedTime = {int(time.time() * 1000)} WHERE id = '{id}'")

                return False

            return True

        except Exception as e:
            logger_config.error(f"Error in AudioGenerator::process : {e}\n{traceback.format_exc()}")
            return False

    def _generate(self):
        audioPath = self._process_review()

        return self._validate(audioPath)
    
    def _process_review(self):
        id = self.type_instance.get_db_entry()[databasecon.getId("id")]
        videoPath = self.type_instance.get_db_entry()[databasecon.getId("videoPath")]

        segments = None
        key_moment = None
        try:
            segments = json.loads(self.type_instance.get_db_entry()[databasecon.getId("otherDetails")])
        except:
            pass
        try:
            key_moment = json.loads(self.type_instance.get_db_entry()[databasecon.getId("answer")])
        except:
            pass

        if not segments:
            segments = self.type_instance.get_source_data(videoPath=videoPath)
            databasecon.execute(f"UPDATE {custom_env.TABLE_NAME} SET otherDetails = ?, lastModifiedTime = {int(time.time() * 1000)} WHERE id = ?", (json.dumps(segments, ensure_ascii=False), id))

        key_moment = self.type_instance.get_key_moment(segments)
        databasecon.execute(f"UPDATE {custom_env.TABLE_NAME} SET answer = ?, lastModifiedTime = {int(time.time() * 1000)} WHERE id = ?", (json.dumps(key_moment, ensure_ascii=False), id))
        self._generated_key_moment = True

        if not self.type_instance.is_audio_creation_allowed():
            return None

        content, audioPath = self.type_instance.get_content_for_audio(key_moment)
        if not audioPath:
            audioPath = f'{custom_env.AUDIO_PATH}/{common.generate_random_string()}.wav'
            hf_tts_client = HFTTSClient()
            hf_tts_client.generate_audio_segment(content, audioPath)
        newPath = f'{custom_env.AUDIO_PATH}/{common.generate_random_string()}.wav'

        common.copy(audioPath, newPath)
        audioPath = self.type_instance.merge_audio(newPath)
        if audioPath is None:
            audioPath = merge_audio.merge(newPath)

        return audioPath

    def _post_success_process(self):
        id = self.type_instance.get_db_entry()[databasecon.getId("id")]
        
        databasecon.execute(f"""
                UPDATE {custom_env.TABLE_NAME} 
                SET audioPath = ?, lastModifiedTime = {int(time.time() * 1000)}
                WHERE id = ?
            """, (self._generatedAudioPath, id))

        gc.collect()