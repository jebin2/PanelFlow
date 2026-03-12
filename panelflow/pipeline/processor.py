import os
import re
import json
import pickle
import shlex
import subprocess
import sys
import zipfile

import json_repair
from PIL import Image, ImageOps

from custom_logger import logger_config
from panelflow import common
from panelflow import config
from jebin_lib import utils, HFTTSClient
from panelflow.pipeline_base import PipelineBase
from panelflow.pipeline import combineImageClip
from panelflow.pipeline import combineVideo
from jebin_lib import merge_audio
from panelflow.pipeline.gemini_config import pre_model_wrapper
from panelflow.pipeline import gemini_history_processor
from panelflow.pipeline import resize_with_aspect
from panelflow.pipeline import remove_sound_effect
from panelflow.pipeline import addMusic
from panelflow.pipeline.create_comic_panel_video import main as main_ComicVideoPipeline, Config as CVP_Config
from jebin_lib import video_optimizer as ffmpeg_optimise


class PanelProcessor(PipelineBase):

    # ------------------------------------------------------------------ step 0

    def _get_panel_files(self):
        files = sorted(utils.list_files(self.panels_dir))
        files = [f for f in files if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp'))]
        if not files and os.path.exists(self.cbz_path):
            logger_config.info("Extracting CBZ")
            utils.create_directory(self.panels_dir)
            with zipfile.ZipFile(self.cbz_path, 'r') as z:
                for member in z.namelist():
                    if member.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')):
                        dest = os.path.join(self.panels_dir, os.path.basename(member))
                        with z.open(member) as src, open(dest, 'wb') as dst:
                            dst.write(src.read())
            files = sorted(utils.list_files(self.panels_dir))
            files = [f for f in files if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp'))]
        return files

    # ------------------------------------------------------------------ step 1

    def get_page_review(self):
        files = self._get_panel_files()
        review_responses = self.load_review_responses()
        if len(files) > 0 and len(review_responses) >= len(files):
            return review_responses

        file_len = len(files)
        review_history = []
        if os.path.exists(self.review_history_path):
            with open(self.review_history_path, 'rb') as f:
                review_history = pickle.load(f)

        review_history = gemini_history_processor.deduplicate_history(review_history)
        geminiWrapper = pre_model_wrapper(
            system_instruction=self.category.review_system_prompt(),
            schema=self.category.recap_schema(),
            history=review_history
        )
        key = geminiWrapper.get_schema().required[0]
        already_processed = len(review_history) // 2

        for i in range(min(already_processed, len(files))):
            if i < len(review_responses):
                continue
            model_index = i * 2 + 1
            if model_index < len(review_history):
                try:
                    impact_value = json_repair.loads(review_history[model_index].parts[0].text).get(key)
                except Exception as e:
                    impact_value = f"Error: {e}"
            else:
                impact_value = "Missing from review_history"
            review_responses.append({"key_moment": files[i], "impact": impact_value})

        try:
            for i in range(already_processed, len(files)):
                model_responses = geminiWrapper.send_message(
                    user_prompt=f"{self.folder_name} :: page {i + 1} of {file_len}",
                    file_path=files[i],
                )
                try:
                    impact_value = json_repair.loads(model_responses[0]).get(key)
                except Exception as e:
                    impact_value = f"Error: {e}"
                review_responses.append({"key_moment": files[i], "impact": impact_value})
                gemini_history_processor.save_history(
                    self.review_history_path, review_history + geminiWrapper.get_history()
                )
        except Exception:
            gemini_history_processor.save_history(
                self.review_history_path, review_history + geminiWrapper.get_history()
            )
            from browser_manager.browser_config import BrowserConfig
            from chat_bot_ui_handler import AIStudioUIChat

            for i in range(len(review_responses), len(files)):
                review_history = gemini_history_processor.load_history(self.review_history_path)
                review_history = gemini_history_processor.deduplicate_history(review_history)
                history_text = gemini_history_processor.history_to_text(review_history)
                cfg = BrowserConfig()
                cfg.user_data_dir = os.getenv("PROFILE_PATH", None)
                cfg.additionl_docker_flag = ' '.join(utils.get_docker_volume_mounts(cfg, config.PARENT_BASE_PATH))
                user_prompt = f"{self.folder_name} :: page {i + 1} of {file_len}"
                result = json_repair.loads(
                    AIStudioUIChat(cfg).quick_chat(
                        user_prompt=f"Previous Pages Narration:: {history_text}\n\nNext Page:: {user_prompt}",
                        system_prompt=self.category.review_system_prompt(),
                        file_path=files[i]
                    )
                )
                impact_value = result[key]
                if impact_value and len(impact_value) > 10:
                    review_responses.append({"key_moment": files[i], "impact": impact_value})
                    gemini_history_processor.append_history(
                        self.review_history_path, user_prompt, json.dumps(result)
                    )

        self.save_review_responses(review_responses)
        return review_responses

    # ------------------------------------------------------------------ step 2

    def get_all_page_recap(self):
        rtd = self.load_recap_title_desc()
        if rtd.get("recap_text"):
            return

        review_history = []
        if os.path.exists(self.review_history_path):
            with open(self.review_history_path, 'rb') as f:
                review_history = pickle.load(f)

        self.get_page_review()

        geminiWrapper = pre_model_wrapper(
            system_instruction=self.category.review_system_prompt(),
            schema=self.category.recap_schema(),
            history=review_history
        )
        key = geminiWrapper.get_schema().required[0]
        model_responses = geminiWrapper.send_message(user_prompt=self.category.get_user_prompt())
        recap_text = common.clean_text(self.category.parse_content(model_responses[0])[key])
        recap_text = self.category.retry(recap_text, geminiWrapper, key)

        with open(self.recap_history_path, 'wb') as f:
            pickle.dump(geminiWrapper.get_history(), f)

        rtd["recap_text"] = recap_text
        self.save_recap_title_desc(rtd)

    # ------------------------------------------------------------------ step 3

    def get_main_title(self):
        rtd = self.load_recap_title_desc()
        if rtd.get("youtube_title"):
            return

        self.get_all_page_recap()

        with open(self.recap_history_path, 'rb') as f:
            recap_history = pickle.load(f)

        geminiWrapper = pre_model_wrapper(
            system_instruction=self.category.title_and_desc_system_prompt(),
            schema=self.category.title_desc_schema(),
            history=recap_history
        )
        model_responses = geminiWrapper.send_message(user_prompt=self.category.title_desc_user_prompt())
        title_desc = self.category.parse_content(model_responses[0])
        rtd["youtube_title"] = re.sub(r'\{.*?\}|\[.*?\]', '', title_desc["youtube_title"])
        rtd["twitter_post"] = re.sub(r'\{.*?\}|\[.*?\]', '', title_desc["twitter_post"])
        self.save_recap_title_desc(rtd)

        review_responses = self.load_review_responses()
        if review_responses:
            review_responses[0]["impact"] = rtd["youtube_title"]
            review_responses[0]["is_sanitise_done"] = False
            self.save_review_responses(review_responses)

    # ------------------------------------------------------------------ step 4

    def get_recap_match(self):
        if os.path.exists(self.recap_match_path):
            return

        self.get_main_title()

        rtd = self.load_recap_title_desc()
        with open(self.recap_history_path, 'rb') as f:
            recap_history = pickle.load(f)

        geminiWrapper = pre_model_wrapper(
            system_instruction=self.category.dialogue_matcher_system_prompt(),
            schema=self.category.dialogue_matcher_schema(),
            history=recap_history
        )
        key = geminiWrapper.get_schema().required[0]
        model_responses = geminiWrapper.send_message(
            user_prompt=self.category.get_recap_match_user_prompt(rtd.get("recap_text", ""))
        )
        self.save_recap_match(self.category.parse_content(model_responses[0])[key])

    # ------------------------------------------------------------------ step 5

    def sanitise_sentences(self):
        self.get_recap_match()

        review_responses = self.load_review_responses()
        rtd = self.load_recap_title_desc()
        if all(r.get("is_sanitise_done") for r in review_responses) and rtd.get("recap_text_sanitised"):
            return review_responses

        for i, res in enumerate(review_responses):
            logger_config.info(f"sanitise_sentences page {i+1}/{len(review_responses)}", overwrite=True)
            if res.get("is_sanitise_done") and "```" not in res.get("impact", ""):
                continue
            for attempt in range(5):
                try:
                    sanitised = remove_sound_effect.remove(res["impact"])
                    if "<unused" in sanitised or not common.is_same_sentence(sanitised, res["impact"], threshold=0.6):
                        raise ValueError("sanitise not correct")
                    break
                except Exception as e:
                    if attempt == 4:
                        raise e
            res["before_sanitise"] = res["impact"]
            res["impact"] = sanitised
            if i == 0:
                res["impact"] = re.sub(r"recap", "", res["impact"], flags=re.IGNORECASE)
            res["is_sanitise_done"] = True
            self.save_review_responses(review_responses)

        if rtd.get("recap_text") and not rtd.get("recap_text_sanitised"):
            for attempt in range(5):
                try:
                    sanitised = remove_sound_effect.remove(rtd["recap_text"])
                    if "<unused" in sanitised or not common.is_same_sentence(sanitised, rtd["recap_text"], threshold=0.6):
                        raise ValueError("sanitise not correct")
                    break
                except Exception as e:
                    if attempt == 4:
                        raise e
            rtd["recap_text"] = sanitised
            rtd["recap_text_sanitised"] = True
            self.save_recap_title_desc(rtd)

        return self.load_review_responses()

    # ------------------------------------------------------------------ step 6a

    def create_sentence_clips(self):
        if utils.file_exists(self.output_no_music_path):
            return

        review_responses = self.sanitise_sentences()

        for i, moment in enumerate(review_responses):
            if not utils.file_exists(moment["key_moment"]):
                raise ValueError(f"page {i+1}: key_moment not found: {moment['key_moment']}")
            logger_config.info(f"create_sentence_clips page {i+1}/{len(review_responses)}", overwrite=True)
            impact = f'{self.category.get_welcome_phrase()} {moment["impact"]}' if i == 0 else moment["impact"]
            if i + 1 == len(review_responses):
                impact = f'{moment["impact"]} {self.category.get_finish_phrase()}'
            impact = impact.strip()

            file_name = utils.generate_random_string_from_input(impact)
            page_dir = os.path.join(self.sentence_media_dir, f"{i+1:04d}")
            utils.create_directory(page_dir)
            video_path = os.path.join(page_dir, f"{i+1:04d}_{file_name}.mp4")

            if utils.file_exists(video_path):
                continue

            if i == 0:
                audio_out = os.path.join(config.TEMP_PATH, f"{utils.generate_random_string()}.wav")
                HFTTSClient().generate_audio_segment(impact.strip(), audio_out)
                _, duration, _, _ = common.get_media_metadata(audio_out)
                resized = os.path.join(config.TEMP_PATH, os.path.basename(moment["key_moment"]))
                resize_with_aspect.scale_keep_ratio(
                    moment["key_moment"], config.IMAGE_SIZE[0], config.IMAGE_SIZE[1], resized, blur_bg=True
                )
                clips = combineImageClip.start([{
                    "img_path": resized,
                    "clip_duration": duration,
                    "clip_start": 0,
                    "donot_animate": True
                }], config.FPS)
                addMusic.process(clips[0], audio_out, output_path=video_path, extend_video=True, trim_video=True)
            else:
                image_path = self._resize_frame(moment["key_moment"], i)
                split_dir = os.path.join(page_dir, f"split_{i+1:04d}")
                self._split_comic_page(image_path, page_dir, split_dir)
                common.delete_matching_videos(page_dir, f"{i+1:04d}_*.mp4")
                cvp_config = CVP_Config()
                cvp_config.comic_title = self.folder_name
                cvp_config.main_file_name = moment["key_moment"]
                cvp_config.comic_image = image_path
                cvp_config.output_video = video_path
                cvp_config.page_specific_dir = page_dir
                cvp_config.split_output_dir = split_dir
                main_ComicVideoPipeline(impact, cvp_config)

        clips = self._get_ordered_sentence_clips()
        if not clips:
            raise ValueError("No sentence clips found for final video assembly")
        combineVideo.start(
            clips,
            audioPath=None,
            fps=config.FPS,
            output_video_path=self.output_no_music_path,
            need_transitions=True
        )

    # ------------------------------------------------------------------ step 6b

    def create_shorts_clips(self):
        if utils.file_exists(self.shorts_output_no_music_path):
            return

        self.get_recap_match()

        files = self._get_panel_files()
        recap_match = self.load_recap_match()
        if not recap_match:
            return

        hf_tts = HFTTSClient()
        changed = False

        for i, match in enumerate(recap_match):
            page_idx = int(match["comic_page_number"]) - 1
            if not (0 <= page_idx < len(files)) or not utils.file_exists(files[page_idx]):
                continue

            audio_path = os.path.join(self.shorts_media_dir, f"audio_{i}.wav")
            if not utils.is_valid_audio(audio_path):
                hf_tts.generate_audio_segment(match["recap_sentence"].strip(), audio_path)

            _, duration, _, _ = common.get_media_metadata(audio_path)
            match["duration"] = duration

            base_name = os.path.basename(files[page_idx])
            resized = os.path.join(self.shorts_media_dir, f"resized_{base_name}.jpg")
            if not utils.file_exists(resized):
                portrait = (config.IMAGE_SIZE[1], config.IMAGE_SIZE[0])
                with Image.open(files[page_idx]) as img:
                    img.resize(portrait, Image.LANCZOS).convert('RGB').save(resized)
            match["img_path"] = resized
            changed = True

        if changed:
            self.save_recap_match(recap_match)

        recap_match = self.load_recap_match()
        frame_params = []
        start = 0.0
        for match in recap_match:
            img_path = match.get("img_path")
            duration = match.get("duration")
            if not img_path or not duration or not utils.file_exists(img_path):
                continue
            frame_params.append({
                "img_path": img_path,
                "clip_duration": duration,
                "clip_start": start,
                "zoom_out_zoom_in_to_full": True,
                "IMAGE_SIZE": (config.IMAGE_SIZE[1], config.IMAGE_SIZE[0]),
            })
            start = round(start + duration, 2)

        if not frame_params:
            raise ValueError("No shorts frame params")

        audio_files = [
            os.path.join(self.shorts_media_dir, f"audio_{i}.wav")
            for i in range(len(recap_match))
            if utils.is_valid_audio(os.path.join(self.shorts_media_dir, f"audio_{i}.wav"))
        ]
        common.combineAudio(audio_files, self.shorts_recap_audio_path, silence=0)

        clips = combineImageClip.start(frame_params, config.FPS)
        combineVideo.start(
            clips,
            audioPath=self.shorts_recap_audio_path,
            fps=config.FPS,
            output_video_path=self.shorts_output_no_music_path,
            need_transitions=False
        )

    # ------------------------------------------------------------------ step 7+8

    def create_final_video(self):
        if utils.file_exists(self.final_video_path):
            return self.final_video_path
        self.create_sentence_clips()
        self._add_bg_music(self.output_no_music_path, self.final_video_path)
        if utils.file_exists(self.final_video_path):
            ffmpeg_optimise.convert_and_compare(self.final_video_path, f"/tmp/{self.folder_name}_final.hevc.mp4", overwrite_original=True)
        return self.final_video_path

    def create_shorts_final_video(self):
        if utils.file_exists(self.shorts_final_video_path):
            return self.shorts_final_video_path
        self.create_shorts_clips()
        self._add_bg_music(self.shorts_output_no_music_path, self.shorts_final_video_path, reuse_musicgen=True)
        if utils.file_exists(self.shorts_final_video_path):
            ffmpeg_optimise.convert_and_compare(self.shorts_final_video_path, f"/tmp/{self.folder_name}_shorts.hevc.mp4", overwrite_original=True)
        return self.shorts_final_video_path

    # ------------------------------------------------------------------ process

    def process(self):
        self.create_final_video()
        self.create_shorts_final_video()
        self.category.create_progress_file()

    # ------------------------------------------------------------------ private helpers

    def _get_ordered_sentence_clips(self):
        all_files = utils.list_files_recursive(self.sentence_media_dir)
        return sorted([f for f in all_files if f.endswith(".mp4")])

    def _resize_add_padding(self, background):
        background = background.resize((config.IMAGE_SIZE[1], config.IMAGE_SIZE[1]))
        add_width = (config.IMAGE_SIZE[0] - config.IMAGE_SIZE[1]) // 2
        background = ImageOps.expand(background, border=(add_width, 0), fill=(0, 0, 0))
        return background

    def _resize_frame(self, img_path, i):
        base_name = os.path.basename(img_path)
        output_path = os.path.join(config.TEMP_PATH, f"{base_name}_resize_frame.jpg")
        if utils.file_exists(output_path):
            return output_path
        with Image.open(img_path) as bg:
            resized = (
                self._resize_add_padding(bg) if i == 0
                else bg.resize((config.IMAGE_SIZE[0], bg.height), Image.LANCZOS)
            )
            resized.convert('RGB').save(output_path)
        return output_path

    def _split_comic_page(self, image_path, output_dir, split_folder):
        completed = os.path.join(split_folder, 'completed')
        if utils.file_exists(completed):
            return
        utils.remove_directory(split_folder)
        utils.create_directory(split_folder)
        config_data = {"input_path": os.path.abspath(image_path), "output_folder": os.path.abspath(split_folder)}
        config_path = os.path.abspath(os.path.join(output_dir, 'split_comic_config.json'))
        with open(config_path, 'w') as f:
            json.dump(config_data, f, indent=4)

        cwd = "/tmp/comic-panel-extractor"
        if not utils.dir_exists(cwd):
            utils.setup_git_repo_get_install_pip(
                repo_url="https://github.com/jebin2/comic-panel-extractor.git",
                target_path=cwd,
                pip_name="comic-panel-extractor",
            )
        python_path = os.path.expanduser("~/.pyenv/versions/comic-panel-extractor_env/bin/comic-panel-extractor")
        cmd = f"{python_path} --config {shlex.quote(config_path)}"
        result = subprocess.run(["bash", "-c", cmd], cwd=cwd, text=True, env=config.SUBPROCESS_ENV)
        if result.returncode != 0:
            raise ValueError(f"comic-panel-extractor failed with code {result.returncode}")

        panels = [f for f in utils.list_files(split_folder) if "_panel_" in os.path.basename(f)]
        if panels:
            with open(completed, 'w') as f:
                f.write("Done")
        else:
            raise ValueError("comic-panel-extractor produced no panels.")

    def _add_bg_music(self, input_path, output_path, reuse_musicgen=False):
        from moviepy.editor import VideoFileClip

        abs_input_path = os.path.abspath(input_path)
        abs_output_path = os.path.abspath(output_path)
        abs_musicgen_path = os.path.abspath(self.musicgen_path)

        if not reuse_musicgen and not utils.file_exists(self.musicgen_path):
            recap_text = self.load_recap_title_desc().get("recap_text", "")
            subprocess.run(
                [sys.executable, "-m", "music_creator.core", recap_text, abs_musicgen_path, os.path.abspath(config.CREATE_MUSIC_SYSTEM_PROMPT)],
                check=True,
                cwd=config.BASE_PATH,
                env={**os.environ, 'PYTHONUNBUFFERED': '1', 'CUDA_LAUNCH_BLOCKING': '1', 'USE_CPU_IF_POSSIBLE': 'true'}
            )
            common.manage_gpu(action="clear_cache")

        video = VideoFileClip(abs_input_path)
        extracted_audio_path = abs_output_path + "_extracted.wav"
        video.audio.write_audiofile(extracted_audio_path)
        video.close()

        merged_audio_path = abs_output_path + "_merged.wav"
        merge_audio.process(extracted_audio_path, abs_musicgen_path, merged_audio_path)

        subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", abs_input_path,
                "-i", merged_audio_path,
                "-c:v", "copy", "-c:a", "aac",
                "-map", "0:v:0", "-map", "1:a:0",
                "-shortest",
                abs_output_path
            ],
            check=True
        )

        os.remove(extracted_audio_path)
        os.remove(merged_audio_path)
