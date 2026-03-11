import os

IS_DOCKER = os.getenv("IS_DOCKER", "False").lower() == "true"
IS_VPS = os.getenv("IS_VPS", "False").lower() == "true"
HAS_DISPLAY = bool(os.environ.get('DISPLAY')) or IS_VPS
# Fallback to current directory if env var is not set, preventing "None/tempOutput" errors
CAPTION_CREATOR_BASE_PATH = os.getenv("CAPTION_CREATOR_BASE_PATH", os.getcwd())
ALL_PROJECT_BASE_PATH = os.getenv("ALL_PROJECT_BASE_PATH")
DATABASE = f'{CAPTION_CREATOR_BASE_PATH}/databases/entries.db'
TABLE_NAME='entries'
AUDIO_PATH = f'{CAPTION_CREATOR_BASE_PATH}/audio'
VIDEO="video"
VIDEO_PATH = f'{CAPTION_CREATOR_BASE_PATH}/{VIDEO}'
TEMP_OUTPUT = f'{CAPTION_CREATOR_BASE_PATH}/tempOutput'
FPS=24
IMAGE_SIZE=(1920, 1080)
MEDIA="media"
MODEL_NAME="gemini-3-flash-preview"
MODEL_NAME_LITE="gemini-flash-lite-latest"
ALL_MODEL_NAME=["gemini-3-flash-preview", "gemini-3.1-pro-preview", "gemini-3.1-flash-lite-preview", "gemini-flash-lite-latest"]
HEADLESS_MODE = IS_DOCKER or not HAS_DISPLAY
REUSE_PATH = f"{CAPTION_CREATOR_BASE_PATH}/reuse"
REUSE_SPECIFIC_PATH = "."
SERVER_PORT=int(os.getenv("SERVER_PORT", "3000"))
AUTHORIZATION_CODE_PATH=f"{TEMP_OUTPUT}/code.txt"

YOUTUBE_PUBLISHER="youtube_publisher"
X_PUBLISHER="x_publisher"
MAX_FRAME_FILE="_max_frame"

COMIC_REVIEW="comic_review"
COMIC_SHORTS="comic_shorts"
COMIC_REVIEW_PATH=f'media/{COMIC_REVIEW}'
