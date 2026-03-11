from prop_content import PropContent
from custom_logger import logger_config
import traceback
import databasecon
import common
import shutil
import custom_env
import re
import json
import video_clipper
import gc
import time
import json_parser
from pydantic import BaseModel
from gemini_config import pre_model_wrapper, compress_and_split, compress
from google import genai
from PIL import Image
import combineAudio
import os
import subprocess
from pathlib import Path
from browser_manager.browser_config import BrowserConfig
from chat_bot_ui_handler import GeminiUIChat, AIStudioUIChat
import json_repair
import os
from jebin_lib import HFTTTClient, HFTTSClient

CHAR_LEN = 4500
#27659

class ImpactMoment(BaseModel):
	key_moment: str
	impact: str

class ReviewFormat(BaseModel):
	moments: list[ImpactMoment]

class RecapDialogMoment(BaseModel):
	dialogue: str
	recap_sentence: str

class DialoguesFormat(BaseModel):
	dialogues: list[RecapDialogMoment]

class DataFormat(BaseModel):
	data: str

class titleAndDescription(BaseModel):
	youtube_title: str
	twitter_post: str

class VideoReviewer(PropContent):

	def __init__(self, main_instance=None, create_new=False):
		super().__init__(main_instance, create_new)

	# def get_series_name(self):
	#	 title = self.get_db_entry()[databasecon.getId("title")]
	#	 anime_name = title.split("Episode")[0].strip() if " Episode" in title else title
	#	 return anime_name

	def get_start_phrase(self):
		return None
	
	def get_welcome_phrase(self):
		# return f"Hello Everyone, Welcome to our next episode of {self.get_series_name()}."
		return ''
	
	def get_finish_phrase(self):
		return "Thanks for tuning in. Stay curious, stay awesome, and don't forget to hit that subscribe button for more amazing content"

	def get_description(self):
		segments = json.loads(self.get_db_entry()[databasecon.getId("otherDetails")])
		return " ".join([segment["text"] for segment in segments])

	def get_system_prompt(self, key_moment=20, transform=False, is_first=False, is_last=False):
		change_word = 'movie'
		change_word_1 = ''
		change_word_2 = change_word
		change_word_3 = 'episode' if self.get_type() == custom_env.COMBINE_ANIME_REVIEW else change_word
		impact_start_phrase = "Start first imapct with unique powerfull/epic opening that draws the listeners intrigued." if is_first else ''
		end_data = 'opening song or credits or Intro scenes' if is_first else ''
		end_data = 'closing song or credits scenes' if is_last else end_data
		if transform:
			# return f"""Transform each 'impact' field in the provided JSON array into a dramatically narrated, tension-building description.
			return f"""Transform each 'impact' field in the provided JSON array into a EPIC, HEART-POUNDING narratives that will leave viewers SPEECHLESS!

Guidelines:
- Preserve the original factual meaning
- Use a cinematic, deep-voiced narrator style
- Amplify emotional intensity
- Add dramatic flair without introducing new information

Transformation Goal: Make each impact sound like a pivotal moment in an epic narrative.
Maintain the exact JSON structure, leaving 'key_moment' fields untouched."""

		return f"""You are an expert in {change_word} recap, specializing in extracting and analyzing key narrative moments from {change_word_3}.

RECAP OBJECTIVES:
- Identify pivotal dialogue scenes that:
  * Significantly alter character dynamics
  * Reveal critical plot developments
  * Expose deep character motivations
  * Mark emotional or narrative turning points

OUTPUT SPECIFICATIONS:
- Produce a JSON array of exactly {key_moment} key moments
- Each moment must include:
  1. Verbatim dialogue text
  2. Comprehensive 5-6 sentence analytical detailed breakdown

SELECTION CRITERIA:
Dialogue Moments Must:
- Demonstrate clear narrative progression
- Reveal character depth or transformation
- Provide critical plot insights
- Maintain chronological coherence

RECAP GUIDELINES:
- Provide contextual framing for each moment
- Demonstrate how moments interconnect
- Maintain analytical precision
- Avoid subjective embellishment
- Focus on observable narrative impact

EXCLUSIONS:
- Eliminate:
  * Repetitive dialogue
  * Minor conversational exchanges
  * Stage directions
  * Peripheral narrative elements
- {end_data}

Focus on transformative narrative moments that fundamentally drive the story's progression.
"""

	def json_schema(self):
		return ReviewFormat.model_json_schema()

	def get_title_and_description(self):
		title = self.get_db_entry()[databasecon.getId("title")]
		key_moment = json.loads(self.get_db_entry()[databasecon.getId("answer")])
		if "youtube_title" in key_moment[0]:
			return key_moment[0]

		movie_or_anime = 'Comic'
		title = f"Comic Title: {title}"

		hf_ttt_client = HFTTTClient()
		content = hf_ttt_client.generate(
			text=title,
			system_prompt=f"""# {movie_or_anime} Content Title and Social Media Post Generator

## Core Objective
You are a viral content creator specializing in crafting irresistibly engaging titles and social media posts for {movie_or_anime} episodes, movies, and series. Your goal is to maximize audience curiosity, engagement, and click-through rates.

## Title Generation Guidelines (YouTube, <100 characters)
- Create DIRECT, EXPLOSIVE titles that INSTANTLY spark curiosity
- AVOID generic list formats like "Top 5" or "X Number of"
- Craft titles that:
  - Capture the CORE essence of the {movie_or_anime}
  - Use power words: "Shocking", "Insane", "Mind-Blowing", "Ultimate"
  - Incorporate dramatic tension or unexpected narrative hooks
  - Hint at epic moments without full spoilers
- Title Structure Recommendations:
  - {"[Movie Name]: [Provocative Descriptor]" if movie_or_anime == "Movie" else "[Anime Name][Episode/part number]: [Provocative Descriptor]"}
  - The Dark Secret Behind [{movie_or_anime} Name]
  - When [Dramatic Concept] Meets [Unexpected Twist]

## Tweet Generation Guidelines (<230 characters)
- AVOID providing links.
- Craft a teaser that leaves audience CRAVING more
- Mix intrigue, emotion, and strategic hashtags
- Use emotive language that creates instant connection
- Include strategic call-to-actions
- Leverage trending {movie_or_anime}/pop culture references
- Create FOMO (Fear of Missing Out)

## Tone Spectrum
- Intensity Range: 🔥 Mild to 🌋 VOLCANIC
- Emotional Triggers: Excitement > Shock > Curiosity > Anticipation

## Forbidden Practices
- No direct plot spoilers
- Avoid generic, bland descriptions
- No misleading clickbait that doesn't deliver
- No numbered list-style titles
- No Link

## Special Handling for Unknown {movie_or_anime}
If {movie_or_anime} details are unavailable:
- Generate a GENERIC but HYPER-ENGAGING title
- Create a mysterious, universally appealing social media post
- Use {movie_or_anime} genre tropes to create excitement

## Engagement Metrics to Consider
- Curiosity Quotient
- Emotional Impact
- Viral Potential
- Genre-Specific Appeal

## Final Checkpoint
Before output, ask:
- Does this make YOU want to click/watch?
- Would this trend on social media?
- Is it 10x more exciting than a standard description?

## Creative Constraints
- YouTube Title: MAX 100 characters
- Tweet: MAX 230 characters
- ALWAYS prioritize EXPLOSIVE engagement"""
)
		content = self.parse_content(content)
		content["youtube_title"] = re.sub(r'\{.*?\}|\[.*?\]', '', content["youtube_title"])
		content["twitter_post"] = re.sub(r'\{.*?\}|\[.*?\]', '', content["twitter_post"])
		logger_config.debug(content)
		return content

	def recap_user_prompt(self):
		return self.get_db_entry()[databasecon.getId("title")]

	def spelling_system_prompt(self):
		return """# Spelling Cross-Check System Prompt

You are a spelling verification assistant. Your task is to cross-check a given paragraph against provided video transcription to identify and correct spelling mistakes.

## Instructions:

1. **Use the video transcription as your spelling reference** - The transcription contains the correct spellings for terms, names, and concepts mentioned in the video
2. **Focus only on spelling errors** - Do not make changes to:
   - Grammar or sentence structure
   - Punctuation (unless it affects spelling context)
   - Word choice or vocabulary
   - Formatting or capitalization (unless it's a clear spelling mistake)

3. **Identify spelling mistakes by**:
   - Finding words in the paragraph that appear misspelled when compared to their correct versions in the transcription
   - Looking for typos, misspellings, or phonetic errors
   - Cross-referencing proper nouns, technical terms, and specific terminology from the transcription

4. **Output JSON format**:
{
  "corrected_paragraph": "Your continuous review content here, written as seamless continuation of the ongoing narrative without any segment or part references."
}

## Example:
**Paragraph**: "The cientist discussed quantum mecanics and Einsteins theory of relativity."
**Transcript**: "The scientist explained that quantum mechanics builds upon Einstein's revolutionary work..."
{
	"corrected_paragraph": "The scientist discussed quantum mechanics and Einstein's theory of relativity."
}

## Important Notes:
- The paragraph content may differ from the transcription but should use the same correct spellings
- Focus on matching spelling accuracy rather than exact word-for-word correspondence
- If a word appears in the paragraph but not in the transcription, apply standard spelling rules
- Maintain the original meaning and structure of the paragraph"""

	def spelling_schema(self):
		return genai.types.Schema(
			type = genai.types.Type.OBJECT,
			required = ["corrected_paragraph"],
			properties = {
				"corrected_paragraph": genai.types.Schema(
					type = genai.types.Type.STRING,
				),
			},
		)

	def spelling_user_prompt(self, Paragraph, otherDetails):
		return f"""**Paragraph**: {Paragraph}

- **Transcript**: {" ".join(seg['text'] for seg in otherDetails)}"""

	def dialogue_matcher_user_prompt(self, recap_sentence=None, dialogue_with_timestamp=None):
		return f"""Recap Sentence: {recap_sentence}

For the given sentence from the "Recap" find ONE exact or most meanigful dialogue from the "Transcript"

OUTPUT FORMAT:
{{
	"recap_sentence":"<sentence from Recap>",
	"dialogue":"<exact dialogue from Transcript>"
}}"""

	def single_dialogue_matcher_schema(self):
		return genai.types.Schema(
			type = genai.types.Type.OBJECT,
			required = ["dialogue", "recap_sentence"],
			properties = {
				"dialogue": genai.types.Schema(
					type = genai.types.Type.STRING,
				),
				"recap_sentence": genai.types.Schema(
					type = genai.types.Type.STRING,
				),
			},
		)

	def title_and_desc_system_prompt(self):
		return """# Social Media Content Creator

Create engaging YouTube titles and Twitter posts that get clicks and engagement.

## Output Format
```json
{
	"youtube_title": "Your title here",
	"twitter_post": "Your post here"
}
```

## YouTube Title Rules
- **Max 100 characters** (best: 60-70)
- Use casual, conversational tone
- Create curiosity without revealing everything
- **Never mention movie names** - keep them mysterious
- **Never use words**: "review", "recap", "breakdown"
- Use hooks like: "This movie changed everything", "You won't believe what happens", "The ending will shock you"
- Include emotional triggers: "shocking", "unexpected", "incredible", "mind-blowing"
- Make it YouTube algorithm friendly with searchable keywords

## Twitter Post Rules
- **Max 280 characters**
- Add 1-2 emojis
- Include 2-3 hashtags
- **Absolutely NO link references** - no "link in bio", "watch here", "check this out"
- Write complete standalone thoughts
- Ask questions to boost engagement
- Share opinions or hot takes
- Make it shareable and discussion-worthy

## Content Strategy
- **Hook immediately** - first few words matter most
- **Build curiosity** - make people want to know more
- **Stay casual** - like talking to a friend
- **Think mobile** - most people scroll on phones
- **Drive engagement** - make people want to comment/share

## Exclude
- **Never mention movie/comic/anime names** - keep them mysterious
- **Never use words**: "review", "recap", "breakdown", "analysis"

## Examples of Good Hooks
YouTube: "This plot twist broke the internet", "Nobody saw this coming", "The most underrated movie ever"
Twitter: "Hot take:", "Am I the only one who thinks...", "This needs to be said:"""

	def title_desc_user_prompt(self):
		return """Create a suitable youtube title and twitter post for the above."""

	def title_desc_schema(self):
		return genai.types.Schema(
			type = genai.types.Type.OBJECT,
			required = ["youtube_title", "twitter_post"],
			properties = {
				"youtube_title": genai.types.Schema(
					type = genai.types.Type.STRING,
				),
				"twitter_post": genai.types.Schema(
					type = genai.types.Type.STRING,
				),
			},
		)

	def title_and_desc_generator(self, history, response):
		try:
			logger_config.debug("Getting Title and description...")
			logger_config.debug(f'history:: {history}')
			geminiWrapper = pre_model_wrapper(
				system_instruction=self.title_and_desc_system_prompt(),
				schema=self.title_desc_schema(),
				history=history
			)
			model_responses = geminiWrapper.send_message(
				user_prompt=self.title_desc_user_prompt(),
			)
			title_desc = self.parse_content(model_responses[0], format=titleAndDescription.model_json_schema())
			response[0]["youtube_title"] = title_desc["youtube_title"]
			response[0]["twitter_post"] = title_desc["twitter_post"]
			return geminiWrapper
		except Exception as e:
			logger_config.warning(f'Error in title_and_desc_generator {str(e)}')

		return None


	def parse_content(self, content, is_lang_parser=False, exception_check=True, format=None):
		try:
			data = json_repair.loads(content)
			if "moments" in data:
				return data["moments"]
			else:
				return data
		except Exception as e:
			raise ValueError("LLM failed to correct the data")
	
	def _split_data(self, segments, char_len=CHAR_LEN):
		sentence = ''
		batches = []

		n = 2
		all_text = ' '.join(seg["text"] for seg in segments)
		total_len = len(all_text)

		char_len = total_len / n

		for segment in segments:
			# Check if adding the current segment will exceed the limit
			if len(sentence) + len(segment["text"]) < char_len:
				sentence += segment["text"]
			else:
				# Save the current sentence to batches and start a new one
				batches.append(sentence)
				sentence = segment["text"]

		# Add any remaining text after the loop finishes
		if sentence:
			batches.append(sentence)
		
		return batches

	def merge_audio(self, audioPath):
		return audioPath

	def match_sentence(self, recap, otherDetails):
		nlp=None
		import spacy
		try:
			nlp = spacy.load("en_core_web_sm")
		except OSError:
			from spacy.cli import download
			download("en_core_web_sm")
			nlp = spacy.load("en_core_web_sm")

		geminiWrapper = pre_model_wrapper(
			system_instruction=self.dialogue_matcher_system_prompt(otherDetails),
			schema=self.single_dialogue_matcher_schema()
		)
		new_dialogues = []
		doc = nlp(recap)

		sentence_count = sum(1 for _ in doc.sents)
		modul_n = (sentence_count // 100) + 1

		sentence = ""
		count = 0
		for sent in doc.sents:
			sentence += f"{sent.text.strip()} "
			count += 1

			if (count % modul_n != 0 or len(sentence) < 100) and count < sentence_count:
				continue

			sentence = sentence.strip()
			logger_config.info(f"Working match_sentence on sentence {count} of {sentence_count}", seconds=5)

			model_responses = geminiWrapper.send_message(
				user_prompt=self.dialogue_matcher_user_prompt(sentence, otherDetails)
			)
			for model_res in model_responses:
				local_dialog = self.parse_content(model_res, format=RecapDialogMoment.model_json_schema())
				new_dialogues.append({
					"key_moment": local_dialog["dialogue"],
					"impact": sentence
				})

			sentence = ""

		logger_config.info(new_dialogues)
		return new_dialogues

	def get_skip_segment(self, intro=True):
		return None

	def save_json_data(self, id, json_data):
		databasecon.execute(
			f"update {custom_env.TABLE_NAME} set json_data=? where id=?",
			values=(json.dumps(json_data, ensure_ascii=False), id)
		)

	def find_script_file(self, videoPath):
		base, _ = os.path.splitext(videoPath)
		txt_file = base + ".txt"
		pdf_file = base + ".pdf"

		if os.path.exists(txt_file):
			return txt_file
		elif os.path.exists(pdf_file):
			return pdf_file
		else:
			return None

	def get_key_moment(self, segments):
		if self.get_type() in [custom_env.COMIC_REVIEW, custom_env.COMIC_SHORTS]:
			google_ai_studio_key_moment = self.get_google_ai_studio_key_moment()
			if google_ai_studio_key_moment:
				return google_ai_studio_key_moment

		raise ValueError("Issue occurred in Google AI Studio")

	def get_content_for_audio(self, key_moment=None, only_content=False):
		id = self.get_db_entry()[databasecon.getId("id")]
		videoPath = self.get_db_entry()[databasecon.getId("videoPath")]
		if not key_moment:
			segments = self.get_source_data(videoPath=videoPath)
			key_moment = self.get_key_moment(segments)

		full_content = ""
		audio_files = []
		hf_tts_client = HFTTSClient()
		for i, moment in enumerate(key_moment):
			logger_config.info(f"Working get_content_for_audio {i+1} of {len(key_moment)}", overwrite=i>0)
			impact = f'{self.get_welcome_phrase()} {moment["impact"]}' if i == 0 else moment["impact"]
			impact = f'{moment["impact"]} {self.get_finish_phrase()}' if i + 1 == len(key_moment) else impact
			impact = impact.strip()
			full_content += impact
			if not only_content:
				file_name = common.generate_random_string_from_input(impact)
				final_path = f'{custom_env.REUSE_SPECIFIC_PATH}/{i+1:04d}_{file_name}.wav'

				audio_files.append(final_path)
				if common.file_exists(final_path) and not common.is_valid_wav(final_path):
					common.remove_file(final_path)
				if not common.file_exists(final_path):
					hf_tts_client.generate_audio_segment(impact, final_path)

				_, duration, _, _ = common.get_media_metadata(final_path)
				key_moment[i]['duration'] = duration
				moment['duration'] = duration

		final_output_audio = None
		if not only_content:
			databasecon.execute(f"UPDATE {custom_env.TABLE_NAME} SET answer = ?, lastModifiedTime = {int(time.time() * 1000)} WHERE id = ?", (json.dumps(key_moment, ensure_ascii=False), id))
			logger_config.info(f"Combining {len(audio_files)} audio files...")
			final_output_audio = f'{custom_env.AUDIO_PATH}/{common.generate_random_string()}.wav'
			combineAudio.start(audio_files, final_output_audio, silence=0)
			logger_config.info(f"Combined audio saved as {final_output_audio}")

		return full_content, final_output_audio

	def get_video_for_duration(self, moment, videoPath):
		duration = moment['duration']
		full_duration, _, _, _ = common.get_media_metadata(videoPath)
		start = moment["frame_second"]
		end = start + duration
		diff = abs(end-start)
		remain = abs(diff-duration)

		if remain > 0:
			if int(start - remain/2) < 0:
				end += remain
			elif int(end + remain/2) > full_duration:
				start -= remain
			else:
				start -= remain/2
				end += remain/2
		else:
			start += remain/2
			end -= remain/2

		start = max(0, start)
		end = min(full_duration, end)
		base = os.path.basename(videoPath)
		name, _ = os.path.splitext(base)
		output_path = f'{custom_env.REUSE_SPECIFIC_PATH}/{name}_{round(start, 2)}_{round(end, 2)}_2.mp4'
		clipped_path = video_clipper.clip(videoPath, start, end, output_path=output_path)

		# subprocess.run([
		#	 'ffmpeg', '-y', '-i', clipped_path,
		#	 '-an', '-c:v', 'copy', output_path
		# ], check=True)
		return clipped_path
	
	def get_audio_details(self):
		audioPath = self.get_db_entry()[databasecon.getId("audioPath")]
		transcript = self.get_description()
		segments = json.loads(self.get_db_entry()[databasecon.getId("otherDetails")])

		return audioPath, transcript, segments

	def save_to_database(self, content):

		lastModifiedTime = int(time.time() * 1000)

		lastrowid = databasecon.execute(f"""INSERT into {custom_env.TABLE_NAME} (videoPath, title, type, lastModifiedTime) VALUES (?, ?, ?, ?)""", (content['videoPath'], content['title'], self.get_type(), lastModifiedTime), type='lastrowid')

		return databasecon.execute(f"select * from {custom_env.TABLE_NAME} where id = {lastrowid}", type='get')
	
	def get_yt_category(self):
		return '1'
	
	def get_x_title(self):
		description = self.get_db_entry()[databasecon.getId('description')]
		if not description or description == 'null':
			description = ''
		return description.strip()
	
	def get_x_description(self):
		return f"""Check out for detailed breakdown {self.get_youtube_link()}"""

	def retry(self, recap, geminiWrapper, format, key):
		if len(recap) > self.get_recap_length("max") or len(recap) < self.get_recap_length("min"):
			for i in range(5):
				logger_config.debug(f"Length: {len(recap)}")
				logger_config.debug(f"Required Length min: {self.get_recap_length('min')} max: {self.get_recap_length('max')}")
				logger_config.info(f"Retrying {i}th time...")
				model_responses = geminiWrapper.send_message(
					user_prompt=f"""Please try again, duration did not met the criteria."""
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