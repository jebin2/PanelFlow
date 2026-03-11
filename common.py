from pathlib import Path
import os
import shutil
import string
from custom_logger import logger_config
import databasecon
import custom_env
import secrets
import hashlib
import random
import time
import glob
import re
import requests
import subprocess
import psutil

def path_exists(path):
    return file_exists(path) or dir_exists(path)

def file_exists(file_path):
    try:
        return Path(file_path).is_file()
    except:
        pass
    return False

def dir_exists(file_path):
    try:
        return Path(file_path).is_dir()
    except:
        pass
    return False

def list_files_recursive(directory):
    remove_zone_identifier(directory)
    # Initialize an empty array to store the file paths
    file_list = []
    
    # Walk through the directory recursively
    for root, dirs, files in os.walk(directory):
        for file in files:
            # Get the full path of the file and append to the array
            file_list.append(os.path.join(root, file))
    
    return file_list

def list_directories_recursive(directory):
    remove_zone_identifier(directory)
    # Initialize an empty list to store the directory names
    directory_list = []
    
    # Walk through the directory recursively
    for root, dirs, files in os.walk(directory):
        for dir_name in dirs:
            # Get the full path of the directory and append to the list
            directory_list.append(os.path.join(root, dir_name))
    
    return directory_list

def remove_zone_identifier(directory):
    try:
        for root, dirs, files in os.walk(directory):
            for file in files:
                if file.endswith(":Zone.Identifier"):
                    full_path = os.path.join(root, file)
                    remove_file(full_path)
    except: pass


def list_files(directory):
    if not dir_exists(directory):
        return []

    remove_zone_identifier(directory)
    # Initialize an empty array to store the file paths
    file_list = []
    
    # Get the list of files in the given directory (non-recursive)
    for file in os.listdir(directory):
        # Construct the full path and check if it's a file
        full_path = os.path.join(directory, file)
        if os.path.isfile(full_path):
            file_list.append(full_path)
    
    return file_list

def remove_file(file_path, retry=True):
    try:
        # Check if the file exists
        if os.path.exists(file_path):
            Path(file_path).unlink()
            logger_config.success(f"{file_path} has been removed successfully.")
    except Exception as e:
        logger_config.warning(f"Error occurred while trying to remove the file: {e}")
        if retry:
            logger_config.debug("retrying after 10 seconds", seconds=10)
            remove_file(file_path, False)

def remove_all_files_and_dirs(directory):
    try:
        if Path(directory).exists():
            shutil.rmtree(directory)  # Recursively delete a directory
    except Exception as e:
        logger_config.warning(f"Failed to delete {directory}. Reason: {e}")

def remove_directory(directory_path):
    try:
        if os.path.exists(directory_path):
            shutil.rmtree(directory_path)
            logger_config.debug(f'Directory Deleted at: {directory_path}')
    except Exception as e:
        logger_config.warning(f'An error occurred: {e}')

def create_directory(directory_path):
    try:
        # Create the directory
        if not os.path.exists(directory_path):
            os.makedirs(directory_path, exist_ok=True)  # exist_ok=True avoids error if the dir already exists
    except Exception as e:
        logger_config.error(f'An error occurred: {e}')

def generate_random_string(length=10):
    characters = string.ascii_letters
    random_string = ''.join(secrets.choice(characters) for _ in range(length))
    return random_string

def generate_random_string_from_input(input_string, length=16):
    # Hash the input string to get a consistent value
    hash_object = hashlib.sha256(input_string.encode())
    hashed_string = hash_object.hexdigest()

    # Use the hash to seed the random number generator
    random.seed(hashed_string)

    # Generate a random string based on the seed
    characters = string.ascii_letters + string.digits
    random_string = ''.join(random.choice(characters) for _ in range(length))

    return random_string

def copy(source, dest):
    try:
        shutil.copy2(source, dest)
        logger_config.success(f"Copied file from '{source}' to '{dest}'")
    except Exception as e:
        logger_config.error(f"An error occurred: {e}")

def clean_text(text):
    text = re.sub(r"\\+", "", text)
    return re.sub(r'\s+', ' ', text).strip()

