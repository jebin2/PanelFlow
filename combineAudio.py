from pydub import AudioSegment
import common

def start(file_names, path=None, silence=1000):  # Default silence = 1 sec
    combined = AudioSegment.empty()

    # Loop through the file names and append them to the combined audio
    file_len = len(file_names)
    for i, file_name in enumerate(file_names):
        if not common.is_valid_wav(file_name):
            raise ValueError(f"Invalid audio. {file_name}")
        audio = AudioSegment.from_wav(file_name)
        combined += audio
        
        # Add silence only between files
        if silence and silence > 0 and i + 1 < file_len:
            combined += AudioSegment.silent(duration=silence)  # Corrected

    # Generate output path
    audio_path = path if path else f'audio/{common.generate_random_string()}.wav'

    combined.export(audio_path, format='wav')
    return audio_path
