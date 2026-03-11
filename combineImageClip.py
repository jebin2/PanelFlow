from moviepy.editor import ImageClip, concatenate_videoclips, ImageSequenceClip
from PIL import Image, ImageSequence
import gc
import os
from contextlib import ExitStack
from custom_logger import logger_config
from typing import List, Dict
import custom_env
import common
from animate_image import ImageAnimator
import traceback
import media_transitions
import numpy as np

def create_image_clip(clip_info, animate_type=None) -> ImageClip:
    if animate_type and (('donot_animate' in clip_info and not clip_info['donot_animate']) or 'donot_animate' not in clip_info):
        return create_animated_image_clip(clip_info, animate_type)
    else:
        # Check for overlay GIF
        if 'overlay_clip' in clip_info and clip_info['overlay_clip']:
            background = Image.open(clip_info['img_path']).convert("RGBA")
            clip_duration = clip_info['clip_duration']
            fps = custom_env.FPS
            num_frames = int(clip_duration * fps)
            gif_path = clip_info['overlay_clip']

            # Load and resize GIF frames
            gif = Image.open(gif_path)
            gif_frames = [frame.convert("RGBA") for frame in ImageSequence.Iterator(gif)]
            gif_frame_count = len(gif_frames)

            position = clip_info.get('overlay_position', (420, 0))

            composited_frames = []
            for i in range(num_frames):
                bg_copy = background.copy()
                gif_frame = gif_frames[i % gif_frame_count]
                bg_copy.paste(gif_frame, position, gif_frame)  # Paste with transparency
                composited_frames.append(np.array(bg_copy.convert("RGB")))

            # Create video from merged frames
            final_clip = ImageSequenceClip(composited_frames, fps=fps)
            return final_clip.set_start(clip_info['clip_start'])

        clip = ImageClip(clip_info['img_path'])
        clip = clip.set_duration(clip_info['clip_duration']).set_start(clip_info['clip_start'])
        return clip

def create_animated_image_clip(clip_info, animate_type=None):
    animator = ImageAnimator("image", path=clip_info['img_path'], duration=clip_info['clip_duration'], start_time=clip_info['clip_start'])

    if animate_type == "gentle_ripple":
        clip = animator.gentle_ripple()
    elif animate_type == "top_bottom_zoom":
        clip = animator.create_top_bottom_zoom(zoom_height=custom_env.IMAGE_SIZE[1])
    elif animate_type == "left_right_zoom":
        clip = animator.create_left_right_zoom(zoom_width=custom_env.IMAGE_SIZE[1]) # shorts
    elif animate_type == "zoom_out_zoom_in_to_full":
        from scale_clip import create_scale_up_clip_multiple
        if 'IMAGE_SIZE' not in clip_info:
            clip_info['IMAGE_SIZE'] = custom_env.IMAGE_SIZE
        clip = create_scale_up_clip_multiple(
            main_image_path=clip_info['img_path'],
            duration=clip_info['clip_duration'],
            bg_size=clip_info['IMAGE_SIZE'],
            zoom_coords={
		        0: clip_info["face_location"] if "face_location" in clip_info and clip_info["face_location"] else (0, 0, clip_info["IMAGE_SIZE"][0], clip_info["IMAGE_SIZE"][1])
            },
            bg_blur=clip_info['bg_blur'] if 'bg_blur' in clip_info else True,
        )
    else:
        clip = animator.diagonal_wave()

    return clip

def process_batch(batch: List[Dict], fps: float, batch_index: int, total_size: int, animate_type="zoom_out_zoom_in_to_full", need_transitions = False) -> str:
    with ExitStack() as stack:
        clips = []
        logger_config.debug("for overwrite")
        for clip_info in batch:
            try:
                clip = create_image_clip(clip_info, animate_type)
                clip = stack.enter_context(clip)
                clips.append(clip)
                logger_config.debug(
                    f"Clip Created {clip_info['img_path'].split(custom_env.CAPTION_CREATOR_BASE_PATH)[-1]} "
                    f"start: {clip_info['clip_start']} "
                    f"duration: {clip_info['clip_duration']}"
                , overwrite=True)
            except Exception as e:
                raise ValueError(f"Error processing clip {clip_info['img_path']}: {str(e)}\n{traceback.format_exc()}")

        if not clips:
            raise ValueError("No valid clips in batch")

        output_path = f"{custom_env.TEMP_OUTPUT}/{common.generate_random_string()}.mp4"
        
        if os.path.exists(output_path):
            raise FileExistsError(f"File already exists: {output_path}")

        if need_transitions:
            logger_config.debug(f"Combining and adding transitions {len(clips)} images at index {batch_index} (total: {total_size})")
            final_video = media_transitions.make(clips)
        else:
            logger_config.debug(f"Combining {len(clips)} images at index {batch_index} (total: {total_size})")

            final_video = concatenate_videoclips(
                clips,
                method="chain"
            )

        common.write_videofile(final_video, output_path, fps=fps)

        final_video.close()
        del final_video
        del clips
        gc.collect()

        logger_config.debug(f"Batch processing completed: {output_path}")
        return output_path

def start(images: List[Dict], fps: float = custom_env.FPS, animate_type="zoom_out_zoom_in_to_full", need_transitions=True) -> List[str]:
    try:
        gc.collect()
        logger_config.debug("Starting image clip combination process...")

        temp_files = []
        batch_size = 500  # Reduced batch size for better memory management
        total_size = len(images)

        batches = [
            images[i:i + batch_size]
            for i in range(0, total_size, batch_size)
        ]
        for i, batch in enumerate(batches):
            output_path = process_batch(batch, fps, i * batch_size, total_size, animate_type, need_transitions)
            temp_files.append(output_path)

        if not temp_files:
            raise ValueError("No video segments were successfully created")

        logger_config.success(f"Successfully combined {len(temp_files)} video segments")
        return temp_files

    except Exception as e:
        raise Exception(f"Failed to combine image clips: {str(e)} {traceback.format_exc()}")

    finally:
        gc.collect()

if __name__ == "__main__":
    logger_config.info(start([{
        "img_path": f"{custom_env.ALL_PROJECT_BASE_PATH}/CaptionCreator/tempOutput/resized.png",
        "clip_duration": 4.49,
        "clip_start": 0
    }]))