def get_media_metadata(file_path):
    try:
        import ffmpeg
        probe = ffmpeg.probe(file_path, v='error', select_streams='v:0', show_entries='format=duration,streams')

        # Duration in float seconds
        duration_in_sec_float = float(probe['format']['duration'])
        duration_in_sec_int = int(duration_in_sec_float)

        # File size in MB
        size = int(os.path.getsize(file_path) // (1024 * 1024))

        fps = None
        for stream in probe['streams']:
            if stream['codec_type'] == 'video':
                fps = eval(stream['r_frame_rate'])  # Frames per second (r_frame_rate is in format num/den)

        return duration_in_sec_int, duration_in_sec_float, size, fps
    except Exception as e:
        logger_config.error(f"Error retrieving media metadata: {e}")
        return None, None, None, None

def write_videofile(video_clip, output_path, fps=custom_env.FPS):
    audio_file = f'{custom_env.TEMP_OUTPUT}/{generate_random_string()}.mp3'
    video_clip.write_videofile(
        output_path,
        fps=fps,
        codec='libx264',
        # audio_codec='aac',
        # preset='faster',  # Faster encoding, slightly larger file
        threads=get_threads(),
        bitrate='8000k',  # Adjust based on your quality needs
        remove_temp=True,
        temp_audiofile=audio_file
    )
    remove_file(audio_file)

def write_audiofile(audio_clip, output_path, fps=44100, codec="libmp3lame", bitrate="192k"):
    audio_clip.write_audiofile(
        output_path,
        fps=fps,
        codec=codec,
        bitrate=bitrate
    )

def download_image(image_url, save_path, throw_error=False):
	response = requests.get(image_url, stream=True)
	if response.status_code == 200:
		with open(save_path, 'wb') as file:
			for chunk in response.iter_content(1024):
				file.write(chunk)
	elif throw_error:
		raise ValueError(f"Error: Unable to download image, status code {response.status_code}")

def get_html_content(url):
    response = requests.get(url)
    if response.status_code != 200:
        raise ValueError(f"Error: Unable to fetch page, status code {response.status_code}")

    return response.content

def delete_matching_videos(output_dir, match_text):
    """
    Delete all MP4 files matching pattern {index:04d}_*.mp4 in the given output directory.
    """
    pattern = os.path.join(output_dir, match_text)
    matching_files = glob.glob(pattern)

    for file_path in matching_files:
        remove_file(file_path)

def safe_json(obj):
    try:
        import json
        json.dumps(obj, ensure_ascii=False)
        return obj
    except TypeError:
        return str(obj.__class__.__name__)  # fallback: just print the type

def is_valid_wav(file_path):
    """Check if the given file is a valid WAV audio file."""
    try:
        if not file_exists(file_path):
            return False
        import wave
        with wave.open(file_path, 'rb') as wav_file:
            # Try to read basic properties
            wav_file.getnchannels()
            wav_file.getsampwidth()
            wav_file.getframerate()
            wav_file.getnframes()
            wav_file.readframes(1)
        return True
    except wave.Error as e:
        logger_config.error(f"Invalid WAV file: {e}")
        return False
    except Exception as e:
        logger_config.error(f"Unexpected error invalid audio: {e}")
        return False

def only_alpha(text: str) -> str:
    # Keep only alphabetic characters (make lowercase to ignore case)
    return re.sub(r'[^a-zA-Z]', '', text).lower()

def is_same_sentence(sentence_1, sentence_2, threshold=0.9):
    # Clean both
    sentence_1 = only_alpha(sentence_1)
    sentence_2 = only_alpha(sentence_2)

    import difflib
    similarity = difflib.SequenceMatcher(None, sentence_1, sentence_2).ratio()
    logger_config.info(f"is_same_sentence :: similarity-{similarity}")
    return similarity > threshold

def manage_gpu(size_gb: float = 0, gpu_index: int = 0, action: str = "check"):
    """
    Manage GPU memory:
      - check       → just prints memory + process table
      - clear_cache → clears PyTorch cache
      - kill        → kills all GPU processes
    """
    try:
        import pynvml,signal, gc
        pynvml.nvmlInit()
        handle = pynvml.nvmlDeviceGetHandleByIndex(gpu_index)
        info = pynvml.nvmlDeviceGetMemoryInfo(handle)

        free_gb = info.free / 1024**3
        total_gb = info.total / 1024**3

        print(f"\nGPU {gpu_index}: Free {free_gb:.2f} GB / Total {total_gb:.2f} GB")

        # Show processes
        processes = pynvml.nvmlDeviceGetComputeRunningProcesses(handle)
        print("\nActive GPU Processes:")
        print(f"{'PID':<8} {'Process Name':<40} {'Used (GB)':<10}")
        print("-" * 60)
        for p in processes:
            used_gb = p.usedGpuMemory / 1024**3
            proc_name = pynvml.nvmlSystemGetProcessName(p.pid).decode(errors="ignore")
            print(f"{p.pid:<8} {proc_name:<40} {used_gb:.2f}")

        if action == "clear_cache":
            try:
                import torch
                gc.collect()
                gc.collect()
                torch.cuda.empty_cache()
                torch.cuda.reset_peak_memory_stats()
                torch.cuda.synchronize()
                time.sleep(1)
                print("\n🧹 Cleared PyTorch CUDA cache")
            except ImportError:
                print("\n⚠️ PyTorch not installed, cannot clear cache.")

        elif action == "kill":
            for p in processes:
                proc_name = pynvml.nvmlSystemGetProcessName(p.pid).decode(errors="ignore")
                try:
                    os.kill(p.pid, signal.SIGKILL)
                    print(f"❌ Killed {p.pid} ({proc_name})")
                except Exception as e:
                    print(f"⚠️ Could not kill {p.pid}: {e}")
            manage_gpu(action="clear_cache")
        gc.collect()
        gc.collect()
        return free_gb > size_gb
    except: return False

def is_gpu_available(verbose=True):
    import torch
    if not torch.cuda.is_available():
        if verbose:
            print("CUDA not available.")
        return False
    
    try:
        # Try a tiny allocation to check if GPU is free & usable
        torch.empty(1, device="cuda")
        if verbose:
            print(f"CUDA available. Using device: {torch.cuda.get_device_name(0)}")
        return True
    except RuntimeError as e:
        if "CUDA-capable device(s) is/are busy or unavailable" in str(e) or \
           "CUDA error" in str(e):
            if verbose:
                print("CUDA detected but busy/unavailable. Please CPU.")
            return False
        raise  # re-raise if it's some other unexpected error

def get_device(is_vision=False):
    import torch
    device = None
    if not is_vision and os.getenv("USE_CPU_IF_POSSIBLE", None):
        device = "cpu"
    else:
        device = "cuda" if is_gpu_available() else "cpu"

    if device == "cpu":
        torch.cuda.is_available = lambda: False

    return device

def get_best_match(query: str, candidates: list[str]) -> tuple[int, str]:
    """
    Returns the index and text of the most suitable match 
    from candidates for the given query.
    
    Args:
        query (str): Input text to compare.
        candidates (list[str]): List of candidate texts.
    
    Returns:
        (int, str): (best_match_index, best_match_text)
    """
    from sentence_transformers import SentenceTransformer, util
    import torch, gc
    # Load model on CPU
    model = SentenceTransformer('all-mpnet-base-v2', device="cpu")

    # Encode query and candidates
    query_emb = model.encode(query, convert_to_tensor=True, device="cpu")
    candidate_embs = model.encode(candidates, convert_to_tensor=True, device="cpu")

    # Compute cosine similarity
    similarities = util.cos_sim(query_emb, candidate_embs)[0]

    # Get index of best match
    best_idx = similarities.argmax().item()
    best_text = candidates[best_idx]

    # Cleanup to free memory
    del model
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    return best_idx, best_text

def get_neko_additional_flags(config):
    additional_flags = []
    additional_flags.append(f'-v {custom_env.CAPTION_CREATOR_BASE_PATH}:{config.neko_attach_folder}')
    additional_flags.append(config.policy_volume_mount(get_chrome_policies_json_path()))
    return additional_flags

def get_chrome_policies_json_path():
    """
    Returns the path to policies.json, downloading it if it doesn't exist.
    """

    local_path = f"{custom_env.ALL_PROJECT_BASE_PATH}/neko-apps/chrome-remote-debug/policies.json"
    if file_exists(local_path):
        return local_path

    target_path = f"{custom_env.REUSE_PATH}/policies.json"
    if file_exists(target_path):
        remove_file(target_path)
    
    url = "https://raw.githubusercontent.com/jebin2/neko-apps/c4c2019a464b0831d019014b8ed86082fba77975/chrome-remote-debug/policies.json"
    logger_config.info(f"Downloading policies.json from {url}")
    
    try:
        response = requests.get(url)
        if response.status_code == 200:
            with open(target_path, 'wb') as f:
                f.write(response.content)
            logger_config.success(f"Downloaded policies.json to {target_path}")
            return target_path
        else:
            logger_config.error(f"Failed to download policies.json. Status code: {response.status_code}")
            return None
    except Exception as e:
        logger_config.error(f"Error downloading policies.json: {e}")
        return None

def setup_git_repo_get_install_pip(repo_url, target_path, pip_name=None, requirements_file=None, force_install=False):
    is_new = False
    if not dir_exists(target_path):
        import subprocess
        logger_config.info(f"Cloning {repo_url} to {target_path}")
        subprocess.run(
            ["git", "clone", repo_url, target_path],
            check=True
        )
        logger_config.info(f"{repo_url} cloned.")
        is_new = True
    else:
        import subprocess
        logger_config.info(f"Pulling {target_path}")
        try:
            subprocess.run(
                ["git", "pull"],
                cwd=target_path,
                check=True
            )
            logger_config.info(f"{target_path} pulled.")
        except subprocess.CalledProcessError:
            import shutil
            logger_config.info(f"Git pull failed for {target_path}, deleting and re-cloning...")
            shutil.rmtree(target_path)
            subprocess.run(
                ["git", "clone", repo_url, target_path],
                check=True
            )
            logger_config.info(f"{repo_url} re-cloned to {target_path}.")
            is_new = True

    if (is_new or force_install) and not custom_env.IS_DOCKER:
        import subprocess
        if requirements_file:
            req_path = os.path.join(target_path, requirements_file)
            if file_exists(req_path):
                logger_config.info(f"Installing dependencies from {requirements_file}")
                subprocess.run(
                    [
                        "bash",
                        "-ic",
                        f"penv {pip_name} && pip install -r {requirements_file}"
                    ],
                    check=True,
                    cwd=target_path
                )
                logger_config.info(f"Dependencies from {requirements_file} installed.")
        elif pip_name:
            logger_config.info(f"Installing {pip_name} via pip")
            subprocess.run(
                [
                    "bash",
                    "-ic",
                    f"penv {pip_name} && pip install -e .[{pip_name}]"
                ],
                check=True,
                cwd=target_path
            )
            logger_config.info(f"{pip_name} installed.")
    return target_path

_SUBPROCESS_ENV = {**os.environ, 'PYTHONUNBUFFERED': '1', 'CUDA_LAUNCH_BLOCKING': '1', 'USE_CPU_IF_POSSIBLE': 'true'}

def run_subprocess_with_retry(cmd, cwd, repo_url, pip_name, requirements_file=None, timeout=None):
    import subprocess
    try:
        result = subprocess.run(["bash", "-c", cmd], cwd=cwd, text=True, env=_SUBPROCESS_ENV, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise TimeoutError(f"{pip_name} timed out after {timeout}s on: {cmd}")
    if result.returncode != 0:
        logger_config.warning(f"{pip_name} failed with code {result.returncode}. Reinstalling and retrying...")
        setup_git_repo_get_install_pip(
            repo_url=repo_url,
            target_path=cwd,
            pip_name=pip_name,
            requirements_file=requirements_file,
            force_install=True
        )
        try:
            result = subprocess.run(["bash", "-c", cmd], cwd=cwd, text=True, env=_SUBPROCESS_ENV, timeout=timeout)
        except subprocess.TimeoutExpired:
            raise TimeoutError(f"{pip_name} timed out again after {timeout}s on: {cmd}")
        if result.returncode != 0:
            raise ValueError(f"{pip_name} failed again with code {result.returncode}")
    return result

def get_threads():
    return len(psutil.Process().cpu_affinity())

def run_ffmpeg(cmd):
    threads = get_threads()
    cmd = [
        "taskset", "-c", "2,3",
        "nice", "-n", "15",
        "ffmpeg",
        "-nostdin",
        "-threads", str(threads)
    ] + cmd[1:]
    logger_config.debug(f"Running command: {' '.join(cmd)}")
    return subprocess.run(cmd, capture_output=True, text=True, check=True)

