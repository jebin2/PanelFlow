from moviepy.editor import AudioFileClip, CompositeAudioClip
from moviepy.audio.fx.all import audio_loop, volumex
import common
import custom_env
from custom_logger import logger_config
import random

MUSIC= {
    "1": {
        "path": "media/background_music/Somewhere Fuse - French Fuse.mp3",
        "sub_clip":(1, 11),
        "volume_1": 1.4,
        "volume_2": 0.1
    },
    "2": {
        "path": "media/background_music/Today Remains Sweet - Lish Grooves.mp3",
        "sub_clip":(2, 14),
        "volume_1": 1.4,
        "volume_2": 0.3
    },
    "3": {
        "path": "media/background_music/Lazy River Dream.mp3",
        "sub_clip":(0, 12.324),
        "volume_1": 1.4,
        "volume_2": 0.2
    },
    "4": {
        "path": "media/background_music/Lazy River Dream.mp3",
        "sub_clip":(104.332, 111.511),
        "volume_1": 1.4,
        "volume_2": 0.1
    },
    "5": {
        "path": "media/background_music/The New Order - Aaron Kenny.mp3",
        "sub_clip":(0, 4.490),
        "volume_1": 1.4,
        "volume_2": 0.6
    },
    "6": {
        "path": "media/background_music/The New Order - Aaron Kenny.mp3",
        "sub_clip":(24.480, 26.756),
        "volume_1": 1.4,
        "volume_2": 0.05
    },
    "7": {
        "path": "media/background_music/Midnight Whispers.mp3",
        "sub_clip":(1.975, 8.325),
        "volume_1": 2,
        "volume_2": 0.1
    },
    "8": {
        "path": "media/background_music/Midnight Whispers.mp3",
        "sub_clip":(98.907, 114.850),
        "volume_1": 2,
        "volume_2": 0.05
    },
    "9": {
        "path": "media/background_music/output.wav",
        "sub_clip":(0, -1),
        "volume_1": 2,
        "volume_2": 1
    }
}

def merge(audio_1, audio_2=None, audio_2_index=[3, 4, 7, 8], volume_1=None, volume_2=None, fps=44100):

    bg_music = None
    if audio_2_index:
        audio_2_index = random.choice(audio_2_index) if audio_2_index else random.choice(list(MUSIC.keys()))

        bg_music = MUSIC[f"{audio_2_index}"]
        audio_2 = bg_music['path']

    volume_1 = volume_1 if volume_1 else bg_music['volume_1']
    volume_2 = volume_2 if volume_2 else bg_music['volume_2']

    # Load audio clips and set fps
    audio_clip_1 = AudioFileClip(audio_1).set_fps(fps)
    audio_clip_2 = AudioFileClip(audio_2).set_fps(fps)
    if bg_music['sub_clip'][1] == -1:
        audio_clip_2 = audio_clip_2.subclip(bg_music['sub_clip'][0], bg_music['sub_clip'][1]) if bg_music else audio_clip_2

    # Loop audio_clip_2 to match audio_clip_1 duration if needed
    if audio_clip_1.duration > audio_clip_2.duration:
        audio_clip_2 = audio_loop(audio_clip_2, duration=audio_clip_1.duration)

    if audio_clip_2.duration > audio_clip_1.duration:
        audio_clip_2 = audio_clip_2.subclip(0, audio_clip_1.duration)

    # Adjust volume levels
    audio_clip_1 = volumex(audio_clip_1, volume_1)
    audio_clip_2 = volumex(audio_clip_2, volume_2)

    # Combine audio clips
    combined_audio = CompositeAudioClip([audio_clip_1, audio_clip_2])
    combined_audio.fps = fps

    # Generate output path and check for existence
    output_path = f'{custom_env.AUDIO_PATH}/{common.generate_random_string()}_merge_audio.wav'
    if common.file_exists(output_path):
        raise Exception(f"file already exists: {output_path}")

    # Write combined audio to file
    common.write_audiofile(combined_audio, output_path, fps=fps)
    combined_audio.close()
    logger_config.debug(output_path)
    return output_path

if __name__ == "__main__":
    merge(f"{custom_env.ALL_PROJECT_BASE_PATH}/CaptionCreator/tempOutput/tZHedxvzPD.wav")