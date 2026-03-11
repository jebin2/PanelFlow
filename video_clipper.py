import custom_env
import common
from custom_logger import logger_config
import subprocess
import os

def format_timestamp(seconds):
    """Convert seconds to HH:MM:SS.nnn format"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:06.3f}"

def clip_mkv(video_path, start_time, end_time, suffix='', output_path=None):
    try:
        if not output_path:
            output_path = f'{custom_env.TEMP_OUTPUT}/{common.generate_random_string()}{suffix}.mkv'

        start_ts = format_timestamp(float(start_time))
        end_ts = format_timestamp(float(end_time))

        logger_config.debug(f"Splitting MKV from {start_ts} to {end_ts}")

        # Build mkvmerge command
        command = [
            "mkvmerge",
            "-o", output_path,    # Output file
            "--split", f"parts:{start_ts}-{end_ts}",  # Split points
            video_path           # Input file
        ]

        subprocess.run(command, check=True, stdout=subprocess.DEVNULL)

        return output_path

    except Exception as e:
        logger_config.error(f"Unexpected error during MKV clipping: {str(e)}")
        raise

def clip(video_path, start_time, end_time, subtitle_path=None, suffix='', index=None, output_path=None):
    if end_time is None or float(start_time) == float(end_time):
        # Single frame extraction
        if not output_path:
            output_path = f'{custom_env.TEMP_OUTPUT}/{common.generate_random_string()}{suffix}.png'
        try:
            cmd = [
                'ffmpeg', '-y',
                '-ss', str(start_time),
                '-i', video_path,
                '-vframes', '1',
                output_path
            ]
            common.run_ffmpeg(cmd)
            
            logger_config.success(f"Extracted single frame:: {output_path}")
            return output_path
        except Exception as e:
            logger_config.error(f"Failed to extract frame at {start_time}: {str(e)}")
            raise
    else:
        if not output_path:
            output_path = f'{custom_env.TEMP_OUTPUT}/{common.generate_random_string()}{suffix}.mp4'
        if video_path.endswith(".mkv"):
            output_path = clip_mkv(video_path, start_time, end_time, suffix, output_path=output_path)
        else:

            # Use subprocess instead of ffmpeg-python wrapper for better control/debugging
            cmd = [
                'ffmpeg', '-y',
                '-ss', str(start_time),
                '-to', str(end_time),
                '-i', video_path,
                '-c:v', 'copy',
                '-c:a', 'copy',
                '-avoid_negative_ts', 'make_zero',
                output_path
            ]
            common.run_ffmpeg(cmd)

            clip_with_subtitle(video_path, start_time, end_time, subtitle_path, output_path, index)

        logger_config.success(f"Clipped video:: {output_path}")
        return output_path

def clip_with_subtitle(video_path, start_time, end_time, subtitle_path, output_path, index):
    try:
        if subtitle_path:
            # Base command
            subtitle_command = [
                'ffmpeg', '-y',
                '-i', video_path,
                '-ss', str(start_time),
                '-to', str(end_time),
                '-filter_complex', f"subtitles={subtitle_path}",
                '-c:v', 'libx264',
                '-c:a', 'copy',
                output_path.replace(".mp4", "_sub.mp4")
            ]
            
            common.run_ffmpeg(subtitle_command)
            logger_config.info(f"completed Index:: {index}")
    except Exception as e:
        # Handle exception if needed (optional, since you're ignoring results)
        pass

def fast_subclip(video_path, start_sec=0, end_sec=None, output_path=None):
    """
    Extract a subclip from a video without re-encoding, avoiding overwrites.
    Uses a fixed path defined by custom_env.REUSE_SPECIFIC_PATH.
    
    Args:
        video_path (str): Path to the input video.
        start_sec (float): Start time in seconds (default 0).
        end_sec (float): End time in seconds (default video duration).
        
    Returns:
        str: Path to the output video.
    """
    base_name = os.path.splitext(os.path.basename(video_path))[0]

    if not output_path:
        output_path = os.path.join(
            custom_env.REUSE_SPECIFIC_PATH,
            f"{base_name}_{start_sec}_{end_sec}.mp4"
        )

    if common.file_exists(output_path):
        logger_config.info(f"Clipped from {start_sec} to {end_sec} : duration: {end_sec - start_sec}")
        return output_path

    # Build ffmpeg command for fast subclip (no re-encoding)
    cmd = ["ffmpeg", "-y"]  # -y to overwrite existing files

    # CRITICAL FIX: Put -ss BEFORE -i for accurate seeking
    if start_sec > 0:
        cmd += ["-ss", f"{start_sec:.3f}"]
    
    # Input file first
    cmd += ["-i", str(video_path)]
    
    # Duration instead of end time for more reliable results
    duration_part = end_sec - start_sec
    cmd += ["-t", f"{duration_part}"]
    
    # Copy streams without re-encoding for speed
    cmd += ["-c", "copy"]
    
    # Avoid negative timestamps and other issues
    cmd += ["-avoid_negative_ts", "make_zero"]
    
    # Output file
    cmd += [str(output_path)]

    # Run ffmpeg
    common.run_ffmpeg(cmd)

    logger_config.info(f"Clipped from {start_sec} to {end_sec} : duration: {end_sec - start_sec}")
    return output_path

if __name__ == "__main__":
    video_path = "media/anime_review/Dragon Ball Daima - 19.mkv"
    duration, _, _, _ = common.get_media_metadata(video_path)
    clip(video_path, (1 * (60)) + 41, duration-70)