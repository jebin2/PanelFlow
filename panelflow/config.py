import os

BASE_PATH = os.path.dirname(os.path.dirname(__file__))

TEMP_PATH = os.path.join(BASE_PATH, 'temp')
os.makedirs(TEMP_PATH, exist_ok=True)
os.environ["TEMP_OUTPUT"] = TEMP_PATH

CONTENT_TO_BE_PROCESSED = os.path.join(BASE_PATH, 'content_to_be_processed')
os.makedirs(CONTENT_TO_BE_PROCESSED, exist_ok=True)

FPS = 24
IMAGE_SIZE = (1920, 1080)

# Gemini (vision provider). LITE is the model gemini_config wraps for 1.3.
MODEL_NAME = "gemini-3-flash-preview"
MODEL_NAME_LITE = "gemini-flash-lite-latest"

SUBPROCESS_ENV = {**os.environ, 'PYTHONUNBUFFERED': '1',
                  'CUDA_LAUNCH_BLOCKING': '1', 'USE_CPU_IF_POSSIBLE': 'true'}
