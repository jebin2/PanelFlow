import subprocess
import json
from typing import Dict, List, Optional
from custom_logger import logger_config
import custom_env
import common
import subprocess
import custom_env
import shutil
import os

class VideoConfig:
    def __init__(self, input_file: str, keep_only_default: bool = False):
        self.input_file = input_file
        self.output_file = f'{custom_env.TEMP_OUTPUT}/{common.generate_random_string()}_track_changer.{input_file.split(".")[-1]}'
        self.streams_info = self._get_streams_info()
        self.keep_only_default = keep_only_default

    def _get_streams_info(self) -> Dict:
        """Get detailed stream information using ffprobe."""
        cmd = [
            'ffprobe',
            '-v', 'quiet',
            '-print_format', 'json',
            '-show_streams',
            '-show_format',
            self.input_file
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return json.loads(result.stdout)
        except subprocess.CalledProcessError as e:
            raise Exception(f"Error analyzing file: {e}")

    def _find_best_english_audio(self) -> Optional[int]:
        """Find the English audio stream with the highest bitrate."""
        best_audio_index = None
        highest_bitrate = -1

        for stream in self.streams_info['streams']:
            if stream['codec_type'] == 'audio':
                # Check if stream is English
                is_english = False
                if 'tags' in stream:
                    language = stream['tags'].get('language', '').lower()
                    title = stream['tags'].get('title', '').lower()
                    is_english = (
                        language in ['eng', 'en'] or
                        'english' in title or
                        'eng' in title
                    )

                if is_english:
                    # Get bitrate
                    bitrate = 0
                    if 'bit_rate' in stream:
                        bitrate = int(stream['bit_rate'])
                    elif 'tags' in stream and 'BPS' in stream['tags']:
                        bitrate = int(stream['tags']['BPS'])
                    
                    if bitrate > highest_bitrate:
                        highest_bitrate = bitrate
                        best_audio_index = int(stream['index'])

        return best_audio_index

    def _find_best_english_subtitle(self) -> Optional[int]:
        """Find the English subtitle stream with the highest bitrate (if available)."""
        best_sub_index = None
        highest_bitrate = -1

        for stream in self.streams_info['streams']:
            codec_name = stream.get('codec_name', '').lower()
            if stream['codec_type'] == 'subtitle' and codec_name not in ['pgs', 'dvdsub', 'hdmv_pgs_subtitle', 'dvd_subtitle']:
                # Check if stream is English
                is_english = False
                if 'tags' in stream:
                    language = stream['tags'].get('language', '').lower()
                    title = stream['tags'].get('title', '').lower()
                    is_english = (
                        language in ['eng', 'en'] or
                        'english' in title or
                        'eng' in title
                    )

                if is_english:
                    # Get bitrate
                    bitrate = 0
                    if 'bit_rate' in stream:
                        bitrate = int(stream['bit_rate'])
                    elif 'tags' in stream and 'BPS' in stream['tags']:
                        bitrate = int(stream['tags']['BPS'])

                    if codec_name == 'ass':
                        bitrate += 1000  # Artificial boost for ASS format

                    txt_len, is_english = self._get_is_eng_sub_n_txt_len(f'0:{stream["index"]}', codec_name == "ass")
                    if txt_len > highest_bitrate and is_english:
                        highest_bitrate = txt_len
                        best_sub_index = int(stream['index'])

        return best_sub_index

    def optimize_tracks(self) -> None:
        """Optimize the tracks by setting the best English audio and subtitle as default."""
        best_audio_index = self._find_best_english_audio()
        best_sub_index = self._find_best_english_subtitle()
        logger_config.debug(f'best_audio_index:: {best_audio_index}')
        logger_config.debug(f'best_sub_index:: {best_sub_index}')

        if not best_audio_index:
            logger_config.warning("No English audio found!")

        if not best_sub_index:
            logger_config.warning("No Subtitle streams found!")
            return False

        # Prepare FFmpeg command
        cmd = ['ffmpeg', '-i', self.input_file, '-map', '0']

        # Reset all audio dispositions
        for i in range(len([s for s in self.streams_info['streams'] if s['codec_type'] == 'audio'])):
            cmd.extend([f'-disposition:a:{i}', '0'])

        # Reset all subtitle dispositions
        for i in range(len([s for s in self.streams_info['streams'] if s['codec_type'] == 'subtitle'])):
            cmd.extend([f'-disposition:s:{i}', '0'])

        audio_stream_number = None
        # Set best audio as default
        if best_audio_index is not None:
            audio_stream_number = len([s for s in self.streams_info['streams'][:best_audio_index] if s['codec_type'] == 'audio'])
            cmd.extend([f'-disposition:a:{audio_stream_number}', 'default'])

        sub_stream_number = None
        # Set best subtitle as default
        if best_sub_index is not None:
            sub_stream_number = len([s for s in self.streams_info['streams'][:best_sub_index] if s['codec_type'] == 'subtitle'])
            cmd.extend([f'-disposition:s:{sub_stream_number}', 'default'])

        # Copy all codecs (no re-encoding)
        cmd.extend(['-c', 'copy', self.output_file])

        cmd.extend(['-y'])

        # Execute FFmpeg command
        try:
            common.run_ffmpeg(cmd)
            logger_config.success(f"Successfully optimized tracks. Output saved to: {self.output_file}")
            try:
                if self.keep_only_default and sub_stream_number is not None:
                    if audio_stream_number is None:
                        audio_stream_number = 0

                    input_file = self.input_file.split("/")[-1]
                    output_path = None

                    if output_path:
                        cmd = [
                            "ffmpeg",
                            "-i", self.input_file,
                            "-map", "0:v:0",                        # Map the first video stream
                            "-map", f"0:a:{audio_stream_number}",   # Map the default audio stream
                            "-map", f"0:s:{sub_stream_number}",     # Map the default subtitle stream
                            "-c", "copy",                           # Copy streams without re-encoding
                            output_path,                            # Output file
                            "-y"                                    # Overwrite output file without prompting
                        ]
                        common.run_ffmpeg(cmd)
            except:
                pass
        except subprocess.CalledProcessError as e:
            raise Exception(f"Error optimizing tracks: {e}")

        return True

    def print_stream_info(self) -> List[Dict]:
        """Return stream information in structured format."""
        result = []
        
        for stream in self.streams_info['streams']:
            # Get language from tags
            language = None
            if 'tags' in stream:
                language = stream['tags'].get('language')

            stream_info = {
                "stream": f"0:{stream['index']}", # Format as 0:0, 0:1, etc.
                "type": stream['codec_type'],
                "codec_name": stream.get('codec_name', '').lower(),
                "is_default": False,
                "bps": None,  # Default to None if no bitrate info available
                "language": language
            }
            
            # Check if stream is default
            if 'disposition' in stream:
                stream_info["is_default"] = bool(stream['disposition'].get('default', 0))
            
            # Get bitrate information
            if 'bit_rate' in stream:
                stream_info["bps"] = int(stream['bit_rate'])
            elif 'tags' in stream and 'BPS' in stream['tags']:
                stream_info["bps"] = int(stream['tags']['BPS'])
            
            result.append(stream_info)
        
        # Print JSON formatted output
        logger_config.debug(json.dumps(result, indent=4, ensure_ascii=False))
        return result

    def _get_is_eng_sub_n_txt_len(self, steam, is_ass):
        text = None
        subs = self.extract_subtitle(steam, is_ass)
        if len(subs) > 0:
            text = ' '.join([dialog["text"] for dialog in subs])

        if text:
            return len(text), self.detect_language(text) == "en"

        return -1, False

    def detect_language(self, text):
        from langdetect import detect
        language = detect(text)
        logger_config.info(language)
        if language == 'ja':
            return "jp"
        elif language == 'en':
            return "en"
        else:
            return "unknown"

    def extract_subtitle(self, steam=None, is_ass=None):
        stream = steam
        is_ass = is_ass
        is_eng_audio = False

        if not steam:
            steamJson = self.print_stream_info()

            if not steamJson or not isinstance(steamJson, list):
                raise ValueError("print_stream_info() returned None or invalid data structure")

            audio_streams = [
                stam for stam in steamJson
                if stam.get("is_default") and stam.get("type") == "audio" and stam.get("language") and ('eng' in stam["language"] or 'en' in stam["language"])
            ]
            is_eng_audio = len(audio_streams) > 0

            sub_streams = [
                stam for stam in steamJson
                if stam.get("is_default") and stam.get("type") == "subtitle" and stam.get("language") and ('eng' in stam["language"] or 'en' in stam["language"])
            ]

            if not sub_streams:
                raise ValueError("No English subtitle stream found.")

            stream = sub_streams[0]["stream"]
            is_ass = sub_streams[0].get("codec_name") == "ass"

        logger_config.debug(f"stream:: {stream} is_ass :: {is_ass}")

        temp_path = f"{custom_env.TEMP_OUTPUT}/{common.generate_random_string()}.ass"

        command = [
            "ffmpeg",
            "-i", self.input_file,
            "-map", stream,
            temp_path,
            "-y"
        ]

        if not is_ass:
            command.extend(["-c:s", "srt"])

        common.run_ffmpeg(command)
        logger_config.success(f"Saved to {temp_path}")

        return self.process_sub(temp_path, self.input_file, is_eng_audio, is_ass)


    def rewrite_encoding(self, path):
        with open(path, "rb") as f:
            raw_data = f.read()

        import chardet
        detected = chardet.detect(raw_data)
        encoding = detected["encoding"]

        if encoding and encoding.lower() != "utf-8":
            logger_config.debug(f"Detected encoding: {encoding}. Converting to UTF-8.")

            decoded_data = raw_data.decode(encoding, errors="replace")

            with open(path, "w", encoding="utf-8") as f:
                f.write(decoded_data)
            logger_config.debug(f"File rewritten in UTF-8 encoding.")
        else:
            logger_config.debug(f"File is already UTF-8 encoded. No changes made.")

    def process_sub(self, path, videoPath, is_eng_audio=False, is_ass=False):
        self.rewrite_encoding(path)
        duration, _, _, _ = common.get_media_metadata(videoPath)
        import pysubs2
        subs = pysubs2.load(path, encoding="utf-8")

        text = None
        processed_subs = []
        for line in subs:
            if line.is_text and text != line.plaintext:
                text = line.plaintext

                # text = re.sub(r"{.*?}", "", line.text)  # Remove formatting (e.g., {\\an1})
                # text = re.sub(r"<.*?>", "", text)       # Remove HTML-like tags
                text = text.replace("\\N", " ")
                text = text.replace("\\n", " ")
                text = text.replace("\n", " ")
                text = text.strip()                    # Remove leading/trailing whitespace

                # if is_ass and line.style and "signs" in line.style.lower():
                #     continue  # Skip vector-based drawing subtitles

                if text and duration >= (line.end / 1000):
                    processed_subs.append({
                        "text": text,
                        "start": line.start / 1000,    # Start time in seconds
                        "end": line.end / 1000        # End time in seconds
                    })

        if len(processed_subs) > 0:
            shutil.copy(path, f'media/subtitles/{path.split("/")[-1]}')
            processed_subs[0]['sub_path'] = f'media/subtitles/{path.split("/")[-1]}'
            processed_subs[0]['is_eng_audio'] = is_eng_audio

        return processed_subs

def process_extract_sub(videoPath):
    try:
        videoConfig = VideoConfig(videoPath, True)
        base_name, _ = os.path.splitext(videoPath)
        srtPath = base_name + ".srt"

        if common.file_exists(srtPath):
            logger_config.debug(f"Extracted subtitle stream from {srtPath}")
            return videoConfig.process_sub(srtPath, videoPath, True)

        else:
            if videoConfig.optimize_tracks():
                shutil.copyfile(videoConfig.output_file, videoPath)

                videoConfig = VideoConfig(videoPath)
                return videoConfig.extract_subtitle()
    except Exception as e:
        logger_config.warning(f"Error in process_extract_sub {str(e)}")

    return None

if __name__ == "__main__":
    videoPath = "media/anime_review/Dragon Ball - Part 3/dragon ball - 022.mkv"
    logger_config.info(process_extract_sub(videoPath))