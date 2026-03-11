import os
import platform

_arch = platform.machine()
BASE_PATH = os.path.dirname(__file__)

PARENT_BASE_PATH = os.path.dirname(BASE_PATH)

DATABASE = f'{BASE_PATH}/databases/entries.db'
TABLE_NAME='entries'
AUDIO_PATH = f'{BASE_PATH}/audio'
VIDEO="video"
VIDEO_PATH = f'{BASE_PATH}/{VIDEO}'
TEMP_OUTPUT = f'{BASE_PATH}/tempOutput'
FPS=24
IMAGE_SIZE=(1920, 1080)
MEDIA="media"
MODEL_NAME="gemini-3-flash-preview"
MODEL_NAME_LITE="gemini-flash-lite-latest"

REUSE_PATH = f"{BASE_PATH}/reuse"
REUSE_SPECIFIC_PATH = "."
SERVER_PORT=int(os.getenv("SERVER_PORT", "3000"))
AUTHORIZATION_CODE_PATH=f"{TEMP_OUTPUT}/code.txt"

COMIC_REVIEW="comic_review"
COMIC_SHORTS="comic_shorts"
COMIC_REVIEW_PATH=f'media/{COMIC_REVIEW}'
