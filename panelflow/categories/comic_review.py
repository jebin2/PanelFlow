from panelflow import common
from panelflow import config as custom_env
from panelflow.categories.video_reviewer import VideoReviewer
from panelflow.pipeline.gemini_config import pre_model_wrapper
from panelflow import databasecon
from custom_logger import logger_config
from PIL import Image
from google import genai
from pydantic import BaseModel
import traceback
from panelflow.categories.video_reviewer import DataFormat
import time
from PIL import ImageOps
import json
from panelflow.pipeline import combineImageClip
from panelflow.pipeline.create_comic_panel_video import main as main_ComicVideoPipeline, Config as CVP_Config
import re
import os
import shlex
import pickle
import json_repair
from browser_manager.browser_config import BrowserConfig
from chat_bot_ui_handler import GeminiUIChat, AIStudioUIChat
from panelflow.pipeline import gemini_history_processor
from panelflow.pipeline import resize_with_aspect
from panelflow.pipeline import remove_sound_effect
from jebin_lib import HFTTSClient, utils

class RecapComicMatch(BaseModel):
	comic_page_number: str
	recap_sentence: str

class ReCapMatch(BaseModel):
	data: list[RecapComicMatch]

class ComicReview(VideoReviewer):

	def __init__(self, create_new=False):
		super().__init__(create_new)
		common.create_directory(custom_env.COMIC_REVIEW_PATH)

	def get_type(self):
		return custom_env.COMIC_REVIEW

	def review_system_prompt(self, script_file=None):
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
* Adapt tone to match each scene: dramatic, intense, comedic, or heartfelt
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
	"data":""
}
"""

	def dialogue_matcher_system_prompt(self):
		return """Task: ComicPage-Recap Matching

Goal: Match recap/summary sentences to their most relevant source Comic Page. Each recap sentence must be paired with at least one corresponding Comic Page excerpt.

Input:

Recap Sentences: A list of sentences summarizing events, actions, or themes.

Matching Process:

Match Types (in order of preference):

Direct: Comic Page explicitly describing the same events, actions, or direct quotes used in the recap.

Supporting: Comic Page that provides context, related character interactions, or establishes key information directly tied to the recap's content.

Thematic: Comic Page providing relevant background, character reactions, or setting information that contributes to the overall theme of the recap.

Matching Rules:

Required Matching: Every recap sentence must have at least one Comic Page match.

Relevance: Prioritize the most relevant Comic Page for each recap.

Context: Include speaker context and character names when beneficial.

Output Format (JSON):

{
	"data":[{
		"recap_sentence": "string",
		"comic_page_number": "string"
	}]
}
Use code with caution.
Quality Assurance:

Contextual Relevance: Ensure the Comic Page meaningfully supports the recap statement."""

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

	def get_source_folder_path(self):
		if not common.dir_exists(custom_env.COMIC_REVIEW_PATH):
			common.create_directory(custom_env.COMIC_REVIEW_PATH)
		return custom_env.COMIC_REVIEW_PATH

	def get_source_path(self, path=None):
		path = self.get_source_folder_path()

		dirs = sorted(common.list_directories_recursive(path)) # sorting is very importanat
		datas = databasecon.execute(f"select id, videoPath from {custom_env.TABLE_NAME} where type='{self.get_type()}'")
		added_dir = []
		for data in datas:
			id, videoPath = data
			added_dir.append(videoPath)

		return dirs[0]

	def get_source_data(self, videoPath=None):
		return []

	def is_audio_creation_allowed(self):
		return False

	def dialogue_matcher_schema(self):
		return genai.types.Schema(
			type = genai.types.Type.OBJECT,
			required = ["data"],
			properties = {
				"data": genai.types.Schema(
					type = genai.types.Type.ARRAY,
					items = genai.types.Schema(
						type = genai.types.Type.OBJECT,
						required = ["comic_page_number", "recap_sentence"],
						properties = {
							"comic_page_number": genai.types.Schema(
								type = genai.types.Type.INTEGER,
							),
							"recap_sentence": genai.types.Schema(
								type = genai.types.Type.STRING,
							),
						},
					),
				),
			},
		)

	def recap_schema(self):
		return genai.types.Schema(
			type = genai.types.Type.OBJECT,
			required = ["data"],
			properties = {
				"data": genai.types.Schema(
					type = genai.types.Type.STRING,
				),
			},
		)

	def get_recap_match_user_prompt(self, recap):
		return f"""Recap: {recap}

