import os
import glob
import re
from custom_logger import logger_config
from panelflow import config
from pydub import AudioSegment
from jebin_lib import utils


def clean_text(text):
    return utils.clean_text(text)

def only_alpha(text: str) -> str:
    return utils.only_alpha(text)

def is_same_sentence(sentence_1, sentence_2, threshold=0.9):
    return utils.is_same_sentence(sentence_1, sentence_2, threshold)

def manage_gpu(size_gb: float = 0, gpu_index: int = 0, action: str = "check"):
    return utils.manage_gpu(size_gb, gpu_index, action)

def is_gpu_available(verbose=True):
    return utils.is_gpu_available(verbose)

def get_device(is_vision=False):
    return utils.get_device(is_vision)

def get_media_metadata(file_path):
    try:
        import ffmpeg
        probe = ffmpeg.probe(file_path, v='error', select_streams='v:0', show_entries='format=duration,streams')
        duration_in_sec_float = float(probe['format']['duration'])
        duration_in_sec_int = int(duration_in_sec_float)
        size = int(os.path.getsize(file_path) // (1024 * 1024))
        fps = None
        for stream in probe['streams']:
            if stream['codec_type'] == 'video':
                fps = eval(stream['r_frame_rate'])
        return duration_in_sec_int, duration_in_sec_float, size, fps
    except Exception as e:
        logger_config.error(f"Error retrieving media metadata: {e}")
        return None, None, None, None

def delete_matching_videos(output_dir, match_text):
    pattern = os.path.join(output_dir, match_text)
    for file_path in glob.glob(pattern):
        utils.remove_file(file_path)

def safe_json(obj):
    try:
        import json
        json.dumps(obj, ensure_ascii=False)
        return obj
    except TypeError:
        return str(obj.__class__.__name__)

def combineAudio(file_names, path=None, silence=1000):
    combined = AudioSegment.empty()
    file_len = len(file_names)
    for i, file_name in enumerate(file_names):
        if not utils.is_valid_audio(file_name):
            raise ValueError(f"Invalid audio. {file_name}")
        combined += AudioSegment.from_wav(file_name)
        if silence and silence > 0 and i + 1 < file_len:
            combined += AudioSegment.silent(duration=silence)
    audio_path = path if path else f'audio/{utils.generate_random_string()}.wav'
    combined.export(audio_path, format='wav')
    return audio_path
