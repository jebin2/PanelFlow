import os
import platform

_arch = platform.machine()
_pkg_dir = os.path.dirname(__file__)

BASE_PATH = os.path.dirname(_pkg_dir)

TEMP_PATH = os.path.join(BASE_PATH, 'temp')
os.makedirs(TEMP_PATH, exist_ok=True)
os.environ["TEMP_OUTPUT"] = TEMP_PATH

PANELS_TO_BE_PROCESSED = os.path.join(BASE_PATH, 'panels_to_be_processed')
os.makedirs(PANELS_TO_BE_PROCESSED, exist_ok=True)

COMIC="comic"
CATEGORY=[COMIC]

HF_BUCKET_ID = os.getenv("HF_BUCKET_ID")

FPS = 24
IMAGE_SIZE = (1920, 1080)

# Prompts
CREATE_MUSIC_SYSTEM_PROMPT = BASE_PATH + "/panelflow/prompt/create_music_system_prompt.md"
MODEL_NAME="gemini-3-flash-preview"
MODEL_NAME_LITE="gemini-flash-lite-latest"

SUBPROCESS_ENV = {**os.environ, 'PYTHONUNBUFFERED': '1', 'CUDA_LAUNCH_BLOCKING': '1', 'USE_CPU_IF_POSSIBLE': 'true'}