For each sentence in the "Recap" find ONE exact or most suitable comic page.

OUTPUT FORMAT:
{{
	"data":[{{
		"recap_sentence":"<sentence from Recap>",
		"comic_page_number":"<comic_page_number>"
	}}]
}}"""

	def get_page_review(self, id, json_data):
		review_responses = json_data.get("review_responses", [])
		if not review_responses:
			title = self.get_db_entry()[databasecon.getId('title')]
			videoPath = self.get_db_entry()[databasecon.getId('videoPath')]
			files = sorted(common.list_files(videoPath))
			file_len = len(files)
			review_history_path = f'{custom_env.REUSE_SPECIFIC_PATH}/review_history.pkl'
			review_history = []
			try:
				with open(review_history_path, 'rb') as f:
					review_history = pickle.load(f)
			except: pass
			review_history = gemini_history_processor.deduplicate_history(review_history)
			geminiWrapper = pre_model_wrapper(
				system_instruction=self.review_system_prompt(),
				schema=self.recap_schema(),
				# delete_files=True,
				history=review_history
			)
			key = geminiWrapper.get_schema().required[0]
			already_processed = len(review_history) // 2

			# --- 1️⃣ Populate from existing review_history ---
			for i in range(min(already_processed, len(files))):
				file_path = files[i]
				model_index = i * 2 + 1  # model entries follow user entries
				if model_index < len(review_history):
					try:
						model_content = review_history[model_index].parts[0].text
						parsed_data = json_repair.loads(model_content)
						impact_value = parsed_data.get(key)
					except Exception as e:
						impact_value = f"Error parsing old response: {e}"
				else:
					impact_value = "Missing from review_history"

				review_responses.append({
					"key_moment": file_path,
					"impact": impact_value
				})
			try:
				# --- 2️⃣ Process remaining files using Gemini ---
				for i in range(already_processed, len(files)):
					file_path = files[i]
					model_responses = geminiWrapper.send_message(
						user_prompt=f"{title} :: page {i + 1} of {file_len}",
						file_path=file_path,
					)

					try:
						parsed_data = json_repair.loads(model_responses[0])
						impact_value = parsed_data.get(key)
					except Exception as e:
						impact_value = f"Error parsing new response: {e}"

					review_responses.append({
						"key_moment": file_path,
						"impact": impact_value
					})

					# Save merged history to pickle (without mutating old list)
					gemini_history_processor.save_history(review_history_path, review_history + geminiWrapper.get_history())
			except:
				gemini_history_processor.save_history(review_history_path, review_history + geminiWrapper.get_history())
				for i in range(already_processed, len(files)):
					review_history = gemini_history_processor.load_history(review_history_path)
					review_history = gemini_history_processor.deduplicate_history(review_history)
					already_processed = len(review_history) // 2
					review_history_to_text = gemini_history_processor.history_to_text(review_history)
					config = BrowserConfig()
					config.user_data_dir = os.getenv("PROFILE_PATH", None)

					# Set up additional docker flags
					config.additionl_docker_flag = ' '.join(common.get_neko_additional_flags(config))
					baseUIChat = AIStudioUIChat(config)

					file_path = files[i]
					user_prompt=f"{title} :: page {i + 1} of {file_len}"
					result = json_repair.loads(baseUIChat.quick_chat(
						user_prompt=f"""Previous Pages Narration:: {review_history_to_text}

