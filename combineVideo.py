from moviepy.editor import VideoFileClip, concatenate_videoclips, AudioFileClip
import gc
import os
import subprocess
from contextlib import ExitStack
from custom_logger import logger_config
from typing import List, Tuple
import common
import custom_env
import media_transitions
import random
from animate_image import ImageAnimator

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
                final_video = final_video.subclip(0, audio.duration)

            final_video = final_video.set_audio(audio)

        if do_animate:
            logger_config.debug(f"Adding animation {len(final_clips)} video clips")
            animator = ImageAnimator("video", clip=final_video)
            final_video = animator.diagonal_wave()

        final_video_audio = final_video.audio
        if final_video_audio:
            final_video_audio = final_video_audio.subclip(0, final_video_audio.duration-0.1)

        final_video = final_video.set_audio(final_video_audio)

        gc.collect()

        output_path = output_video_path
        if not output_path:
            output_path = f"{custom_env.VIDEO}/{common.generate_random_string()}.mp4"

        if os.path.exists(output_path):
            raise FileExistsError(f"File already exists: {output_path}")

        logger_config.debug(f"Rendering video: {output_path}")
        common.write_videofile(final_video, output_path, fps=fps)

        # Force cleanup
        final_video.close()
        if audio:
            audio.close()

        gc.collect()

    logger_config.debug(f"Video saved as {output_path}")
    return output_path

def start_ffmpeg(temp_files, audioPath=None, fps=None):
    gc.collect()
    output_path_video = f"{custom_env.TEMP_OUTPUT}/{common.generate_random_string()}.mp4"
    
    if common.file_exists(output_path_video):
        raise FileExistsError(f"File already exists: {output_path_video}")
    
    # Create a temporary text file listing all video files to concatenate
    list_file_path = os.path.join(custom_env.TEMP_OUTPUT, "temp_list.txt")
    with open(list_file_path, 'w') as f:
        for temp_file in temp_files:
            f.write(f"file '{temp_file}'\n")

    # Base ffmpeg command for concatenation without re-encoding
    ffmpeg_cmd = [
        'ffmpeg', '-f', 'concat', '-safe', '0', '-i', list_file_path,
        '-c', 'copy', '-loglevel', 'error', output_path_video
    ]

    # Run the ffmpeg command
    logger_config.debug(f"Concatenating {len(temp_files)} video clips without re-encoding")
    common.run_ffmpeg(ffmpeg_cmd)
    logger_config.success("success")
    
    # Optionally, add audio if provided
    if audioPath:
        logger_config.success("audiooo")
        # output_filename = f"{common.generate_random_string()}.wav"
        # audio_output_path = os.path.join(custom_env.TEMP_OUTPUT, f"{output_filename}")
        # audio.write_audiofile(audio_output_path, fps=fps)
        output_path_video_w_auduio = f"{custom_env.TEMP_OUTPUT}/{common.generate_random_string()}.mp4"
        ffmpeg_audio_cmd = [
            'ffmpeg', '-i', output_path_video, '-i', audioPath,
            '-c:v', 'copy', '-c:a', 'aac', '-shortest', '-loglevel', 'error', output_path_video_w_auduio
        ]
        common.run_ffmpeg(ffmpeg_audio_cmd)
        logger_config.success("2312312312")
    
    logger_config.debug(f"Video saved as {output_path_video_w_auduio}")
    
    gc.collect()

    return output_path_video_w_auduio