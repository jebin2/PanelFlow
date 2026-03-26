from jebin_lib import load_env, utils, ensure_hf_mounted, sync_to_hf
load_env()

import gc
import sys
import os
import traceback
from custom_logger import logger_config

from panelflow import config
from panelflow.pipeline.processor import PanelProcessor


class ContentCreator:

    def __init__(self):
        ensure_hf_mounted(config.HF_BUCKET_ID, config.HF_TOKEN, config.HF_MOUNT_PATH)

    def run(self):
        if not os.path.isdir(config.CONTENT_TO_BE_PROCESSED):
            logger_config.warning(f"Input folder not found: {config.CONTENT_TO_BE_PROCESSED}")
            return

        comic_folders = []
        for category in config.CATEGORY:
            cat_path = os.path.join(config.CONTENT_TO_BE_PROCESSED, category)
            if not os.path.isdir(cat_path):
                continue
            for entry in sorted(os.scandir(cat_path), key=lambda e: e.name):
                if entry.is_dir():
                    comic_folders.append((utils.to_rel(entry.path, config.CONTENT_TO_BE_PROCESSED), category))
                elif entry.name.lower().endswith('.cbz'):
                    folder_name = os.path.splitext(entry.name)[0]
                    folder_path = os.path.join(cat_path, folder_name)
                    utils.create_directory(folder_path)
                    dest = os.path.join(folder_path, entry.name)
                    if not os.path.exists(dest):
                        os.rename(entry.path, dest)
                    comic_folders.append((utils.to_rel(folder_path, config.CONTENT_TO_BE_PROCESSED), category))

        for idx, (folder, category) in enumerate(comic_folders):
            instance = None
            try:
                logger_config.info(f"PanelProcessor {idx+1}/{len(comic_folders)}: {folder}")
                instance = PanelProcessor(folder=folder, category=category)
                if instance.allowed_create():
                    sync_to_hf(config.CONTENT_TO_BE_PROCESSED, config.HF_MOUNT_PATH, subpath=folder)
                    instance.run()
            except Exception as e:
                logger_config.error(f"Failed: {folder}: {e}\n{traceback.format_exc()}")
            finally:
                gc.collect()

def main():
    os.chdir(config.BASE_PATH)

    one_pass = '--onepass' in sys.argv

    for entry in os.scandir(config.BASE_PATH):
        if entry.name.startswith(('thread_id_', 'temp', 'chat_bot_ui_handler_logs')) and entry.is_dir():
            utils.remove_directory(entry.path)

    os.makedirs(config.TEMP_PATH, exist_ok=True)

    while True:
        creator = None
        try:
            creator = ContentCreator()
            creator.run()
        except Exception as e:
            logger_config.error(f"Failed to process: {e}")
            logger_config.error(traceback.format_exc())
            del e
        finally:
            del creator
            gc.collect()

        if one_pass:
            break
        logger_config.info("Sleeping for 60 seconds", seconds=60)

if __name__ == '__main__':
    main()
