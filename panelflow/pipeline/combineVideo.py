from moviepy import VideoFileClip, concatenate_videoclips, AudioFileClip
import gc
import os
from contextlib import ExitStack
from custom_logger import logger_config
from typing import List, Tuple
from panelflow import config
from jebin_lib import utils
from panelflow.pipeline import media_transitions

def start(temp_files: List[str], audioPath, fps: float, do_animate = False, output_video_path=None, need_transitions = True) -> Tuple[str, str]:
    gc.collect()

    # Use ExitStack to ensure all video clips are properly closed
    with ExitStack() as stack:
        final_clips = [
            stack.enter_context(VideoFileClip(temp))  # audio=False reduces memory usage
            for temp in temp_files
        ]

        if len(final_clips) > 1:
            if need_transitions:
                logger_config.debug(f"Concatenating and adding transitions {len(final_clips)} video clips")
                final_video = media_transitions.make(final_clips)
            else:
                final_video = concatenate_videoclips(
                    final_clips,
                    method="chain"
                )
        else:
            final_video = final_clips[0]

        gc.collect()

        audio = None
        if audioPath:
            audio = AudioFileClip(audioPath)
            if final_video.duration > audio.duration:
                logger_config.debug(f'trimming video: {final_video.duration - audio.duration}')
                final_video = final_video.subclipped(0, audio.duration)

            final_video = final_video.with_audio(audio)

        final_video_audio = final_video.audio
        if final_video_audio:
            final_video_audio = final_video_audio.subclipped(0, final_video_audio.duration-0.1)

        final_video = final_video.with_audio(final_video_audio)

        gc.collect()

        output_path = output_video_path
        if not output_path:
            output_path = f"{config.TEMP_PATH}/{utils.generate_random_string()}.mp4"

        if os.path.exists(output_path):
            raise FileExistsError(f"File already exists: {output_path}")

        logger_config.debug(f"Rendering video: {output_path}")
        utils.write_videofile(final_video, output_path, fps=fps)

        # Force cleanup
        final_video.close()
        if audio:
            audio.close()

        gc.collect()

    logger_config.debug(f"Video saved as {output_path}")
    return output_path

