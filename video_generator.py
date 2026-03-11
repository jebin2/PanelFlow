from PIL import Image
import os
import random
from custom_logger import logger_config
import databasecon
import common
import custom_env
import gc
from concurrent.futures import ProcessPoolExecutor
import time
import combineImageClip
import combineVideo
import json
import render_text
import shutil
import traceback
from pathlib import Path

BACKGROUND_IMAGES_N = 11
BACKGROUND_LABEL = 'background'
BACKGROUND_EXT = 'jpg'

BACKGROUND_VIDEO_N = 20
BACKGROUND_VIDEO_LABEL = 'video'
BACKGROUND_VIDEO_PATH = 'background_videos'
BACKGROUND_VIDEO_EXT = 'mp4'

FONT_N = 1
FONT_LABEL = 'font'
FONT_PATH = 'Fonts'
FONT_EXT = 'ttf'

IS_VIDEO_BACKGROUND = True

class VideoGenerator:
    type_instance = None
    generatedVideoPath = None
    generatedThumbnailPath = None
    start_show_answer = None

    def __init__(self, type_instance):
        self.type_instance = type_instance
        self.generatedVideoPath = None
        self.generatedThumbnailPath = None
        self.start_show_answer = None

    def _validate(self):
        return self.type_instance.is_video_allowed()

    def process(self):
        try:
            status = self._validate()
            if status:
                status = self._generate()

            if status:
                self._post_success_process()
            elif self.type_instance.is_video_allowed():
                id = self.type_instance.get_db_entry()[databasecon.getId("id")]
                databasecon.execute(f"UPDATE {custom_env.TABLE_NAME} SET generatedVideoPath = NULL, generatedThumbnailPath = NULL, lastModifiedTime = {int(time.time() * 1000)} WHERE id = '{id}'")
                return False

            return True

        except Exception as e: # needed here to added in id_not_in
            logger_config.error(f"Error in VideoGenerator::process : {e}\n{traceback.format_exc()}")
            return False

    def _generate(self):
        gc.collect()
        type = self.type_instance.get_db_entry()[databasecon.getId("type")]
        videoPath = self.type_instance.get_db_entry()[databasecon.getId("videoPath")]
        self.generatedVideoPath = self.type_instance.get_db_entry()[databasecon.getId("generatedVideoPath")]
        self.generatedThumbnailPath = self.type_instance.get_db_entry()[databasecon.getId("generatedThumbnailPath")]
        if not self.generatedVideoPath:
            audioPath, transcript, segments = self.type_instance.get_audio_details()

            fps = custom_env.FPS

            frame_params = self.type_instance.create_frame_params(
                segments=segments,
                fps=fps
            )

            if len(frame_params) == 0:
                logger_config.error('frame_params cannot be empty')
                return None

            if type in [custom_env.COMIC_REVIEW]:
                temp_files = frame_params
            else:
                temp_files = combineImageClip.start(frame_params, fps)

            output_video_path = f"{custom_env.VIDEO}/{Path(videoPath if videoPath else self.type_instance.get_type()).stem}_{common.generate_random_string()}.mp4"

            self.generatedVideoPath = combineVideo.start(temp_files, audioPath, fps, output_video_path=output_video_path)
            self.update_video()

        output_musicgen_path=f'{custom_env.REUSE_SPECIFIC_PATH}/musicgen_out.wav'
        try:
            from addMusic import process as add_music_process
            transcript, _ = self.type_instance.get_content_for_audio(only_content=True)
            prefix_file_name = Path(self.generatedVideoPath).stem
            output_video_path = f"{custom_env.VIDEO}/{prefix_file_name}_music_{common.generate_random_string()}.mp4"
            add_music_process(self.generatedVideoPath, text=transcript, output_path=output_video_path, output_musicgen_path=output_musicgen_path)
            self.generatedVideoPath = output_video_path
            self.update_video(add_bg_music=True)
        except Exception as e:
            logger_config.warning(f"issue in adding music {str(e)} {traceback.format_exc()}")
        
        return True

    def _find_segment_time(self, sentence, segments, type, checkAfterSegment):
        sentence = sentence.strip().lower()  # Normalize the sentence for better matching
        sentence = sentence.replace(".", "")
        sendNextWordStartTime = False
        combineSegementText = None
        for i, segment in enumerate(segments):
            if checkAfterSegment is None or segment["id"] >= checkAfterSegment["id"]:
                segment_text = segment["text"].strip().lower()
                segment_text = segment_text.replace(".", "")
                if combineSegementText is None:
                    combineSegementText = segment_text
                else:
                    combineSegementText += f" {segment_text}"
                if sendNextWordStartTime:
                    return segment
                if sentence in combineSegementText:
                    if type == "start":
                        return segment
                    else:
                        if i == len(segments) - 1:
                            return segment
                        sendNextWordStartTime = True

        return None
    
    def _post_success_process(self):
        id = self.type_instance.get_db_entry()[databasecon.getId("id")]

        self.update_video()
        
        self.type_instance.post_process(self.start_show_answer)
        databasecon.execute(f"""
                    UPDATE {custom_env.TABLE_NAME} 
                    SET video_processed = ?, lastModifiedTime = {int(time.time() * 1000)}
                    WHERE id = ?
                """, (1, id))
        gc.collect()
    
    def save_json_data(self, id, json_data):
        databasecon.execute(
            f"update {custom_env.TABLE_NAME} set json_data=? where id=?",
            values=(json.dumps(json_data, ensure_ascii=False), id)
        )

    def update_video(self, add_bg_music=False):
        id = self.type_instance.get_db_entry()[databasecon.getId("id")]
        databasecon.execute(f"""
                UPDATE {custom_env.TABLE_NAME}
                SET generatedVideoPath = ?, generatedThumbnailPath = ?, lastModifiedTime = {int(time.time() * 1000)}
                WHERE id = ?
            """, (self.generatedVideoPath, self.generatedThumbnailPath, id))

        if add_bg_music:
            json_data = json.loads(self.type_instance.get_db_entry()[databasecon.getId("json_data")])
            json_data.update({
                "add_bg_music": True
            })
            databasecon.execute(
                f"update {custom_env.TABLE_NAME} set json_data=? where id=?",
                values=(json.dumps(json_data, ensure_ascii=False), id)
            )