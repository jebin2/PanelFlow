import os
import platform

_arch = platform.machine()
_pkg_dir = os.path.dirname(__file__)

BASE_PATH = os.path.dirname(_pkg_dir)

TEMP_PATH = os.path.join(BASE_PATH, 'temp')
os.makedirs(TEMP_PATH, exist_ok=True)
os.environ["TEMP_OUTPUT"] = TEMP_PATH

CONTENT_TO_BE_PROCESSED = os.path.join(BASE_PATH, 'content_to_be_processed')
os.makedirs(CONTENT_TO_BE_PROCESSED, exist_ok=True)

COMIC="comic"
COMIC_DIR=f"{CONTENT_TO_BE_PROCESSED}/{COMIC}"

CATEGORY=[COMIC]

HF_BUCKET_ID = os.getenv("HF_BUCKET_ID")
HF_TOKEN = os.getenv("HF_TOKEN")
HF_MOUNT_PATH = os.getenv("HF_MOUNT_PATH")

FPS = 24
IMAGE_SIZE = (1920, 1080)

# Prompts
CREATE_MUSIC_SYSTEM_PROMPT = BASE_PATH + "/panelflow/prompt/create_music_system_prompt.md"
with open(BASE_PATH + "/panelflow/prompt/all_page_recap_prompt.md", "r") as f:
    ALL_PAGE_RECAP_PROMPT = f.read()
with open(BASE_PATH + "/panelflow/prompt/comic_review_system_prompt.md", "r") as f:
    COMIC_REVIEW_SYSTEM_PROMPT = f.read()
with open(BASE_PATH + "/panelflow/prompt/comic_recap_user_prompt.md", "r") as f:
    COMIC_RECAP_USER_PROMPT = f.read()
with open(BASE_PATH + "/panelflow/prompt/comic_dialogue_matcher_prompt.md", "r") as f:
    COMIC_DIALOGUE_MATCHER_PROMPT = f.read()
with open(BASE_PATH + "/panelflow/prompt/comic_title_desc_system_prompt.md", "r") as f:
    COMIC_TITLE_DESC_SYSTEM_PROMPT = f.read()

BG_MUSIC_PATH = BASE_PATH + "/bg_music/848419_8470157-lq.mp3"

MODEL_NAME="gemini-3-flash-preview"
MODEL_NAME_LITE="gemini-flash-lite-latest"

SUBPROCESS_ENV = {**os.environ, 'PYTHONUNBUFFERED': '1', 'CUDA_LAUNCH_BLOCKING': '1', 'USE_CPU_IF_POSSIBLE': 'true'}