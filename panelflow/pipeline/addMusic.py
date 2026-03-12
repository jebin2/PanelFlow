from moviepy.editor import VideoFileClip, AudioFileClip, CompositeAudioClip, concatenate_videoclips
import numpy as np
from panelflow import common
from panelflow import config
from jebin_lib import utils
import subprocess, sys, os

def get_audio_rms(audio_clip, sample_duration=1.0):
    """
    Calculate RMS of an audio clip by sampling a segment.
    To avoid processing very long audio, we sample the first `sample_duration` seconds.
    """
    duration = min(sample_duration, audio_clip.duration)
    audio_segment = audio_clip.subclip(0, duration)
    audio_array = audio_segment.to_soundarray(fps=44100)
    return np.sqrt(np.mean(audio_array**2))

def calculate_bg_volume(main_rms, bg_rms):
    """
    Calculate background music volume based on both main audio and background music RMS levels.
    """
    # Base volume adjustment based on main audio level
    if main_rms > 0.03:  # High main audio level
        base_volume = 0.3
    elif main_rms > 0.01:  # Medium main audio level
        base_volume = 0.4
    else:  # Low main audio level
        base_volume = 0.5
    
    # Adjust based on background music loudness
    if bg_rms > 0.15:  # Very loud background music
        bg_volume = base_volume * 0.2  # Reduce significantly
    elif bg_rms > 0.08:  # Moderately loud background music
        bg_volume = base_volume * 0.4  # Reduce moderately
    elif bg_rms > 0.03:  # Normal background music
        bg_volume = base_volume * 0.6  # Keep base volume
    elif bg_rms > 0.01:  # Quiet background music
        bg_volume = base_volume * 0.8  # Boost slightly
    else:  # Very quiet background music
        bg_volume = base_volume * 1.2  # Boost more
    
    # Ensure volume stays within reasonable bounds
    bg_volume = max(0.1, min(0.8, bg_volume))
    
    return bg_volume

def process(video, audio_path=None, output_path=None, text=None, extend_video=False, trim_video=False, output_musicgen_path=None):
    if isinstance(video, str):
        video = VideoFileClip(video)

    if not audio_path and text:
        if utils.file_exists(output_musicgen_path):
            audio_path = output_musicgen_path
        else:
            subprocess.run([sys.executable, "create_music.py", text, output_musicgen_path], check=True, env={**os.environ, 'PYTHONUNBUFFERED': '1', 'CUDA_LAUNCH_BLOCKING': '1', 'USE_CPU_IF_POSSIBLE': 'true'})
            audio_path = output_musicgen_path
            utils.manage_gpu(action="clear_cache")

    new_audio = AudioFileClip(audio_path)

    # Handle duration matching (your existing code)
    if video.duration < new_audio.duration:
        if extend_video:
            loops_required = int(new_audio.duration // video.duration) + 2
            video = concatenate_videoclips([video] * loops_required)
            video = video.subclip(0, new_audio.duration)
        else:
            new_audio = new_audio.subclip(0, video.duration)
    else:
        if trim_video:
            video = video.subclip(0, new_audio.duration)
        else:
            from moviepy.audio.fx.all import audio_fadein, audio_fadeout
            from moviepy.editor import concatenate_audioclips
            fade_dur = 1.0
            clips = []
            t = 0

            while t < video.duration:
                part = new_audio.subclip(0, min(new_audio.duration, video.duration - t))
                part = audio_fadein(part, fade_dur)
                part = audio_fadeout(part, fade_dur)
                clips.append(part)
                t += part.duration
            new_audio = concatenate_audioclips(clips).set_duration(video.duration)

    original_audio = video.audio

    # Calculate both audio RMS levels for better volume adjustment
    if original_audio:
        # Calculate RMS for both audio sources
        main_rms = get_audio_rms(original_audio)
        bg_rms = get_audio_rms(new_audio)
        
        # Calculate optimal background volume
        bg_volume = calculate_bg_volume(main_rms, bg_rms)
        
        print(f"Main RMS: {main_rms:.4f}, BG RMS: {bg_rms:.4f}, BG Volume: {bg_volume:.2f}")
        
        # Apply volumes
        new_audio = new_audio.volumex(bg_volume)
        original_audio = original_audio.volumex(0.8)  # Keep main audio strong
        
        # Combine audio tracks
        combined_audio = CompositeAudioClip([original_audio, new_audio])
        video = video.set_audio(combined_audio)
    else:
        # If no original audio, still adjust background music based on its own level
        bg_rms = get_audio_rms(new_audio)
        
        # For videos without original audio, use a different scaling approach
        if bg_rms > 0.15:
            bg_volume = 0.5
        elif bg_rms > 0.08:
            bg_volume = 0.65
        elif bg_rms > 0.03:
            bg_volume = 0.8
        else:
            bg_volume = 1.0
            
        print(f"No main audio, BG RMS: {bg_rms:.4f}, BG Volume: {bg_volume:.2f}")
        video = video.set_audio(new_audio.volumex(bg_volume))

    if output_path:
        utils.write_videofile(video, output_path)

    return video