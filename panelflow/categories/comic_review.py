import json
import os
import re
import pickle
import traceback
import shlex
import subprocess

from google import genai
from pydantic import BaseModel
from custom_logger import logger_config
from PIL import Image, ImageOps
import json_repair

from .base import CategoryBase
from panelflow import config
from panelflow import common
from panelflow.pipeline.gemini_config import pre_model_wrapper
from panelflow.pipeline import gemini_history_processor
from panelflow.pipeline import resize_with_aspect
from panelflow.pipeline import remove_sound_effect
from panelflow.pipeline import combineImageClip
from panelflow.pipeline.create_comic_panel_video import main as main_ComicVideoPipeline, Config as CVP_Config
from panelflow.pipeline import addMusic
from jebin_lib import HFTTSClient, utils

class DataFormat(BaseModel):
    data: str


class titleAndDescription(BaseModel):
    youtube_title: str
    twitter_post: str


class ComicReview(CategoryBase):

    def __init__(self, processor_obj):
        super().__init__(config.COMIC_REVIEW, processor_obj)

    def get_cred_token_file_name(self):
        return ("ytcredentials.json", "yttoken.json")

    def get_yt_description(self):
        return (
            "Join me as we break down the latest comics, diving deep into its themes, "
            "character development, and key plot points.\n\n"
            "#comics #ComicBreakdown #ComicAnalysis #ComicReview #ComicNarration #ComicStorytelling"
        )

    def get_yt_tags(self):
        return ['ComicBreakdown', 'ComicAnalysis', 'ComicReview', 'ComicNarration', 'ComicStorytelling', 'comics']

    def get_recap_length(self, type):
        if type == "min":
            return 0
        return 10000000000000000

    # ------------------------------------------------------------------ prompts

    def review_system_prompt(self):
        return """You are an engaging comic narrator, skilled at transforming comic chapters into immersive storytelling content for YouTube. Your job is to:

### 🎬 Transform Comic Panels Into Narrative Storytelling

* Convert visual panels into vivid, flowing narration.
* Focus on **story-relevant content only**, including:

  * Key plot points and major developments
  * Character actions, dialogue, and meaningful interactions
  * Visual cues that drive the story (e.g. setting, props, expressions)
  * Scene atmosphere and tone

### 🎙 Maintain Immersive, Natural Storytelling

* Use a **conversational, emotionally resonant style**
* Describe character **expressions, tone of voice, and emotional shifts**
* Create atmosphere through descriptive language and mood-setting details
* Adapt tone to match each scene: **dramatic, intense, comedic, or heartfelt**
* Distinguish characters with **unique vocal styles or descriptors** where appropriate
* Avoid all sound effects, onomatopoeia, or audio cues - focus purely on narrative description

### 🧭 Ensure Seamless Narrative Flow

* Narrate as **one continuous story** — no references to panels, pages, or transitions
* Keep pacing tight and focused, matching story beats
* Avoid any mention of publishing info, credits, or metadata

### 🎧 Keep the YouTube Audience Engaged

* Use **dynamic, cinematic descriptions** that complement what viewers see
* Balance action, dialogue, and quiet moments for emotional impact
* Set scenes clearly, but concisely — **let mood and moment lead**
* Make viewers feel invested in the characters and their journey
* Write only speakable content that flows naturally when read by TTS systems

Response ONLY IN JSON FORMAT:
{
\t"data":""
}
"""

    def get_user_prompt(self):
        return """Transform these comic pages into a dynamic 1 minute Recap.

Recap Text Requirements:

Start with a powerful 1-2 sentence hook
Analyze main narrative content only
Focus on key plot points, dramatic moments within the core story, clear and punchy sentences that sound natural when read aloud
Avoid complex words or phrases that might trip up TTS engines
Build tension through pacing and word choice
MUST be 1 minute when read at natural speaking pace
Include clear beginning, middle, and end
Use engaging, present-tense narrative style
Maintain suspense and viewer interest
Length guideline: 1 minute duration
Include natural pauses and breathing room (using punctuation like ..., —, !)

Write in a style that balances descriptive storytelling with fast-paced energy suitable for Shorts.

VALIDATION STEPS:
Make sure recap is 1 minute duration
Confirm focus on core narrative only"""

    def dialogue_matcher_system_prompt(self):
        return """Task: ComicPage-Recap Matching

Goal: Match recap/summary sentences to their most relevant source Comic Page. Each recap sentence must be paired with at least one corresponding Comic Page excerpt.

Matching Rules:
- Every recap sentence must have at least one Comic Page match.
- Prioritize the most relevant Comic Page for each recap.

Output Format (JSON):

{
\t"data":[{
\t\t"recap_sentence": "string",
\t\t"comic_page_number": "string"
\t}]
}"""

    def title_and_desc_system_prompt(self):
        return """# Social Media Content Creator

Create engaging YouTube titles and Twitter posts that get clicks and engagement.

## Output Format
```json
{
\t"youtube_title": "Your title here",
\t"twitter_post": "Your post here"
}
```

## YouTube Title Rules
- **Max 100 characters** (best: 60-70)
- Use casual, conversational tone
- Create curiosity without revealing everything
- **Never mention movie names** - keep them mysterious
- **Never use words**: "review", "recap", "breakdown"
- Use hooks like: "This comic changed everything", "You won't believe what happens"
- Include emotional triggers: "shocking", "unexpected", "incredible", "mind-blowing"

## Twitter Post Rules
- **Max 280 characters**
- Add 1-2 emojis, 2-3 hashtags
- **Absolutely NO link references**
- Write complete standalone thoughts

## Exclude
- **Never mention movie/comic/anime names**
- **Never use words**: "review", "recap", "breakdown", "analysis"
"""

    def title_desc_user_prompt(self):
        return "Create a suitable youtube title and twitter post for the above."

    def title_desc_schema(self):
        return genai.types.Schema(
            type=genai.types.Type.OBJECT,
            required=["youtube_title", "twitter_post"],
            properties={
                "youtube_title": genai.types.Schema(type=genai.types.Type.STRING),
                "twitter_post": genai.types.Schema(type=genai.types.Type.STRING),
            },
        )

    def recap_schema(self):
        return genai.types.Schema(
            type=genai.types.Type.OBJECT,
            required=["data"],
            properties={"data": genai.types.Schema(type=genai.types.Type.STRING)},
        )

    def dialogue_matcher_schema(self):
        return genai.types.Schema(
            type=genai.types.Type.OBJECT,
            required=["data"],
            properties={
                "data": genai.types.Schema(
                    type=genai.types.Type.ARRAY,
                    items=genai.types.Schema(
                        type=genai.types.Type.OBJECT,
                        required=["comic_page_number", "recap_sentence"],
                        properties={
                            "comic_page_number": genai.types.Schema(type=genai.types.Type.INTEGER),
                            "recap_sentence": genai.types.Schema(type=genai.types.Type.STRING),
                        },
                    ),
                )
            },
        )

    def get_recap_match_user_prompt(self, recap_text):
        return f"""Recap: {recap_text}

For each sentence in the "Recap" find ONE exact or most suitable comic page.

OUTPUT FORMAT:
{{
\t"data":[{{
\t\t"recap_sentence":"<sentence from Recap>",
\t\t"comic_page_number":"<comic_page_number>"
\t}}]
}}"""

    def get_welcome_phrase(self):
        return ''

    def get_finish_phrase(self):
        return "Thanks for tuning in. Stay curious, stay awesome, and don't forget to hit that subscribe button for more amazing content"

    # ------------------------------------------------------------------ helpers

    def parse_content(self, content, format=None):
        try:
            data = json_repair.loads(content)
            if "moments" in data:
                return data["moments"]
            return data
        except Exception:
            raise ValueError("LLM failed to correct the data")

    def retry(self, recap, geminiWrapper, format, key):
        if len(recap) > self.get_recap_length("max") or len(recap) < self.get_recap_length("min"):
            for i in range(5):
                model_responses = geminiWrapper.send_message(
                    user_prompt="Please try again, duration did not meet the criteria."
                )
                new_recap = ""
                for model_res in model_responses:
                    local_recap = self.parse_content(model_res, format=format)[key]
                    new_recap += f" {local_recap}"
                if len(new_recap) <= self.get_recap_length("max") and len(new_recap) > len(recap):
                    recap = new_recap
                if len(new_recap) <= self.get_recap_length("max") and len(new_recap) >= self.get_recap_length("min"):
                    recap = new_recap
                    break
        return common.clean_text(recap)

    # ------------------------------------------------------------------ step 1

    def get_page_review(self, review_responses):
        """Step 1 — AI narration per page → review_responses.json (page entries only)."""
        p = self.processor_obj
        files = sorted(utils.list_files(p.panels_dir))
        files = [f for f in files if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp'))]
        file_len = len(files)

        review_history = []
        if os.path.exists(p.review_history_path):
            with open(p.review_history_path, 'rb') as f:
                review_history = pickle.load(f)

        review_history = gemini_history_processor.deduplicate_history(review_history)
        geminiWrapper = pre_model_wrapper(
            system_instruction=self.review_system_prompt(),
            schema=self.recap_schema(),
            history=review_history
        )
        key = geminiWrapper.get_schema().required[0]
        already_processed = len(review_history) // 2

        # Populate from existing history entries not yet in review_responses
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
                    user_prompt=f"{p.folder_name} :: page {i + 1} of {file_len}",
                    file_path=files[i],
                )
                try:
                    impact_value = json_repair.loads(model_responses[0]).get(key)
                except Exception as e:
                    impact_value = f"Error: {e}"
                review_responses.append({"key_moment": files[i], "impact": impact_value})
                gemini_history_processor.save_history(
                    p.review_history_path, review_history + geminiWrapper.get_history()
                )
        except Exception:
            gemini_history_processor.save_history(
                p.review_history_path, review_history + geminiWrapper.get_history()
            )
            # Fallback: AIStudioUIChat per remaining page
            from browser_manager.browser_config import BrowserConfig
            from chat_bot_ui_handler import AIStudioUIChat

            for i in range(len(review_responses), len(files)):
                review_history = gemini_history_processor.load_history(p.review_history_path)
                review_history = gemini_history_processor.deduplicate_history(review_history)
                history_text = gemini_history_processor.history_to_text(review_history)
                config = BrowserConfig()
                config.user_data_dir = os.getenv("PROFILE_PATH", None)
                config.additionl_docker_flag = ' '.join(common.get_neko_additional_flags(config))
                user_prompt = f"{p.folder_name} :: page {i + 1} of {file_len}"
                result = json_repair.loads(
                    AIStudioUIChat(config).quick_chat(
                        user_prompt=f"Previous Pages Narration:: {history_text}\n\nNext Page:: {user_prompt}",
                        system_prompt=self.review_system_prompt(),
                        file_path=files[i]
                    )
                )
                impact_value = result[key]
                if impact_value and len(impact_value) > 10:
                    review_responses.append({"key_moment": files[i], "impact": impact_value})
                    gemini_history_processor.append_history(
                        p.review_history_path, user_prompt, json.dumps(result)
                    )

        p.save_review_responses(review_responses)
        return review_responses

    # ------------------------------------------------------------------ step 2

    def get_all_page_recap(self, review_responses):
        """Step 2 — Combine page reviews into 1-min recap → recap_title_desc.json {recap_text}."""
        p = self.processor_obj
        rtd = p.load_recap_title_desc()
        if rtd.get("recap_text"):
            return

        review_history = []
        if os.path.exists(p.review_history_path):
            with open(p.review_history_path, 'rb') as f:
                review_history = pickle.load(f)

        geminiWrapper = pre_model_wrapper(
            system_instruction=self.review_system_prompt(),
            schema=self.recap_schema(),
            history=review_history
        )
        key = geminiWrapper.get_schema().required[0]
        model_responses = geminiWrapper.send_message(user_prompt=self.get_user_prompt())
        recap_text = common.clean_text(
            self.parse_content(model_responses[0], format=DataFormat.model_json_schema())[key]
        )
        recap_text = self.retry(recap_text, geminiWrapper, DataFormat.model_json_schema(), key)

        with open(p.recap_history_path, 'wb') as f:
            pickle.dump(geminiWrapper.get_history(), f)

        rtd["recap_text"] = recap_text
        p.save_recap_title_desc(rtd)

    # ------------------------------------------------------------------ step 3

    def get_main_title(self):
        """Step 3 — Generate YouTube title + Twitter post → recap_title_desc.json."""
        p = self.processor_obj
        rtd = p.load_recap_title_desc()
        if rtd.get("youtube_title"):
            return

        with open(p.recap_history_path, 'rb') as f:
            recap_history = pickle.load(f)

        geminiWrapper = pre_model_wrapper(
            system_instruction=self.title_and_desc_system_prompt(),
            schema=self.title_desc_schema(),
            history=recap_history
        )
        model_responses = geminiWrapper.send_message(user_prompt=self.title_desc_user_prompt())
        title_desc = self.parse_content(model_responses[0], format=titleAndDescription.model_json_schema())
        rtd["youtube_title"] = re.sub(r'\{.*?\}|\[.*?\]', '', title_desc["youtube_title"])
        rtd["twitter_post"] = re.sub(r'\{.*?\}|\[.*?\]', '', title_desc["twitter_post"])
        p.save_recap_title_desc(rtd)

        # First page impact = YouTube title (short cover text, same as CaptionCreator)
        review_responses = p.load_review_responses()
        if review_responses:
            review_responses[0]["impact"] = rtd["youtube_title"]
            review_responses[0]["is_sanitise_done"] = False
            p.save_review_responses(review_responses)

    # ------------------------------------------------------------------ step 4

    def get_recap_match(self):
        """Step 4 — Match recap sentences to comic pages → recap_match.json."""
        p = self.processor_obj
        if os.path.exists(p.recap_match_path):
            return

        rtd = p.load_recap_title_desc()
        recap_text = rtd.get("recap_text", "")

        with open(p.recap_history_path, 'rb') as f:
            recap_history = pickle.load(f)

        geminiWrapper = pre_model_wrapper(
            system_instruction=self.dialogue_matcher_system_prompt(),
            schema=self.dialogue_matcher_schema(),
            history=recap_history
        )
        key = geminiWrapper.get_schema().required[0]
        model_responses = geminiWrapper.send_message(
            user_prompt=self.get_recap_match_user_prompt(recap_text)
        )
        recap_match = self.parse_content(model_responses[0])[key]
        p.save_recap_match(recap_match)

    # ------------------------------------------------------------------ step 5

    def sanitise_sentences(self, review_responses):
        """Step 5 — Remove sound effects from page impacts + recap_text."""
        p = self.processor_obj

        # Sanitise per-page impacts
        changed = False
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
            p.save_review_responses(review_responses)

        # Sanitise recap_text
        rtd = p.load_recap_title_desc()
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
            p.save_recap_title_desc(rtd)

        return review_responses

    # ------------------------------------------------------------------ step 6a

    def _resize_add_padding(self, background):
        background = background.resize((config.IMAGE_SIZE[1], config.IMAGE_SIZE[1]))
        add_width = (config.IMAGE_SIZE[0] - config.IMAGE_SIZE[1]) // 2
        background = ImageOps.expand(background, border=(add_width, 0), fill=(0, 0, 0))
        return background

    def resize_frame(self, img_path, i):
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

    def split_comic_page(self, image_path, output_dir, split_folder):
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

    def create_sentence_clips(self, review_responses):
        """Step 6a — Landscape (1920×1080) clip per page narration → sentence_media/."""
        p = self.processor_obj

        for i, moment in enumerate(review_responses):
            if not utils.file_exists(moment["key_moment"]):
                raise ValueError(f"create_sentence_clips page {i+1}/{len(review_responses)}: key_moment not found: {moment['key_moment']}")
            logger_config.info(f"create_sentence_clips page {i+1}/{len(review_responses)}", overwrite=True)
            impact = f'{self.get_welcome_phrase()} {moment["impact"]}' if i == 0 else moment["impact"]
            if i + 1 == len(review_responses):
                impact = f'{moment["impact"]} {self.get_finish_phrase()}'
            impact = impact.strip()

            file_name = utils.generate_random_string_from_input(impact)
            page_dir = os.path.join(p.sentence_media_dir, f"{i+1:04d}")
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
                image_path = self.resize_frame(moment["key_moment"], i)
                split_dir = os.path.join(page_dir, f"split_{i+1:04d}")
                self.split_comic_page(image_path, page_dir, split_dir)
                common.delete_matching_videos(page_dir, f"{i+1:04d}_*.mp4")
                cvp_config = CVP_Config()
                cvp_config.comic_title = p.folder_name
                cvp_config.main_file_name = moment["key_moment"]
                cvp_config.comic_image = image_path
                cvp_config.output_video = video_path
                cvp_config.page_specific_dir = page_dir
                cvp_config.split_output_dir = split_dir
                main_ComicVideoPipeline(impact, cvp_config)

    # ------------------------------------------------------------------ step 6b

    def create_shorts_clips(self):
        """Step 6b — Portrait (1080×1920) image-slide clip per recap_match sentence → shorts_media/."""
        p = self.processor_obj
        files = sorted(utils.list_files(p.panels_dir))
        files = [f for f in files if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp'))]

        recap_match = p.load_recap_match()
        if not recap_match:
            return

        hf_tts = HFTTSClient()
        changed = False

        for i, match in enumerate(recap_match):
            page_idx = int(match["comic_page_number"]) - 1
            if not (0 <= page_idx < len(files)) or not utils.file_exists(files[page_idx]):
                continue

            # TTS audio
            audio_path = os.path.join(p.shorts_media_dir, f"audio_{i}.wav")
            if not utils.is_valid_audio(audio_path):
                hf_tts.generate_audio_segment(match["recap_sentence"].strip(), audio_path)

            _, duration, _, _ = common.get_media_metadata(audio_path)
            match["duration"] = duration

            # Resize to portrait 1080×1920
            base_name = os.path.basename(files[page_idx])
            resized = os.path.join(p.shorts_media_dir, f"resized_{base_name}.jpg")
            if not utils.file_exists(resized):
                portrait = (config.IMAGE_SIZE[1], config.IMAGE_SIZE[0])  # 1080×1920
                with Image.open(files[page_idx]) as img:
                    img.resize(portrait, Image.LANCZOS).convert('RGB').save(resized)
            match["img_path"] = resized
            changed = True

        if changed:
            p.save_recap_match(recap_match)
