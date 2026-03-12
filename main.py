from jebin_lib import load_env
load_env()

import gc
import sys
import os
import traceback

from custom_logger import logger_config
from panelflow import config as custom_env
from panelflow.pipeline.processor import PanelProcessor
from jebin_lib import utils, HFDatasetClient

class ContentCreator:

    def __init__(self, local_only=True, remote_only=False):
        self.hf_client = HFDatasetClient(repo_id=custom_env.PUBLISH_HF_REPO_ID) if custom_env.PUBLISH_HF_REPO_ID else None
        self.sync_states = {}
        self.local_only = local_only
        self.remote_only = remote_only
        self.setup()

    def _snapshot_comic_folders(self, cat_path):
        if not os.path.isdir(cat_path):
            return
        for entry in os.scandir(cat_path):
            if entry.is_dir():
                self.sync_states[entry.path] = self._get_dir_fingerprint(entry.path)

    def setup(self):
        if self.hf_client:
            for category in custom_env.CATEGORY:
                local_cat_path = os.path.join(custom_env.PANELS_TO_BE_PROCESSED, category)
                if self.local_only:
                    self.hf_client.upload_folder(local_cat_path, category, delete_patterns=["*"])
                elif self.remote_only:
                    if os.path.isdir(local_cat_path):
                        import shutil
                        shutil.rmtree(local_cat_path)
                    self.hf_client.download_folder(category, custom_env.PANELS_TO_BE_PROCESSED)
                else:
                    self.hf_client.download_folder(category, custom_env.PANELS_TO_BE_PROCESSED)
                self._snapshot_comic_folders(local_cat_path)

    def _get_dir_fingerprint(self, path):
        if not os.path.exists(path):
            return frozenset()
        result = set()
        for root, _, files in os.walk(path):
            for f in files:
                fpath = os.path.join(root, f)
                try:
                    st = os.stat(fpath)
                    result.add((os.path.relpath(fpath, path), st.st_mtime_ns, st.st_size))
                except OSError:
                    continue
        return frozenset(result)

    def sync(self, local_path, remote_path):
        if self.hf_client:
            current_fp = self._get_dir_fingerprint(local_path)
            if self.sync_states.get(local_path) == current_fp:
                return
            self.hf_client.upload_folder(local_path, remote_path)
            self.sync_states[local_path] = self._get_dir_fingerprint(local_path)

    def force_sync(self, local_path, remote_path):
        if self.hf_client:
            self.hf_client.upload_folder(local_path, remote_path, delete_patterns=["*"])
            self.sync_states[local_path] = self._get_dir_fingerprint(local_path)

    def run(self):
        if not os.path.isdir(custom_env.PANELS_TO_BE_PROCESSED):
            logger_config.warning(f"Input folder not found: {custom_env.PANELS_TO_BE_PROCESSED}")
            return

        comic_folders = []
        for category in custom_env.CATEGORY:
            cat_path = os.path.join(custom_env.PANELS_TO_BE_PROCESSED, category)
            if not os.path.isdir(cat_path):
                continue
            for entry in sorted(os.scandir(cat_path), key=lambda e: e.name):
                if entry.is_dir():
                    comic_folders.append((os.path.relpath(entry.path, custom_env.BASE_PATH), category))
                elif entry.name.lower().endswith('.cbz'):
                    folder_name = os.path.splitext(entry.name)[0]
                    folder_path = os.path.join(cat_path, folder_name)
                    utils.create_directory(folder_path)
                    dest = os.path.join(folder_path, entry.name)
                    if not os.path.exists(dest):
                        os.rename(entry.path, dest)
                    comic_folders.append((os.path.relpath(folder_path, custom_env.BASE_PATH), category))

        for idx, (folder, category) in enumerate(comic_folders):
            try:
                Pipeline = PanelProcessor
                logger_config.info(f"{Pipeline.__name__} {idx+1}/{len(comic_folders)}: {folder}")

                remote_path = os.path.relpath(folder, custom_env.PANELS_TO_BE_PROCESSED)
                kwargs = dict(
                    folder=folder,
                    category=category,
                    sync_callback=lambda lp=folder, rp=remote_path: self.sync(lp, rp)
                )

                instance = Pipeline(**kwargs)
                if instance.allowed_create():
                    instance.process()

            except Exception as e:
                logger_config.error(f"Failed: {folder}: {e}\n{traceback.format_exc()}")
            finally:
                gc.collect()


def main():
    os.chdir(custom_env.BASE_PATH)

    local_only = '--localonly' in sys.argv
    remote_only = '--remoteonly' in sys.argv
    one_pass = '--onepass' in sys.argv

    while True:
        creator = None
        try:
            creator = ContentCreator(
                local_only=local_only,
                remote_only=remote_only
            )
            creator.run()
        except Exception as e:
            logger_config.error(f"ContentCreator failed: {e}\n{traceback.format_exc()}")
        finally:
            del creator
            gc.collect()

        if one_pass:
            break
        logger_config.info("Sleeping for 60 seconds", seconds=60)


if __name__ == '__main__':
    main()
