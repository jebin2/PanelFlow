from jebin_lib import load_env, utils
load_env()

import gc
import sys
import os
import shutil
import traceback

from jebin_lib import HFBucketClient
from custom_logger import logger_config
from panelflow import config
from panelflow.pipeline.processor import PanelProcessor

class ContentCreator:

    def __init__(self, local_only=True, remote_only=False):
        self.hf_client = HFBucketClient(bucket_id=config.HF_BUCKET_ID) if config.HF_BUCKET_ID else None
        self.local_only = local_only
        self.remote_only = remote_only
        self.setup()

    def setup(self):
        if self.hf_client:
            for category in config.CATEGORY:
                local_cat_path = os.path.join(config.PANELS_TO_BE_PROCESSED, category)
                if self.local_only:
                    self.hf_client.upload_folder(local_cat_path, category, delete=True)
                elif self.remote_only:
                    if os.path.isdir(local_cat_path):
                        shutil.rmtree(local_cat_path)
                    self.hf_client.download_folder(category, local_cat_path)
                else:
                    self.hf_client.download_folder(category, local_cat_path)
                    self.hf_client.upload_folder(local_cat_path, category)

    def sync(self, local_path, remote_path):
        if self.hf_client:
            self.hf_client.upload_folder(local_path, remote_path)


    def run(self):
        if not os.path.isdir(config.PANELS_TO_BE_PROCESSED):
            logger_config.warning(f"Input folder not found: {config.PANELS_TO_BE_PROCESSED}")
            return

        comic_folders = []
        for category in config.CATEGORY:
            cat_path = os.path.join(config.PANELS_TO_BE_PROCESSED, category)
            if not os.path.isdir(cat_path):
                continue
            for entry in sorted(os.scandir(cat_path), key=lambda e: e.name):
                if entry.is_dir():
                    comic_folders.append((utils.to_rel(entry.path, config.BASE_PATH), category))
                elif entry.name.lower().endswith('.cbz'):
                    folder_name = os.path.splitext(entry.name)[0]
                    folder_path = os.path.join(cat_path, folder_name)
                    utils.create_directory(folder_path)
                    dest = os.path.join(folder_path, entry.name)
                    if not os.path.exists(dest):
                        os.rename(entry.path, dest)
                    comic_folders.append((utils.to_rel(folder_path, config.BASE_PATH), category))

        for idx, (folder, category) in enumerate(comic_folders):
            try:
                Pipeline = PanelProcessor
                logger_config.info(f"{Pipeline.__name__} {idx+1}/{len(comic_folders)}: {folder}")

                remote_path = utils.to_rel(folder, config.PANELS_TO_BE_PROCESSED)
                kwargs = dict(
                    folder=folder,
                    category=category,
                    sync_callback=lambda lp=folder, rp=remote_path, sub=None: self.sync(
                        os.path.join(lp, sub) if sub else lp,
                        os.path.join(rp, sub) if sub else rp
                    )
                )

                instance = Pipeline(**kwargs)
                if instance.allowed_create():
                    instance.process()

            except Exception as e:
                logger_config.error(f"Failed: {folder}: {e}\n{traceback.format_exc()}")
            finally:
                gc.collect()

def main():
    os.chdir(config.BASE_PATH)

    local_only = '--localonly' in sys.argv
    remote_only = '--remoteonly' in sys.argv
    one_pass = '--onepass' in sys.argv

    # remove directory start with thread_id_*
    for entry in os.scandir(config.BASE_PATH):
        if entry.name.startswith(('thread_id_', 'temp', 'chat_bot_ui_handler_logs')) and entry.is_dir():
            utils.remove_directory(entry.path)

    while True:
        creator = None
        try:
            creator = ContentCreator(
                local_only=local_only,
                remote_only=remote_only
            )
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