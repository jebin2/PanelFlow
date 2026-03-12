import gc
import os
import traceback
import subprocess
import sys
import zipfile

from custom_logger import logger_config
from panelflow import common
from panelflow import config as custom_env
from jebin_lib import utils
from panelflow.pipeline_base import PipelineBase
from panelflow.pipeline import combineImageClip
from panelflow.pipeline import combineVideo
from panelflow.pipeline import merge_audio

class PanelProcessor(PipelineBase):

    def process(self):
        try:
            logger_config.info(f"Processing {self.folder_name}")

            # ── Step 0: extract CBZ → Panels/ if not yet done ───────────────
            files = sorted(utils.list_files(self.panels_dir))
            files = [f for f in files if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp'))]
            if not files and os.path.exists(self.cbz_path):
                logger_config.info("Step 0: extract CBZ")
                utils.create_directory(self.panels_dir)
                with zipfile.ZipFile(self.cbz_path, 'r') as z:
                    for member in z.namelist():
                        if member.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')):
                            dest = os.path.join(self.panels_dir, os.path.basename(member))
                            with z.open(member) as src, open(dest, 'wb') as dst:
                                dst.write(src.read())
                files = sorted(utils.list_files(self.panels_dir))
                files = [f for f in files if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp'))]

            # ── Steps 1-5: shared AI state ──────────────────────────────────
            review_responses = self.load_review_responses()
            all_pages_present = len(files) > 0 and len(review_responses) >= len(files)

            if not all_pages_present:
                logger_config.info("Step 1: generate_review_responses")
                review_responses = self.category.get_page_review(review_responses)

            if not self.load_recap_title_desc().get("recap_text"):
                logger_config.info("Step 2: generate_recap")
                self.category.get_all_page_recap(review_responses)

            if not self.load_recap_title_desc().get("youtube_title"):
                logger_config.info("Step 3: generate_title_desc")
                self.category.get_main_title()

            if not os.path.exists(self.recap_match_path):
                logger_config.info("Step 4: match_pages")
                self.category.get_recap_match()

            recap_title_desc = self.load_recap_title_desc()
            if not all(r.get("is_sanitise_done") for r in review_responses) or not recap_title_desc.get("recap_text_sanitised"):
                logger_config.info("Step 5: sanitise_sentences")
                self.category.sanitise_sentences(review_responses)

            # ── Step 6a: landscape sentence clips ───────────────────────────
            if not utils.file_exists(self.final_video_path):
                logger_config.info("Step 6a: create_sentence_clips (review)")
                self.category.create_sentence_clips(review_responses)

            # ── Step 6b: portrait shorts clips ──────────────────────────────
            if not utils.file_exists(self.shorts_final_video_path):
                logger_config.info("Step 6b: create_shorts_clips")
                self.category.create_shorts_clips()

            # ── Step 7a: combine review clips ───────────────────────────────
            if not utils.file_exists(self.final_video_path):
                logger_config.info("Step 7a: create_final_video (review)")
                self._create_final_video()

            # ── Step 7b: combine shorts clips ───────────────────────────────
            if not utils.file_exists(self.shorts_final_video_path):
                logger_config.info("Step 7b: create_shorts_final_video")
                self._create_shorts_final_video()

            # ── Step 8a: add music to review ────────────────────────────────
            if not utils.file_exists(self.final_video_path):
                logger_config.info("Step 8a: add_bg_music (review)")
                self._add_bg_music(self.output_no_music_path, self.final_video_path)

            # ── Step 8b: add music to shorts (reuse musicgen.wav) ───────────
            if not utils.file_exists(self.shorts_final_video_path):
                logger_config.info("Step 8b: add_bg_music (shorts)")
                self._add_bg_music(
                    self.shorts_output_no_music_path,
                    self.shorts_final_video_path,
                    reuse_musicgen=True
                )

            # ── Step 9: write progress.json ─────────────────────────────────
            if not utils.file_exists(self.progress_path):
                logger_config.info("Step 9: create_progress_file")
                self.category.create_progress_file()

            logger_config.success(f"Done: {self.folder_name}")

        except Exception as e:
            logger_config.error(f"VideoProcessor failed for {self.folder_name}: {e}\n{traceback.format_exc()}")
        finally:
            gc.collect()

    # ------------------------------------------------------------------ helpers

    def _get_ordered_sentence_clips(self):
        """Return sentence_media/NNNN/NNNN_*.mp4 files in numeric order."""
        all_files = utils.list_files_recursive(self.sentence_media_dir)
        clips = sorted([f for f in all_files if f.endswith(".mp4")])
        return clips

    def _create_final_video(self):
        clips = self._get_ordered_sentence_clips()
        if not clips:
            raise ValueError("No sentence clips found for final video assembly")
        combineVideo.start(
            clips,
            audioPath=None,  # audio already embedded per clip
            fps=custom_env.FPS,
            output_video_path=self.output_no_music_path,
            need_transitions=True
        )

    def _create_shorts_final_video(self):
        recap_match = self.load_recap_match()
        if not recap_match:
            return

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
                "IMAGE_SIZE": (custom_env.IMAGE_SIZE[1], custom_env.IMAGE_SIZE[0]),  # 1080×1920
            })
            start = round(start + duration, 2)

        if not frame_params:
            raise ValueError("No shorts frame params")

        # Combine per-sentence audio into one track
        audio_files = [
            os.path.join(self.shorts_media_dir, f"audio_{i}.wav")
            for i in range(len(recap_match))
            if utils.is_valid_audio(os.path.join(self.shorts_media_dir, f"audio_{i}.wav"))
        ]
        common.combineAudio(audio_files, self.shorts_recap_audio_path, silence=0)

        clips = combineImageClip.start(frame_params, custom_env.FPS)
        combineVideo.start(
            clips,
            audioPath=self.shorts_recap_audio_path,
            fps=custom_env.FPS,
            output_video_path=self.shorts_output_no_music_path,
            need_transitions=False
        )

    def _add_bg_music(self, input_path, output_path, reuse_musicgen=False):
        from moviepy.editor import VideoFileClip

        abs_input_path = os.path.abspath(input_path)
        abs_output_path = os.path.abspath(output_path)
        abs_musicgen_path = os.path.abspath(self.musicgen_path)

        # Step 1: generate musicgen.wav if needed
        if not reuse_musicgen and not utils.file_exists(self.musicgen_path):
            recap_text = self.load_recap_title_desc().get("recap_text", "")
            subprocess.run(
                [sys.executable, "-m", "panelflow.pipeline.music_creator", recap_text, abs_musicgen_path],
                check=True,
                cwd=custom_env.BASE_PATH,
                env={**os.environ, 'PYTHONUNBUFFERED': '1', 'CUDA_LAUNCH_BLOCKING': '1', 'USE_CPU_IF_POSSIBLE': 'true'}
            )
            common.manage_gpu(action="clear_cache")

        # Step 2: extract video audio to a temp WAV
        video = VideoFileClip(abs_input_path)
        extracted_audio_path = abs_output_path + "_extracted.wav"
        video.audio.write_audiofile(extracted_audio_path)
        video.close()

        # Step 3: merge extracted audio + musicgen → merged WAV
        merged_audio_path = abs_output_path + "_merged.wav"
        merge_audio.process(extracted_audio_path, abs_musicgen_path, merged_audio_path)

        # Step 4: attach merged audio to video via ffmpeg
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
