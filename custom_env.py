import subprocess
import os

def _is_running_in_vm():
    try:
        output = subprocess.check_output(['whoami']).decode().strip()
        if "vboxuser" in output:
            return True
    except Exception:
        pass
    return False

isVM = _is_running_in_vm()
IS_DOCKER = os.getenv("IS_DOCKER", "False").lower() == "true"
IS_VPS = os.getenv("IS_VPS", "False").lower() == "true"
HAS_DISPLAY = bool(os.environ.get('DISPLAY')) or IS_VPS
USE_API_TTS_STT = True


OLLAMA_REQ_URL="http://172.28.156.132:11434" if isVM else "http://127.0.0.1:11434"
# Fallback to current directory if env var is not set, preventing "None/tempOutput" errors
CAPTION_CREATOR_BASE_PATH = os.getenv("CAPTION_CREATOR_BASE_PATH", os.getcwd())
ALL_PROJECT_BASE_PATH = os.getenv("ALL_PROJECT_BASE_PATH")
DATABASE = f'{CAPTION_CREATOR_BASE_PATH}/databases/entries.db'
BACKUP_DATABASE = f'{CAPTION_CREATOR_BASE_PATH}/databases/entries_backup.db'
TABLE_NAME='entries'
AUDIO_PATH = f'{CAPTION_CREATOR_BASE_PATH}/audio'
VIDEO="video"
VIDEO_PATH = f'{CAPTION_CREATOR_BASE_PATH}/{VIDEO}'
TEMP_OUTPUT = f'{CAPTION_CREATOR_BASE_PATH}/tempOutput'
FPS=24
IMAGE_SIZE=(1920, 1080)
GEN_AUDIO=True
GEN_VIDEO=True
MEDIA="media"
MODEL_NAME="gemini-3-flash-preview"
MODEL_NAME_LITE="gemini-flash-lite-latest"
ALL_MODEL_NAME=["gemini-3-flash-preview", "gemini-3.1-pro-preview", "gemini-3.1-flash-lite-preview", "gemini-flash-lite-latest"]
HEADLESS_MODE = IS_DOCKER or not HAS_DISPLAY
POWERSHELL = "/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"
REUSE_PATH = f"{CAPTION_CREATOR_BASE_PATH}/reuse"
REUSE_SPECIFIC_PATH = "."
BROWSER_EXECUTABLE= None if IS_DOCKER else "/usr/bin/brave-browser"
SERVER_PORT=int(os.getenv("SERVER_PORT", "3000"))
AUTHORIZATION_CODE_PATH=f"{TEMP_OUTPUT}/code.txt"
ENCRYPT_PATH=f"{CAPTION_CREATOR_BASE_PATH}/encrypt"
CAPTION_CREATOR_BROWSER_PROFILE = os.path.abspath(os.path.expanduser("~/.caption_creator_browser_profile"))


JSON_VALIDATOR_SYSTEM_PROMPT="""You are an expert JSON validator and fixer. For any provided JSON, you will:
1. Add missing double quotes around keys and string values
2. Fix missing/mismatched brackets and braces
3. Fix any escaped quotes within strings
4. Remove invalid line breaks within values
5. Remove trailing commas
6. Return the corrected, valid JSON while preserving all original content

Please return only the fixed JSON without additional commentary."""
CAPTIONED="_captioned_"

YOUTUBE_PUBLISHER="youtube_publisher"
X_PUBLISHER="x_publisher"
MAX_FRAME_FILE="_max_frame"

COMIC_REVIEW="comic_review"
COMIC_SHORTS="comic_shorts"
COMIC_REVIEW_PATH=f'media/{COMIC_REVIEW}'
