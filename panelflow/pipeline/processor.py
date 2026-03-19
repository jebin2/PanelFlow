import os
import re
import json
import shlex
import subprocess
import sys
import zipfile

import json_repair
from PIL import Image, ImageOps

from custom_logger import logger_config
from panelflow import common
from panelflow import config
from jebin_lib import utils, HFTTSClient, normalize_loudness
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
        file_len = len(files)

        review_responses_json = self.load_review_responses_json_path()
        review_history_pkl = self.load_review_history_pkl()

        if file_len > 0 and len(review_responses_json) >= file_len:
            return review_responses_json, review_history_pkl

        geminiWrapper = pre_model_wrapper(
            system_instruction=self.category.review_system_prompt(),
            schema=self.category.recap_schema(),
            history=review_history_pkl
        )
        key = geminiWrapper.get_schema().required[0]
        already_processed = len(review_history_pkl) // 2

        for i in range(min(already_processed, len(files))):
            if i < len(review_responses_json):
                continue
            model_index = i * 2 + 1
            if model_index < len(review_history_pkl):
                try:
                    impact_value = json_repair.loads(review_history_pkl[model_index].parts[0].text).get(key)
                except Exception as e:
                    impact_value = f"Error: {e}"
            else:
                impact_value = "Missing from review_history"
            review_responses_json.append({"key_moment": files[i], "impact": impact_value})

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
                review_responses_json.append({"key_moment": files[i], "impact": impact_value})
                gemini_history_processor.save_history(
                    self.review_history_pkl_path, review_history_pkl + geminiWrapper.get_history()
                )
                self.save_review_responses(review_responses_json)
        except Exception:
            gemini_history_processor.save_history(
                self.review_history_pkl_path, review_history_pkl + geminiWrapper.get_history()
            )
            from browser_manager.browser_config import BrowserConfig
            from chat_bot_ui_handler import AIStudioUIChat

            for i in range(len(review_responses_json), len(files)):
                history_text = gemini_history_processor.history_to_text(self.load_review_history_pkl())
                cfg = BrowserConfig()
                cfg.additionl_docker_flag = ' '.join(utils.get_docker_volume_mounts(cfg, config.BASE_PATH))
                user_prompt = f"{self.folder_name} :: page {i + 1} of {file_len}"
                response = AIStudioUIChat(cfg).quick_chat(
                    user_prompt=f"Previous Pages Narration:: {history_text}\n\nNext Page:: {user_prompt}",
                    system_prompt=self.category.review_system_prompt(),
                    file_path=files[i]
                )
                if not response:
                    raise ValueError(f"AIStudioUIChat returned empty response for page {i + 1}")
                result = json_repair.loads(response)
                impact_value = result[key]
                if impact_value and len(impact_value) > 10:
                    review_responses_json.append({"key_moment": files[i], "impact": impact_value})
                    gemini_history_processor.append_history(
                        self.review_history_pkl_path, user_prompt, json.dumps(result)
                    )
                    self.save_review_responses(review_responses_json)

        self.save_review_responses(review_responses_json)
        return self.load_review_responses_json_path(), self.load_review_history_pkl()

    # ------------------------------------------------------------------ step 2

    def get_all_page_recap(self):
        rtd = self.load_recap_title_desc()
        if rtd.get("recap_text"):
            return rtd

        review_responses_json, review_history_pkl = self.get_page_review()

        geminiWrapper = pre_model_wrapper(
            system_instruction=config.ALL_PAGE_RECAP_PROMPT,
            schema=self.category.recap_schema(),
            history=review_history_pkl
        )
        key = geminiWrapper.get_schema().required[0]
        try:
            model_responses = geminiWrapper.send_message(user_prompt=self.category.get_user_prompt())
            recap_text = utils.clean_text(self.category.parse_content(model_responses[0])[key])
            recap_text = self.category.retry(recap_text, geminiWrapper, key)
        except Exception:
            from browser_manager.browser_config import BrowserConfig
            from chat_bot_ui_handler import AIStudioUIChat

            history_text = gemini_history_processor.history_to_text(review_history_pkl)
            cfg = BrowserConfig()
            cfg.additionl_docker_flag = ' '.join(utils.get_docker_volume_mounts(cfg, config.BASE_PATH))
            response = AIStudioUIChat(cfg).quick_chat(
                user_prompt=f"Previous Pages Narration:: {history_text}\n\nGenerate Recap:: {self.category.get_user_prompt()}",
                system_prompt=config.ALL_PAGE_RECAP_PROMPT
            )
            if not response:
                raise ValueError("AIStudioUIChat returned empty response for recap")
            result = json_repair.loads(response)
            if not isinstance(result, dict) or key not in result:
                raise ValueError(f"AIStudioUIChat returned unexpected response: {response!r}")
            recap_text = utils.clean_text(result[key])

        self.save_recap_history_pkl(geminiWrapper.get_history())

        rtd["recap_text"] = recap_text
        self.save_recap_title_desc(rtd)
        return rtd

    # ------------------------------------------------------------------ step 3

    def get_main_title(self):
        rtd = self.get_all_page_recap()
        if rtd.get("youtube_title"):
            return rtd

        recap_history = self.load_recap_history_pkl()

        geminiWrapper = pre_model_wrapper(
            system_instruction=self.category.title_and_desc_system_prompt(),
            schema=self.category.title_desc_schema(),
            history=recap_history
        )
        try:
            model_responses = geminiWrapper.send_message(user_prompt=self.category.title_desc_user_prompt())
            title_desc = self.category.parse_content(model_responses[0])
        except Exception:
            from browser_manager.browser_config import BrowserConfig
            from chat_bot_ui_handler import AIStudioUIChat

            recap_history = gemini_history_processor.load_history(self.recap_history_pkl_path)
            recap_history = gemini_history_processor.deduplicate_history(recap_history)
            history_text = gemini_history_processor.history_to_text(recap_history)
            cfg = BrowserConfig()
            cfg.additionl_docker_flag = ' '.join(utils.get_docker_volume_mounts(cfg, config.BASE_PATH))
            response = AIStudioUIChat(cfg).quick_chat(
                user_prompt=f"Previous Recap:: {history_text}\n\nGenerate Title & Description:: {self.category.title_desc_user_prompt()}",
                system_prompt=self.category.title_and_desc_system_prompt()
            )
            if not response:
                raise ValueError("AIStudioUIChat returned empty response for title/desc")
            title_desc = json_repair.loads(response)
        rtd["youtube_title"] = re.sub(r'\{.*?\}|\[.*?\]', '', title_desc["youtube_title"])
        rtd["twitter_post"] = re.sub(r'\{.*?\}|\[.*?\]', '', title_desc["twitter_post"])
        self.save_recap_title_desc(rtd)

        review_responses_json = self.load_review_responses_json_path()
        if review_responses_json:
            review_responses_json[0]["impact"] = rtd["youtube_title"]
            review_responses_json[0]["is_sanitise_done"] = False
            self.save_review_responses(review_responses_json)
        else:
            raise ValueError("review_responses_json is empty, cannot generate recap match")

        return rtd

    # ------------------------------------------------------------------ step 4

    def get_recap_match(self):
        recap_match = self.load_recap_match()
        if recap_match:
            return recap_match

        rtd = self.get_main_title()
        if not rtd.get("recap_text"):
            raise ValueError("recap_text is empty, cannot generate recap match")
        recap_history = self.load_recap_history_pkl()

        geminiWrapper = pre_model_wrapper(
            system_instruction=self.category.dialogue_matcher_system_prompt(),
            schema=self.category.dialogue_matcher_schema(),
            history=recap_history
        )
        key = geminiWrapper.get_schema().required[0]
        user_prompt = self.category.get_recap_match_user_prompt(rtd.get("recap_text"))
        try:
            model_responses = geminiWrapper.send_message(user_prompt=user_prompt)
            result = self.category.parse_content(model_responses[0])[key]
        except Exception:
            from browser_manager.browser_config import BrowserConfig
            from chat_bot_ui_handler import AIStudioUIChat

            recap_history = gemini_history_processor.load_history(self.recap_history_pkl_path)
            recap_history = gemini_history_processor.deduplicate_history(recap_history)
            history_text = gemini_history_processor.history_to_text(recap_history)
            cfg = BrowserConfig()
            cfg.additionl_docker_flag = ' '.join(utils.get_docker_volume_mounts(cfg, config.BASE_PATH))
            response = AIStudioUIChat(cfg).quick_chat(
                user_prompt=f"Previous Recap:: {history_text}\n\nMatch Sentences to Pages:: {user_prompt}",
                system_prompt=self.category.dialogue_matcher_system_prompt()
            )
            if not response:
                raise ValueError("AIStudioUIChat returned empty response for recap match")
            result = json_repair.loads(response)[key]
        if not result:
            raise ValueError("get_recap_match returned empty result")

        # Normalise consecutive entries with the same comic_page_number
        normalised = []
        for entry in result:
            if normalised and normalised[-1]["comic_page_number"] == entry["comic_page_number"]:
                normalised[-1]["recap_sentence"] += " " + entry["recap_sentence"]
            else:
                normalised.append(dict(entry))
        result = normalised

        self.save_recap_match(result)

        return result

    # ------------------------------------------------------------------ step 5

    def sanitise_sentences(self):
        review_responses_json = self.load_review_responses_json_path()
        rtd = self.load_recap_title_desc()
        if all(r.get("is_sanitise_done") for r in review_responses_json) and rtd.get("recap_text_sanitised"):
            return review_responses_json

        for i, res in enumerate(review_responses_json):
            logger_config.info(f"sanitise_sentences page {i+1}/{len(review_responses_json)}", overwrite=True)
            if res.get("is_sanitise_done") and "```" not in res.get("impact", ""):
                continue
            for attempt in range(5):
                try:
                    sanitised = remove_sound_effect.remove(res["impact"])
                    if "<unused" in sanitised or not utils.is_same_sentence(sanitised, res["impact"], threshold=0.6):
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
            self.save_review_responses(review_responses_json)

        if rtd.get("recap_text") and not rtd.get("recap_text_sanitised"):
            for attempt in range(5):
                try:
                    sanitised = remove_sound_effect.remove(rtd["recap_text"])
                    if "<unused" in sanitised or not utils.is_same_sentence(sanitised, rtd["recap_text"], threshold=0.6):
                        raise ValueError("sanitise not correct")
                    break
                except Exception as e:
                    if attempt == 4:
                        raise e
            rtd["recap_text"] = sanitised
            rtd["recap_text_sanitised"] = True
            self.save_recap_title_desc(rtd)

        return self.load_review_responses_json_path()

    # ------------------------------------------------------------------ step 6a

    def create_sentence_clips(self):
        if utils.file_exists(self.output_no_music_path):
            return self.output_no_music_path

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
                cvp_config.category_obj = self.category
                main_ComicVideoPipeline(impact, cvp_config)
            if self.sync_callback:
                self.sync_callback(sub=os.path.relpath(page_dir, self.folder))

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

        return self.output_no_music_path

    # ------------------------------------------------------------------ step 6b

    def create_shorts_clips(self):
        if utils.file_exists(self.shorts_output_no_music_path):
            return self.shorts_output_no_music_path

        files = self._get_panel_files()
        recap_match = self.get_recap_match()

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
                resize_with_aspect.scale_keep_ratio(
                    files[page_idx], config.IMAGE_SIZE[1], config.IMAGE_SIZE[0], resized, blur_bg=False
                )
            match["img_path"] = resized
            changed = True

        if changed:
            self.save_recap_match(recap_match)

        recap_match = self.get_recap_match()
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

        return self.shorts_output_no_music_path

    # ------------------------------------------------------------------ step 7+8

    def create_final_video(self):
        if utils.file_exists(self.final_video_path):
            return self.final_video_path

        self._add_bg_music(self.create_sentence_clips(), self.final_video_path)
        if utils.file_exists(self.final_video_path):
            normalize_loudness(self.final_video_path)
            ffmpeg_optimise.convert_and_compare(self.final_video_path, f"/tmp/{self.folder_name}_final.hevc.mp4", overwrite_original=True)
        return self.final_video_path

    def create_shorts_final_video(self):
        if utils.file_exists(self.shorts_final_video_path):
            return self.shorts_final_video_path

        self._add_bg_music(self.create_shorts_clips(), self.shorts_final_video_path, reuse_musicgen=True)
        if utils.file_exists(self.shorts_final_video_path):
            normalize_loudness(self.shorts_final_video_path)
            ffmpeg_optimise.convert_and_compare(self.shorts_final_video_path, f"/tmp/{self.folder_name}_shorts.hevc.mp4", overwrite_original=True)
        return self.shorts_final_video_path

    # ------------------------------------------------------------------ process

    def _create_thumbnail(self):
        if utils.file_exists(self.thumbnail_path):
            return self.thumbnail_path

        files = self._get_panel_files()

        target_w, target_h = config.IMAGE_SIZE  # 1920x1080
        with Image.open(files[0]) as img:
            img = img.convert("RGB")
            iw, ih = img.size
            # Scale to fill the full width, then crop from the top
            scale = target_w / iw
            resized = img.resize((target_w, int(ih * scale)), Image.LANCZOS)
            cropped = resized.crop((0, 0, target_w, target_h))
            cropped.save(self.thumbnail_path, "JPEG", quality=95)

        return self.thumbnail_path

    def process(self):
        if self.is_processed():
            logger_config.info(f"Already processed: {self.folder}")
            return

        self.create_final_video()
        self.create_shorts_final_video()
        self._create_thumbnail()
        self.category.create_progress_file()
        if self.sync_callback:
            self.sync_callback()

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
            if i == 0:
                resized = self._resize_add_padding(bg)
            else:
                scale = config.IMAGE_SIZE[0] / bg.width
                new_h = int(bg.height * scale)
                resized = bg.resize((config.IMAGE_SIZE[0], new_h), Image.LANCZOS)

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
        from moviepy import VideoFileClip

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
            utils.manage_gpu(action="clear_cache")

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
