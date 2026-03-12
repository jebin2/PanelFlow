from panelflow import config as custom_env
from panelflow import common
from panelflow.categories.comic_review import ComicReview
from panelflow import databasecon
from custom_logger import logger_config
import json
import time
import traceback
from PIL import Image
import gc
import os
from jebin_lib import HFTTSClient

class ComicShortsReview(ComicReview):

    def __init__(self, create_new=False):
        super().__init__(create_new)

    def allowed_to_create_new_content(self):
        return False

    def allowed_to_publish_in_x(self):
        return False

    def get_type(self):
        return custom_env.COMIC_SHORTS

    def is_audio_creation_allowed(self):
        return True

    def resize_frame(self, img_path, i, text):
        base_name = os.path.basename(img_path)
        temp_file = f'{custom_env.TEMP_OUTPUT}/{base_name}_resize_frame.jpg'
        if common.file_exists(temp_file):
            return temp_file
        with Image.open(img_path) as background:
            resized_image = background.resize(custom_env.IMAGE_SIZE[::-1], Image.LANCZOS)
            if temp_file.lower().endswith('.jpg') or temp_file.lower().endswith('.jpeg'):
                resized_image = resized_image.convert('RGB')
            resized_image.save(temp_file)
            return temp_file

    def get_content_for_audio(self, key_moment=None, only_content=False):
        id = self.get_db_entry()[databasecon.getId("id")]
        videoPath = self.get_db_entry()[databasecon.getId("videoPath")]
        if not key_moment:
            segments = self.get_source_data(videoPath=videoPath)
            key_moment = self.get_key_moment(segments)

        hf_tts_client = HFTTSClient()
        audio_files = []

        files = sorted(common.list_files(videoPath))
        content = ""
        for moment in key_moment:
            if moment['key_moment'] == 'overview':
                recap_match = moment["recap_match"]
                for i in range(len(recap_match)):
                    logger_config.info(f"Working get_content_for_audio {i+1} of {len(recap_match)}", overwrite=i>0)
                    numbers = recap_match[i]["comic_page_number"]
                    index = int(numbers)-1
                    if common.file_exists(files[index]):
                        content += f'{recap_match[i]["recap_sentence"]} '
                        if not only_content:
                            final_path = f'{custom_env.REUSE_SPECIFIC_PATH}/audio_{i}.wav'
                            audio_files.append(final_path)
                            if common.file_exists(final_path) and not common.is_valid_wav(final_path):
                                common.remove_file(final_path)
                            if not common.file_exists(final_path):
                                hf_tts_client.generate_audio_segment(recap_match[i]["recap_sentence"].strip(), final_path)

                            _, duration, _, _ = common.get_media_metadata(final_path)
                            recap_match[i]['duration'] = duration
                            moment["recap_match"] = recap_match

                if not only_content:
                    databasecon.execute(f"UPDATE {custom_env.TABLE_NAME} SET answer = ?, lastModifiedTime = {int(time.time() * 1000)} WHERE id = ?", (json.dumps(key_moment, ensure_ascii=False), id))
                break

        final_output_audio = None
        if not only_content:
            logger_config.info(f"Combining {len(audio_files)} audio files...")
            final_output_audio = f'{custom_env.AUDIO_PATH}/{common.generate_random_string()}.wav'
            common.combineAudio(audio_files, final_output_audio, silence=0)
            logger_config.info(f"Combined audio saved as {final_output_audio}")

        return content, final_output_audio

    def get_google_ai_studio_key_moment(self):
        return json.loads(self.get_db_entry()[databasecon.getId("answer")])

    def create_frame_params(self, segments=None, background_path=None, font_path=None, start_show_answer=None, frames_details=None, fps=custom_env.FPS):
        frame_params = []
        id = self.get_db_entry()[databasecon.getId("id")]
        videoPath = self.get_db_entry()[databasecon.getId("videoPath")]
        files = sorted(common.list_files(videoPath))
        key_moment = json.loads(self.get_db_entry()[databasecon.getId("answer")])
        logger_config.debug(f'key_moment:: {key_moment}')

        hf_tts_client = HFTTSClient()
        for moment in key_moment:
            if moment['key_moment'] == 'overview':
                recap_match = moment["recap_match"]
                start = 0
                for i in range(len(recap_match)):
                    try:
                        numbers = recap_match[i]["comic_page_number"]
                        numbers = int(numbers)-1
                        if common.file_exists(files[numbers]):
                            text = recap_match[i]["recap_sentence"]
                            if 'duration' not in recap_match[i] or not recap_match[i]['duration']:
                                audio_path = f'{custom_env.TEMP_OUTPUT}/{common.generate_random_string()}.wav'
                                hf_tts_client.generate_audio_segment(text, audio_path)
                                _, duration, _, _ = common.get_media_metadata(audio_path)
                                recap_match[i]['duration'] = duration
                                moment["recap_match"] = recap_match
                                databasecon.execute(f"UPDATE {custom_env.TABLE_NAME} SET answer = ?, lastModifiedTime = {int(time.time() * 1000)} WHERE id = ?", (json.dumps(key_moment, ensure_ascii=False), id))

                            frame_params.append({
                                'img_path': self.resize_frame(files[numbers], i, text),
                                'clip_duration': recap_match[i]['duration'],
                                'clip_start': start,
                                "zoom_out_zoom_in_to_full": True,
                                "IMAGE_SIZE": custom_env.IMAGE_SIZE[::-1]
                            })
                            start += recap_match[i]['duration']
                            start = round(start, 2)
                    except Exception as e:
                        logger_config.error(f"Error {str(e)} \n {traceback.format_exc()}")
                        pass

                break

        gc.collect()

        return frame_params

    def get_yt_description(self):
        title = self.get_db_entry()[databasecon.getId('title')]
        return f"#Comics #Comic #comicbooks #comicbook #comicshorts #{title}"

    def get_recap_length(self, type):
        if type == "min":
            return 700
        return 1500