Next Page:: {user_prompt}""",
						system_prompt=self.review_system_prompt(),
						file_path = file_path
					))
					impact_value = result[key]
					if impact_value and len(impact_value) > 10:
						review_responses.append({
							"key_moment": file_path,
							"impact": impact_value
						})
						gemini_history_processor.append_history(review_history_path, user_prompt, json.dumps(result))

			json_data.update({
				"review_responses": review_responses
			})
			self.save_json_data(id, json_data)

		return json_data

	def get_all_page_recap(self, id, json_data):
		logger_config.debug("Getting Recap...")
		review_responses, recap_response = json_data.get("review_responses"), json_data.get("recap_response")
		review_history_path = f'{custom_env.REUSE_SPECIFIC_PATH}/review_history.pkl'
		with open(review_history_path, 'rb') as f:
			review_history = pickle.load(f)
		if not recap_response:
			geminiWrapper = pre_model_wrapper(
				system_instruction=self.review_system_prompt(),
				schema=self.recap_schema(),
				history=review_history
			)
			key = geminiWrapper.get_schema().required[0]
			model_responses = geminiWrapper.send_message(
				user_prompt=self.get_user_prompt()
			)
			recap_response = common.clean_text(self.parse_content(model_responses[0], format=DataFormat.model_json_schema())[key])
			review_responses.append({
				"key_moment": "overview",
				"impact": recap_response
			})
			recap_response = self.retry(recap_response, geminiWrapper, DataFormat.model_json_schema(), key)
			review_responses[-1]["impact"] = recap_response

			recap_history_path = f'{custom_env.REUSE_SPECIFIC_PATH}/recap_history.pkl'
			with open(recap_history_path, 'wb') as f:
				pickle.dump(geminiWrapper.get_history(), f)

			json_data.update({
				"review_responses": review_responses,
				"recap_response": recap_response
			})
			self.save_json_data(id, json_data)

		return json_data

	def get_main_title(self, id, json_data):
		review_responses = json_data.get("review_responses")
		recap_history_path = f'{custom_env.REUSE_SPECIFIC_PATH}/recap_history.pkl'
		with open(recap_history_path, 'rb') as f:
			recap_history = pickle.load(f)
		youtube_title = review_responses[0].get("youtube_title")
		if not youtube_title:
			self.title_and_desc_generator(recap_history, review_responses)
			review_responses[0]["youtube_title"] = review_responses[0]["youtube_title"]
			review_responses[0]["twitter_post"] = review_responses[0]["twitter_post"]
			review_responses[0]["impact"] = review_responses[0]["youtube_title"]

			json_data.update({
				"review_responses": review_responses
			})
			self.save_json_data(id, json_data)

		return json_data

	def get_recap_match(self, id, json_data):
		logger_config.debug("Matching comic page...")
		review_responses = json_data.get("review_responses")
		recap_history_path = f'{custom_env.REUSE_SPECIFIC_PATH}/recap_history.pkl'
		with open(recap_history_path, 'rb') as f:
			recap_history = pickle.load(f)
		recap_match = review_responses[-1].get("recap_match")
		if not recap_match:
			geminiWrapper = pre_model_wrapper(
				system_instruction=self.dialogue_matcher_system_prompt(),
				schema=self.dialogue_matcher_schema(),
				history=recap_history
			)
			key = geminiWrapper.get_schema().required[0]
			model_responses = geminiWrapper.send_message(
				user_prompt=self.get_recap_match_user_prompt(review_responses[-1]["impact"])
			)
			review_responses[-1]["recap_match"] = self.parse_content(model_responses[0], format=ReCapMatch.model_json_schema())[key]

			json_data.update({
				"review_responses": review_responses
			})
			self.save_json_data(id, json_data)

		return json_data

	def sanitise_sentences(self, id, json_data):
		logger_config.info("sanitise_sentences...")

		review_responses = json_data.get("review_responses")
		for i, res in enumerate(review_responses):
			logger_config.info(f"Working  sanitise_sentences {i+1} of {len(review_responses)}", overwrite=True)
			if "is_sanitise_done" not in res or "```" in res["impact"]:
				for j in range(5):
					try:
						sanitised_sentence = remove_sound_effect.remove(res["impact"])
						if "<unused" in sanitised_sentence or not common.is_same_sentence(sanitised_sentence, res["impact"], threshold=0.6):
							raise ValueError(f"sanitise_sentences is not correct")
						break
					except Exception as e:
						if j == 4: raise e

				res["before_sanitise"] = res["impact"]
				res["impact"] = sanitised_sentence
				if i == 0:
					res["impact"] = re.sub(r"recap", "", res["impact"], flags=re.IGNORECASE)
				res["is_sanitise_done"] = True

				json_data.update({
					"review_responses": review_responses
				})
				self.save_json_data(id, json_data)

		return review_responses

	def get_google_ai_studio_key_moment(self):
		try:
			db_entry = self.get_db_entry()
			id = db_entry[databasecon.getId("id")]
			json_data = db_entry[databasecon.getId("json_data")]
			videoPath = db_entry[databasecon.getId("videoPath")]
			try:
				if json_data:
					json_data = json.loads(json_data)
			except: pass
			if not json_data:
				json_data = {}

			json_data = self.get_page_review(id, json_data)
			json_data = self.get_all_page_recap(id, json_data)

			json_data = self.get_main_title(id, json_data)
			json_data = self.get_recap_match(id, json_data)

			return self.sanitise_sentences(id, json_data)

		except Exception as e:
			raise ValueError(f'Error in get_google_ai_studio_key_moment {e}\n{traceback.format_exc()}')

	def get_frame_path(self, moment, videoPath, sub_path, i):
		return None if moment["key_moment"] == "overview" else moment["key_moment"]

	def __resize_add_padding(self, background):
		background = background.resize((custom_env.IMAGE_SIZE[1], custom_env.IMAGE_SIZE[1]))
		add_width = (custom_env.IMAGE_SIZE[0] - custom_env.IMAGE_SIZE[1]) // 2
		background = ImageOps.expand(background, border=(add_width, 0), fill=(0, 0, 0))
		return background

	def resize_frame(self, img_path, i):
		comic_name = img_path.split("/")[-2]
		base_name = os.path.basename(img_path)
		output_path = f'{custom_env.TEMP_OUTPUT}/{comic_name}_{base_name}_resize_frame.jpg'
		if common.file_exists(output_path):
			return output_path
		with Image.open(img_path) as background:
			resized_image = self.__resize_add_padding(background) if i == 0 else background.resize((custom_env.IMAGE_SIZE[0], background.height), Image.LANCZOS)
			if output_path.lower().endswith('.jpg') or output_path.lower().endswith('.jpeg'):
				resized_image = resized_image.convert('RGB')
			resized_image.save(output_path)
			return output_path

	def split_comic_page(self, image_path, output_dir, split_comic_folder_path):
		completed_file_name = f'{split_comic_folder_path}/completed'
		if not common.file_exists(completed_file_name):
			common.remove_directory(split_comic_folder_path)
			common.create_directory(split_comic_folder_path)
			config_data = {
				"input_path": image_path,
				"output_folder": split_comic_folder_path
			}

			config_path = f'{output_dir}/split_comic_config.json'
			# Write config JSON
			with open(config_path, 'w') as file:
				json.dump(config_data, file, indent=4, ensure_ascii=False)

			cwd = "/tmp/comic-panel-extractor"
			if not common.dir_exists(cwd):
				utils.setup_git_repo_get_install_pip(
					repo_url="https://github.com/jebin2/comic-panel-extractor.git",
					target_path=cwd,
					pip_name="comic-panel-extractor",
				)
				if not common.dir_exists(cwd):
					raise ValueError("comic-panel-extractor not setup correctly.")

			# Build command
			python_path = os.path.expanduser("~/.pyenv/versions/comic-panel-extractor_env/bin/comic-panel-extractor")
			cmd = f"""{python_path} --config {shlex.quote(config_path)}"""
			logger_config.info(f"Command to run:: {cmd}")

			common.run_subprocess_with_retry(
				cmd=cmd,
				cwd=cwd,
				repo_url="https://github.com/jebin2/comic-panel-extractor.git",
				pip_name="comic-panel-extractor"
			)

			if len([
				os.path.abspath(file)
				for file in common.list_files(split_comic_folder_path)
				if "_panel_" in os.path.basename(file)
			]) > 0:
				with open(completed_file_name, 'w') as file:
					file.write("Done")
			else:
				raise ValueError("comic not extracted.")

	def create_frame_params(self, segments=None, background_path=None, font_path=None, start_show_answer=None, frames_details=None, fps=custom_env.FPS):
		key_moment = json.loads(self.get_db_entry()[databasecon.getId("answer")])
		logger_config.debug(f'key_moment:: {key_moment}')

		video_files = []
		for i, moment in enumerate(key_moment):
			if common.file_exists(moment["key_moment"]):
				logger_config.info(f"Working create_frame_params {i+1} of {len(key_moment)-1}", overwrite=True)
				impact = f'{self.get_welcome_phrase()} {moment["impact"]}' if i == 0 else moment["impact"]
				impact = f'{moment["impact"]} {self.get_finish_phrase()}' if i + 1 == len(key_moment) else impact
				file_name = common.generate_random_string_from_input(impact)
				page_specific_dir = f'{custom_env.REUSE_SPECIFIC_PATH}/{i+1:04d}'
				utils.create_directory(page_specific_dir)
				video_path = f'{page_specific_dir}/{file_name}.mp4'
				video_files.append(video_path)

				# if not common.file_exists(video_path):
				if i == 0:
					image_path = moment["key_moment"]
					if not common.file_exists(video_path):
						output_path = f'{custom_env.TEMP_OUTPUT}/{common.generate_random_string()}.wav'
						hf_tts_client = HFTTSClient()
						hf_tts_client.generate_audio_segment(impact.strip(), output_path)
						_, duration, _, _ = common.get_media_metadata(output_path)
						resized_output_path = f'{custom_env.TEMP_OUTPUT}/{os.path.basename(image_path)}'
						resize_with_aspect.scale_keep_ratio(image_path, custom_env.IMAGE_SIZE[0], custom_env.IMAGE_SIZE[1], resized_output_path, blur_bg=True)
						clips = combineImageClip.start([{
							"img_path": resized_output_path,
							"clip_duration": duration,
							"clip_start": 0,
							"donot_animate": i == 0 if self.get_type() == custom_env.COMIC_REVIEW else False
						}], fps)
						import addMusic
						addMusic.process(clips[0], output_path, output_path=video_path, extend_video=True, trim_video=True)
				elif not common.file_exists(video_path):
					image_path = self.resize_frame(moment["key_moment"], i)
					split_output_dir = f'{page_specific_dir}/split_{i+1:04d}'
					self.split_comic_page(image_path, page_specific_dir, split_output_dir)

					common.delete_matching_videos(page_specific_dir, f'{i+1:04d}_*.mp4')
					cvp_config = CVP_Config()
					cvp_config.comic_title = self.get_db_entry()[databasecon.getId('title')]
					cvp_config.main_file_name = moment["key_moment"]
					cvp_config.temp_folder=page_specific_dir
					cvp_config.comic_image = image_path
					cvp_config.output_video = video_path
					cvp_config.page_specific_dir = page_specific_dir
					cvp_config.split_output_dir = split_output_dir
					main_ComicVideoPipeline(impact, cvp_config)

		return video_files

	def post_process(self, start_show_answer=None):
		self.refresh_db_entry()
		super().post_process(start_show_answer)
		self.refresh_db_entry()

		self.comic_shorts_creator()

	def comic_shorts_creator(self):
		if self.get_type() == custom_env.COMIC_REVIEW:
			db_entry = self.get_db_entry()
			videoPath = db_entry[databasecon.getId("videoPath")]
			result = databasecon.execute(f"select id, videoPath from {custom_env.TABLE_NAME} where videoPath=? and type=?", values=(videoPath, custom_env.COMIC_SHORTS), type="get")
			create_shorts = True
			if result:
				id, path = result
				if id:
					create_shorts = False
					logger_config.info(f"Comic Shorts Entry is already created.")
			if create_shorts:
				title = videoPath.split("/")[-1]
				answer = db_entry[databasecon.getId("answer")]
				otherDetails = db_entry[databasecon.getId("otherDetails")]
				json_data = json.loads(db_entry[databasecon.getId("json_data")])
				json_data.pop("add_caption", None)
				json_data.pop("add_bg_music", None)

				lastModifiedTime = int(time.time() * 1000)

				lastrowid = databasecon.execute(f"""INSERT into {custom_env.TABLE_NAME} (title, videoPath, answer, otherDetails, json_data, type, lastModifiedTime) VALUES (?, ?, ?, ?, ?, ?, ?)""", (title, videoPath, answer, otherDetails, json.dumps(json_data, ensure_ascii=False), custom_env.COMIC_SHORTS, lastModifiedTime), type='lastrowid')

				logger_config.info(f"Comic Shorts Entry is created:: {lastrowid}")

	def get_yt_description(self):
		return f"""Join me as we break down the latest comics, diving deep into its themes, character development, and key plot points. In this video, we analyze the most impactful moments and explore the hidden meanings behind the story. Don't forget to like, comment, and subscribe for more comic breakdowns!

#comics #ComicBreakdown #ComicAnalysis #ComicReview #ComicNarration #ComicStorytelling"""

	def get_yt_tags(self):
		return ['ComicBreakdown', 'ComicAnalysis ', 'ComicReview', 'ComicNarration', 'ComicStorytelling', 'comics']

	def get_recap_length(self, type):
		if type == "min":
			return 0
		return 10000000000000000