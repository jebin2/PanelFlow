"""
Comic-to-Video Pipeline
Converts comic book pages into narrated video with dynamic focus on speech bubbles.
"""

import json
from custom_logger import logger_config
from typing import List, Tuple, Optional
from dataclasses import dataclass
from panelflow.pipeline.scale_clip import create_scale_up_clip_multiple

from PIL import Image, ImageFilter

import numpy as np
from moviepy import AudioFileClip, ImageClip, VideoClip, concatenate_audioclips, concatenate_videoclips

# Custom modules
from panelflow import config
from panelflow import common
import re
import json_repair
from tqdm import tqdm
import os
from jebin_lib import HFTTSClient, HFSTTClient, utils
from caption_generator.core import MultiTypeCaptionGenerator
from chat_bot_ui_handler import GoogleAISearchChat, QwenUIChat, BingUIChat, BraveAISearch, DuckDuckGoAISearch, AIStudioUIChat, GeminiUIChat
from jebin_lib import text_splitter
from panelflow.pipeline.gemini_config import pre_model_wrapper
import difflib

@dataclass
class Config:
	"""Configuration settings for the comic-to-video pipeline."""
	comic_title: str = ""
	main_file_name: str = ""
	comic_image: str = ""
	distance_threshold: int = 70
	vertical_threshold: int = 30
	resolution: Tuple[int, int] = config.IMAGE_SIZE
	margin_ratio: float = 0.08
	auto_scroll: bool = True
	zoom_enabled: bool = False
	zoom_factor: float = 1.1
	output_video: str = f"{config.TEMP_PATH}/comic_focus.mp4"
	min_text_length: int = 2
	similarity_model: str = 'all-mpnet-base-v2'
	split_output_dir: str = '',
	pattern = re.compile(r"\d+_panel_\((\d+), (\d+), (\d+), (\d+)\)\.jpg")
	page_specific_dir: str = '', # should be parent for all
	category_obj: object = None


@dataclass
class TextDetection:
	"""Represents a detected text region."""
	bbox: List[int]
	text: str
	confidence: float
	id: Optional[int] = None


@dataclass
class NarrationMapping:
	"""Represents mapping between narration and speech bubble."""
	narration_id: int
	narration_text: str
	bubble_id: int
	bubble_text: str
	bubble_bbox: List[int]
	similarity: float
	audio: str
	duration: float
	image_path: str
	scene_caption: str = ""
	stt_json_path: str = ""


class TextDetector:
	"""Handles text detection and grouping from comic images."""
	
	def __init__(self, config: Config):
		self.config = config
		self.reader = None

	def load_ocr_model(self):
		"""Load OCR model separately."""
		if self.reader is None:
			logger_config.info("Loading EasyOCR model...")
			is_gpu = utils.is_gpu_available()
			if utils.get_device() == "cpu":
				is_gpu = False
				os.environ['CUDA_VISIBLE_DEVICES'] = ""
				os.environ['CUDA_LAUNCH_BLOCKING'] = '1'
				from torch.utils.data import DataLoader

				# Monkey patch DataLoader to disable pin_memory
				original_init = DataLoader.__init__

				def patched_init(self, *args, **kwargs):
					kwargs['pin_memory'] = False
					return original_init(self, *args, **kwargs)

				DataLoader.__init__ = patched_init
			import easyocr
			self.reader = easyocr.Reader(['en'], gpu=is_gpu)

	def cleanup_ocr_model(self):
		"""Clean up OCR model to free memory."""
		try:
			if hasattr(self, 'reader') and self.reader is not None:
				del self.reader
				self.reader = None
				# Clear any GPU memory if EasyOCR uses GPU
				utils.manage_gpu("clear_cache")
				logger_config.info("EasyOCR model cleaned up")
		except:
			pass
	
	def detect_text(self, image_path: str) -> List[TextDetection]:
		"""Detect text regions in the image."""
		self.load_ocr_model()
		results = self.reader.readtext(image_path)
		logger_config.info(f"EasyOCR found {len(results)} raw detections")
		
		detections = []
		for box, text, confidence in tqdm(results, total=len(results), desc="Detect Text"):
			bbox = [
				min(x[0] for x in box),
				min(x[1] for x in box),
				max(x[0] for x in box),
				max(x[1] for x in box)
			]
			detections.append(TextDetection(
				bbox=bbox,
				text=text.strip(),
				confidence=float(confidence)
			))
		
		return detections
	
	@staticmethod
	def calculate_distance(bbox1: List[int], bbox2: List[int]) -> float:
		"""Calculate Euclidean distance between two bounding box centers."""
		center1 = [(bbox1[0] + bbox1[2]) / 2, (bbox1[1] + bbox1[3]) / 2]
		center2 = [(bbox2[0] + bbox2[2]) / 2, (bbox2[1] + bbox2[3]) / 2]
		return np.linalg.norm(np.subtract(center1, center2))
	
	def group_text_regions(self, detections: List[TextDetection]) -> List[TextDetection]:
		"""Group nearby text regions into speech bubbles."""
		# Filter out single character detections
		filtered_detections = [
			det for det in detections 
			if len(det.text.strip()) >= self.config.min_text_length
		]
		
		# Sort by vertical position (top to bottom)
		filtered_detections.sort(key=lambda d: d.bbox[1])
		
		groups = []
		for detection in filtered_detections:
			added_to_group = False
			
			for group in groups:
				if self.calculate_distance(detection.bbox, group.bbox) < self.config.distance_threshold:
					# Merge with existing group
					group.text += " " + detection.text
					group.bbox = [
						min(group.bbox[0], detection.bbox[0]),
						min(group.bbox[1], detection.bbox[1]),
						max(group.bbox[2], detection.bbox[2]),
						max(group.bbox[3], detection.bbox[3])
					]
					added_to_group = True
					break
			
			if not added_to_group:
				groups.append(detection)
		
		# Sort groups by vertical position and assign IDs
		groups.sort(key=lambda g: g.bbox[1])
		for idx, group in enumerate(groups):
			group.id = idx + 1
		
		return groups
	
	def detect_and_group_text(self, image_path: str) -> str:
		"""Main method to detect and group text, saving results to JSON."""
		output_path = f"{self.config.page_specific_dir}/detect_and_group_text.json"
		
		try:
			with open(output_path, "r", encoding="utf-8") as f:
				groups_data = json.load(f)
		except: utils.remove_file(output_path)

		if not utils.file_exists(output_path):
			detections = self.detect_text(image_path)
			groups = self.group_text_regions(detections)
			groups_data = []
			for group in groups:
				groups_data.append({
					"id": group.id,
					"bbox": [int(x) for x in group.bbox],
					"text": group.text,
					"confidence": group.confidence
				})
			
			with open(output_path, "w", encoding="utf-8") as f:
				json.dump(groups_data, f, indent=4, ensure_ascii=False)
			
			logger_config.info(f"Grouped bubbles saved: {output_path}")
		return str(output_path)

	def cleanup(self):
		self.cleanup_ocr_model()

	def __enter__(self):
		return self

	def __exit__(self, exc_type, exc_val, exc_tb):
		self.cleanup()

	def __del__(self):
		self.cleanup()


class NarrationMapper:
	"""Maps narration text to speech bubbles using semantic similarity."""
	
	def __init__(self, config: Config):
		self.config = config
		self.model = None

	def load_similarity_model(self):
		"""Load only the sentence transformer model."""
		if self.model is None:
			from sentence_transformers import SentenceTransformer
			logger_config.info("Loading SentenceTransformer model...")
			self.model = SentenceTransformer(self.config.similarity_model, device=utils.get_device())

	def cleanup_similarity_model(self):
		"""Clean up similarity model to free CUDA memory."""
		try:
			if self.model is not None:
				del self.model
				self.model = None
				utils.manage_gpu(action="clear_cache")
				logger_config.info("SentenceTransformer model cleaned up")
		except:
			pass

	def create_narration_mappings(self, bubbles_path: str, narration_lines: List[str], caption_generator_map) -> List:
		"""Create narration mappings without generating audio."""
		output_path = f"{self.config.page_specific_dir}/map_narration_to_bubbles.json"
		try:
			# Load existing narration mappings if available
			with open(output_path, "r", encoding="utf-8") as f:
				existing_mappings = json.load(f)
				# Check if audio files exist for all mappings
				all_audio_exists = all(
					utils.is_valid_audio(mapping.get("audio", "")) and utils.is_valid_json(mapping.get("audio", "").replace(".wav", ".json")) 
					for mapping in existing_mappings
				)
				if all_audio_exists:
					return True, str(output_path)
		except:
			utils.remove_file(output_path)
		
		try:
			self.load_similarity_model()
			with open(bubbles_path, "r", encoding="utf-8") as f:
				bubbles = json.load(f)

			# Generate embeddings
			bubble_texts = [bubble["text"] for bubble in bubbles]
			use_similarity = len(bubble_texts) > 0
			if use_similarity:
				bubble_embeddings = self.model.encode(bubble_texts, convert_to_tensor=True)
				narration_embeddings = self.model.encode(narration_lines, convert_to_tensor=True)
				
				# Calculate similarity
				from sentence_transformers import util
				cosine_scores = util.cos_sim(narration_embeddings, bubble_embeddings)
			
			mappings = []
			for idx, narration in tqdm(enumerate(narration_lines), total=len(narration_lines), desc="Processing narration"):
				if use_similarity:
					# Find best matching bubble
					if idx+1 == len(narration_lines):
						best_bubble_idx = len(bubbles) - 1
					else:
						best_bubble_idx = cosine_scores[idx].argmax().item()

					similarity_score = cosine_scores[idx][best_bubble_idx].item()
				else:
					similarity_score = 0.0  # or -1 if you want to mark it clearly
				image_path = None
				
				# if similarity_score < 0.8:
				best_match = max(
					caption_generator_map,
					key=lambda obj: difflib.SequenceMatcher(None, utils.only_alpha(obj.get("recap_sentence", "")), utils.only_alpha(narration)).ratio()
				)

				image_path = best_match["frame_path"]
				if isinstance(image_path, list):
					image_path = image_path[0]

				match = self.config.pattern.match(os.path.basename(image_path))
				if match:
					panel_x1, panel_y1, panel_x2, panel_y2 = map(int, match.groups())
					matched_bubble = {
						"id": -1,
						"text": "",
						"bbox": [panel_x1, panel_y1, panel_x2, panel_y2]
					}
				# else:
				# 	matched_bubble = bubbles[best_bubble_idx]
				
				# Prepare audio path but don't generate yet
				file_name = utils.generate_random_string_from_input(narration)
				final_audio_path = f'{self.config.page_specific_dir}/{idx+1:04d}_{file_name}.wav'
				stt_json_path = f"{final_audio_path.replace('.wav', '.json')}"
				
				mapping = NarrationMapping(
					narration_id=idx + 1,
					narration_text=narration,
					bubble_id=matched_bubble["id"],
					bubble_text=matched_bubble["text"],
					bubble_bbox=matched_bubble["bbox"],
					similarity=round(similarity_score, 3),
					audio=final_audio_path,
					duration=0,  # Will be set after audio generation
					image_path=image_path,
					scene_caption=best_match.get("scene_caption", ""),
					stt_json_path=stt_json_path
				)

				# Merge consecutive identical bubble targeting into a single narration
				if mappings and mappings[-1].image_path == mapping.image_path:
					merged_text = mappings[-1].narration_text + " " + mapping.narration_text
					merged_file_name = utils.generate_random_string_from_input(merged_text)
					merged_audio = f'{self.config.page_specific_dir}/{mappings[-1].narration_id:04d}_{merged_file_name}.wav'
					mappings[-1].narration_text = merged_text
					mappings[-1].audio = merged_audio
					mappings[-1].stt_json_path = merged_audio.replace('.wav', '.json')
				else:
					mappings.append(mapping)
			
			return False, mappings

		finally:
			# Clean up similarity model to free CUDA memory
			self.cleanup_similarity_model()

	def generate_audio_for_mappings(self, mappings: List):
		"""Generate audio files for all narration mappings."""
		output_path = f"{self.config.page_specific_dir}/map_narration_to_bubbles.json"
		hf_tts_client = HFTTSClient()
		stt_client = HFSTTClient()
		for mapping in mappings:
			if not utils.is_valid_audio(mapping.audio):
				# Generate TTS audio
				hf_tts_client.generate_audio_segment(mapping.narration_text, mapping.audio)

			# Run STT to get word-level timestamps (cached as <audio>.json)
			stt_json_path = f"{mapping.audio.replace('.wav', '.json')}"
			if not utils.is_valid_json(stt_json_path):
				stt_client.transcribe(mapping.audio)

			if not utils.is_valid_audio(mapping.audio) or not utils.is_valid_json(stt_json_path):
				raise ValueError(f"Audio or STT JSON not found for mapping: {mapping}")

			# Get audio duration and update mapping
			_, duration, _, _ = common.get_media_metadata(mapping.audio)
			mapping.duration = duration

		# Step 3: Save final mappings
		mappings_data = []
		for mapping in mappings:
			d = mapping.__dict__.copy()
			d["audio"] = utils.to_rel(d["audio"], config.BASE_PATH)
			d["image_path"] = utils.to_rel(d["image_path"], config.BASE_PATH)
			d["stt_json_path"] = utils.to_rel(d["stt_json_path"], config.BASE_PATH)
			mappings_data.append(d)

		with open(output_path, "w", encoding="utf-8") as f:
			json.dump(mappings_data, f, indent=4, ensure_ascii=False)
		
		logger_config.info(f"Narration mapping saved: {output_path}")
	
		return str(output_path)

	def cleanup(self):
		"""Clean up all models."""
		self.cleanup_similarity_model()

	def __enter__(self):
		return self

	def __exit__(self, exc_type, exc_val, exc_tb):
		self.cleanup()

	def __del__(self):
		self.cleanup()


class VideoGenerator:
	"""Generates video clips with focus transitions between speech bubbles."""
	
	def __init__(self, config: Config):
		self.config = config
	
	def compute_y_offset(self, img_height: int, view_height: int, 
						bubble_coords: List[int], margin_ratio: float = 0.1) -> int:
		"""Calculate vertical offset for placing bubble in view frame."""
		x1, y1, x2, y2 = bubble_coords
		margin = int(view_height * margin_ratio)
		
		# Try to place bubble near top with margin
		offset = y1 - margin
		
		# Adjust if bubble would be cut off at bottom
		if offset + view_height > img_height:
			offset = img_height - view_height
		
		# Clamp to valid range
		return max(0, offset)

	def create_pan_zoom_clip(self, img_clip: ImageClip, start_coords: List[int], 
						   end_coords: List[int], duration: float, 
						   margin_ratio: float = 0.1, zoom_factor: float = 1.1) -> VideoClip:
		"""Create a clip that pans and zooms between speech bubbles and returns end crop box."""
		img_width, img_height = img_clip.size
		view_width, view_height = self.config.resolution
		
		start_y_offset = self.compute_y_offset(img_height, view_height, start_coords, margin_ratio)
		end_y_offset = self.compute_y_offset(img_height, view_height, end_coords, margin_ratio)
		
		def make_frame(t: float) -> np.ndarray:
			progress = t / duration  # Normalize time 0..1
			
			# Interpolate vertical position
			y_offset = int(np.interp(progress, [0, 1], [start_y_offset, end_y_offset]))
			
			# Interpolate zoom with ease in/out
			zoom = np.interp(progress, [0, 0.5, 1], [1.0, zoom_factor, 1.0])
			
			# Calculate crop dimensions
			crop_width = int(view_width / zoom)
			crop_height = int(view_height / zoom)
			
			x1 = max(0, (img_width - crop_width) // 2)
			y1_crop = max(y_offset + (view_height - crop_height) // 2, 0)
			
			# Crop and resize
			frame = img_clip.cropped(
				x1=x1,
				y1=y1_crop,
				x2=x1 + crop_width,
				y2=y1_crop + crop_height
			)
			return frame.resized((view_width, view_height)).get_frame(t)

		# Calculate the end crop box for chaining
		final_crop_box = [
			max(0, (img_width - int(view_width / zoom_factor)) // 2),
			max(end_y_offset + (view_height - int(view_height / zoom_factor)) // 2, 0),
			min(img_width, (img_width + int(view_width / zoom_factor)) // 2),
			min(img_height, end_y_offset + (view_height + int(view_height / zoom_factor)) // 2)
		]
		
		return VideoClip(make_frame, duration=duration), final_crop_box

	def is_image_within_resolution(self, image_path, size, tolerance=200):
		"""Allow panel images slightly larger than resolution."""
		img = Image.open(image_path)
		width, height = img.size
		target_w, target_h = size

		# Allow tolerance for panels slightly larger
		return (width <= target_w + tolerance) and (height <= target_h + tolerance + 1000)

	def find_matching_panel(self, bubble_bbox, image_path=None):
		"""Find the panel file in output_folder whose coordinates contain or overlap with bubble_bbox."""
		if image_path:
			return image_path

		output_folder = self.config.split_output_dir
		bubble_x1, bubble_y1, bubble_x2, bubble_y2 = bubble_bbox

		for filename in os.listdir(output_folder):
			match = self.config.pattern.match(filename)
			if match:
				image_path = os.path.join(output_folder, filename)
				if self.is_image_within_resolution(image_path, size=self.config.resolution):
					panel_x1, panel_y1, panel_x2, panel_y2 = map(int, match.groups())
					tolerance = 200  # Allow 20px leeway on all sides

					# Expand panel bbox by tolerance
					panel_x1 -= tolerance
					panel_y1 -= tolerance
					panel_x2 += tolerance
					panel_y2 += tolerance
					print(f"Checking panel: {(panel_x1, panel_y1, panel_x2, panel_y2)} against bubble: {bubble_bbox}")

					# Check if bubble bbox is fully inside panel bbox
					if (panel_x1 <= bubble_x1 <= panel_x2 and
						panel_y1 <= bubble_y1 <= panel_y2 and
						panel_x1 <= bubble_x2 <= panel_x2 and
						panel_y1 <= bubble_y2 <= panel_y2):
						return image_path

					# OPTIONAL: If you want to check for any overlap instead of fully inside
					if not (bubble_x2 < panel_x1 or bubble_x1 > panel_x2 or
						bubble_y2 < panel_y1 or bubble_y1 > panel_y2):
						return image_path

		logger_config.warning(f"No Match Found:: {bubble_bbox}")
		return None

	def add_remaining_panel(self, final_mapping):
		# Step 1: get all panel frame paths
		all_frame_paths = [
			utils.to_abs(file, config.BASE_PATH)
			for file in utils.list_files(self.config.split_output_dir)
			if "_panel_" in os.path.basename(file)
		]

		# Step 2: load all captions json
		all_captions_path = f"{self.config.page_specific_dir}/all_captions.json"
		if not os.path.exists(all_captions_path):
			print(f"⚠️ Missing captions file: {all_captions_path}")
			return final_mapping

		with open(all_captions_path, "r", encoding="utf-8") as f:
			all_captions = json.load(f)

		# Step 3: build lookup for frame -> caption
		frame_to_caption = {
			c["frame_path"]: c
			for c in all_captions
		}

		# Step 4: collect already used frames
		used_frames = set()
		for entry in final_mapping:
			if "image_path" in entry:
				used_frames.add(entry["image_path"])
			if "all_image_path" in entry:
				if isinstance(entry["all_image_path"], list):
					used_frames.update(entry["all_image_path"])
				else:
					used_frames.add(entry["all_image_path"])

		# Step 5: process remaining frames
		remaining_frames = [f for f in all_frame_paths if f not in used_frames]

		for frame in remaining_frames:
			caption_entry = frame_to_caption.get(frame)
			if not caption_entry:
				continue

			caption_text = caption_entry.get("caption", "")

			# Step 6: find best matching final_mapping bubble_text
			best_match = None
			best_score = 0
			for mapping in final_mapping:
				bubble_text = mapping.get("bubble_text", "")
				if not bubble_text:
					continue

				# similarity score
				score = difflib.SequenceMatcher(None, caption_text, bubble_text).ratio()
				if score > best_score:
					best_score = score
					best_match = mapping

			# Step 7: append frame to the best match
			if best_match:
				if "all_image_path" not in best_match or not isinstance(best_match["all_image_path"], list):
					best_match["all_image_path"] = [best_match.get("all_image_path")] if best_match.get("all_image_path") else []
				best_match["all_image_path"].append(frame)
				logger_config.info(f"✅ Adding remaining panel: {frame} -> {best_match}")

		return final_mapping

	def generate_comic_video(self, mapping_path: str, output_path: Optional[str] = None) -> str:
		"""Generate the final comic video with narration and focus transitions."""
		if output_path is None:
			output_path = self.config.output_video

		# Load narration mappings
		with open(mapping_path, "r", encoding="utf-8") as f:
			narration_mapping = json.load(f)

		# STEP 1: First resolve the correct panel image path for each narration entry
		for entry in narration_mapping:
			coords = entry["bubble_bbox"]
			image_path = entry["image_path"]
			entry["image_path"] = self.find_matching_panel(coords, image_path)

		# STEP 2: Deduplicate consecutive entries with same text and resolved image path
		deduped_mapping = []
		i = 0
		while i < len(narration_mapping):
			current_entry = narration_mapping[i]
			image_path = current_entry["image_path"]
			bubble_text = current_entry["bubble_text"]
			coords = current_entry["bubble_bbox"]

			combined_duration = current_entry["duration"]
			combined_audio = [AudioFileClip(current_entry["audio"])]

			j = i + 1
			while j < len(narration_mapping):
				next_entry = narration_mapping[j]
				if (next_entry["bubble_text"] == bubble_text and 
					next_entry["image_path"] == image_path):
					combined_duration += next_entry["duration"]
					combined_audio.append(AudioFileClip(next_entry["audio"]))
					j += 1
				else:
					break

			# Concatenate audio clips
			merged_audio_clip = concatenate_audioclips(combined_audio)

			deduped_mapping.append({
				"bubble_bbox": coords,
				"duration": combined_duration,
				"audio_clip": merged_audio_clip,
				"bubble_text": bubble_text,
				"image_path": image_path
			})

			i = j  # Skip to next unique entry

		logger_config.info(f"Deduplicated {len(narration_mapping)} entries to {len(deduped_mapping)} entries")

		# STEP 2: Merge entries with duration 2 seconds
		final_mapping = []
		i = 0
		while i < len(deduped_mapping):
			current_entry = deduped_mapping[i]
			combined_duration = current_entry["duration"]
			combined_audio = [current_entry["audio_clip"]]
			coords = current_entry["bubble_bbox"]
			image_path = current_entry["image_path"]
			bubble_text = current_entry["bubble_text"]
			all_image_path = [image_path] if image_path else []

			# Keep merging next entries until combined_duration >= 2
			j = i + 1
			while combined_duration < 2 and j < len(deduped_mapping):
				combined_duration += deduped_mapping[j]["duration"]
				combined_audio.append(deduped_mapping[j]["audio_clip"])
				if deduped_mapping[j]["image_path"]:
					all_image_path.append(deduped_mapping[j]["image_path"])
				j += 1

			# Concatenate audio
			merged_audio_clip = concatenate_audioclips(combined_audio)

			final_mapping.append({
				"bubble_bbox": coords,
				"duration": combined_duration,
				"audio_clip": merged_audio_clip,
				"bubble_text": bubble_text,
				"image_path": image_path,
				"all_image_path": all_image_path
			})

			i = j  # Move to next distinct entry

		logger_config.info(f"✅ Merged short entries to {len(final_mapping)} entries")

		# STEP 3: Merge backwards if last entry is still < 2 seconds
		if len(final_mapping) >= 2 and final_mapping[-1]["duration"] < 2:
			logger_config.info("⚠️ Last entry < 2s, merging backwards with previous entry.")
			# Pop last two entries
			last_entry = final_mapping.pop()
			second_last_entry = final_mapping.pop()

			# Merge them
			merged_duration = second_last_entry["duration"] + last_entry["duration"]
			all_image_path = second_last_entry["all_image_path"] + last_entry["all_image_path"]
			merged_audio = concatenate_audioclips([second_last_entry["audio_clip"], last_entry["audio_clip"]])

			# Keep coordinates of the first entry
			final_mapping.append({
				"bubble_bbox": second_last_entry["bubble_bbox"],
				"duration": merged_duration,
				"audio_clip": merged_audio,
				"bubble_text": second_last_entry["bubble_text"],
				"image_path": second_last_entry["image_path"],
				"all_image_path": all_image_path
			})

		logger_config.info(f"✅ Merged final short entries to {len(final_mapping)} entries")

		# STEP 3a: Adding remaining panel
		final_mapping = self.add_remaining_panel(final_mapping)

		# STEP 4: Generate video clips
		clips = []
		previous_end_coords = []
		print(json.dumps(final_mapping, indent=4, default=common.safe_json))
		for i, entry in enumerate(final_mapping):
			coords = entry["bubble_bbox"]
			duration = entry["duration"]
			audio_clip = entry["audio_clip"]
			image_path = entry["image_path"]
			all_image_path = entry["all_image_path"]

			if i == 0:
				previous_end_coords = coords

			if image_path is None:
				logger_config.info(f'No matching panel found for entry {i}')
				image_path = self.config.comic_image
			else:
				logger_config.info(f'Found matching panel:: {image_path}')

			temp_width, temp_height = ImageClip(image_path).size

			zoom_coordinates = {
				0: (0, 0, temp_width, temp_height)
			}

			clip = create_scale_up_clip_multiple(
				main_image_path=image_path,
				multiple_image_path=all_image_path,
				duration=duration,
				bg_size=self.config.resolution,
				zoom_coords=zoom_coordinates,
				temp_folder=self.config.page_specific_dir
			)

			previous_end_coords = coords

			# Attach merged audio
			clip = clip.with_audio(audio_clip)
			clips.append(clip)

		# Combine all clips
		final_video = concatenate_videoclips(clips, method="compose")
		utils.write_videofile(final_video, output_path)

		logger_config.info(f"Video saved to {output_path}")
		return output_path

class ComicVideoPipeline:
	"""Main pipeline orchestrator for comic-to-video conversion."""
	
	def __init__(self, config: Config):
		self.config = config
		self.video_generator = VideoGenerator(config)
		
		utils.create_directory(self.config.page_specific_dir)

	def caption_generator(self, narration_text):
		output_path = f"{self.config.page_specific_dir}/caption_generator.json"

		captionGen = MultiTypeCaptionGenerator(frame_base_path=config.BASE_PATH, cache_path=self.config.page_specific_dir, sources=[GoogleAISearchChat, QwenUIChat, BingUIChat, BraveAISearch, DuckDuckGoAISearch], FYI=self.config.category_obj.get_fyi(self.config.comic_title))

		if utils.file_exists(output_path) and utils.is_valid_json(output_path):
			with open(output_path, "r", encoding="utf-8") as f:
				frame_paths = json.load(f)
		else:
			frame_paths = [
				{
					"frame_path": [file]
				}
				for file in utils.list_files(self.config.split_output_dir)
				if "_panel_" in os.path.basename(file)
			]

		captions = captionGen.caption_generation(
			frame_paths
		)

		if len([extract_scene for extract_scene in captions if extract_scene.get("scene_caption") is None or str(extract_scene.get("scene_caption", "")).strip() == ""]) > 0:
			raise Exception(f"Failed to generate captions for {self.config.main_file_name}")
		else:
			with open(output_path, "w", encoding="utf-8") as f:
				json.dump(captions, f, indent=4, ensure_ascii=False)
			return captions
	
	def process_narration_text(self, narration_text: str) -> List[str]:
		"""Process narration text into individual lines."""
		sentences = text_splitter.split(narration_text)
		return sentences

	def _only_scene_caption_dialogue(self, caption_generator_map):
		return [
			{
				"scene_caption": obj.get("scene_caption", ""),
				"scene_dialogue": obj.get("scene_dialogue", "")
			}
			for obj in caption_generator_map
		]

	def _match_scene_schema(self):
		from google import genai
		return genai.types.Schema(
			type = genai.types.Type.OBJECT,
			required = ["data"],
			properties = {
				"data": genai.types.Schema(
					type = genai.types.Type.ARRAY,
					items = genai.types.Schema(
						type = genai.types.Type.OBJECT,
						required = ["scene_caption", "recap_sentence"],
						properties = {
							"scene_caption": genai.types.Schema(
								type = genai.types.Type.STRING,
							),
							"recap_sentence": genai.types.Schema(
								type = genai.types.Type.STRING,
							),
						},
					),
				),
			},
		)

	def match_scene_caption_to_narration(self, caption_generator_map, narration_lines):
		output_path = f"{self.config.page_specific_dir}/caption_generator.json"
		recap_caption_match_path = f"{self.config.page_specific_dir}/recap_caption_match.json"

		# Fast path: if recap_caption_match.json already has N resolved entries, skip all LLM calls.
		if utils.is_valid_json(recap_caption_match_path):
			with open(recap_caption_match_path, "r", encoding="utf-8") as f:
				narration_caption_map = json.load(f)
			if len(narration_caption_map) >= len(narration_lines):
				logger_config.info(f"recap_caption_match.json loaded ({len(narration_caption_map)} entries), skipping scene matching.")
				return caption_generator_map, narration_caption_map
			else:
				logger_config.info("recap_caption_match.json has fewer entries than narration lines, regenerating...")
				utils.remove_file(recap_caption_match_path)

		match_scene = None
		retry_times = 0
		chat_source = [AIStudioUIChat, GeminiUIChat]
		while match_scene is None and retry_times < 5:
			retry_times += 1
			# first check for reponses in a file
			if utils.file_exists(f"{self.config.page_specific_dir}/match_scene.txt"):
				with open(f"{self.config.page_specific_dir}/match_scene.txt", "r", encoding="utf-8") as f:
					match_scene = f.read()

			if not match_scene:
				user_prompt = f"""Scene Captions:: {self._only_scene_caption_dialogue(caption_generator_map)}\nRecap Sentences:: {narration_lines}"""

				with open(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "panelflow", "prompt", "scene_matching_system_prompt_dup.md"), "r") as f:
					system_prompt = f.read()

				logger_config.info("Scene Matching")
				baseUIChat = chat_source[retry_times % len(chat_source)]()
				match_scene = baseUIChat.quick_chat(
					user_prompt=user_prompt,
					system_prompt=system_prompt
				)

				# save the response in a txt file so that we can reuse it
				with open(f"{self.config.page_specific_dir}/match_scene.txt", "w", encoding="utf-8") as f:
					f.write(match_scene)

			with open(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "panelflow", "prompt", "json_validator_system_prompt.md"), "r") as f:
				system_prompt = f.read()

			logger_config.info("JSON Validator")
			# Sanitize surrogate characters that can't be encoded to UTF-8.
			# Use surrogatepass→replace pattern which reliably strips lone surrogates.
			if isinstance(match_scene, str):
				match_scene = match_scene.encode('utf-8', errors='surrogatepass').decode('utf-8', errors='replace')

			# Try direct JSON parse first (no AI needed)
			validated_scene = None
			try:
				validated_scene = utils.parse_json(match_scene, schema={
					"type": list,
					"items": {"required": ["scene_caption", "recap_sentence"]},
				})
			except Exception:
				pass

			if validated_scene is not None:
				match_scene = validated_scene
			else:
				try:
					# Fall back to AI JSON validation
					geminiWrapper = pre_model_wrapper(
						model_name=config.MODEL_NAME_LITE,
						system_instruction=system_prompt,
						schema=self._match_scene_schema(),
						delete_files=True
					)
					model_responses = geminiWrapper.send_message(
						user_prompt=match_scene
					)
					match_scene = json_repair.loads(model_responses[0])["data"]
					all_recap = [sent["recap_sentence"] for sent in match_scene]
					all_recap[len(narration_lines) - 1]
				except Exception as e:
					logger_config.error(f"Sentence not similar retry: {e}")
					match_scene = None
					utils.remove_file(f"{self.config.page_specific_dir}/match_scene.txt")

		if match_scene is None:
			utils.remove_file(f"{self.config.page_specific_dir}/match_scene.txt")
			raise ValueError("Failed to generate match scene")

		for ms_entry in match_scene:
			best_panel = max(
				caption_generator_map,
				key=lambda obj: difflib.SequenceMatcher(None, utils.only_alpha(obj.get("scene_caption", "")), utils.only_alpha(ms_entry.get("scene_caption", ""))).ratio()
			)
			ms_entry["frame_path"] = best_panel["frame_path"]

		with open(recap_caption_match_path, "w", encoding="utf-8") as f:
			json.dump(match_scene, f, indent=4, ensure_ascii=False)

		return caption_generator_map, match_scene

	def pick_panel_animations(self, mapping_path: str, page_size: tuple) -> list:
		"""Use LLM to assign a per-panel animation type for the Remotion render."""
		output_path = f"{self.config.page_specific_dir}/panel_animations.json"

		with open(mapping_path, "r", encoding="utf-8") as f:
			panels = json.load(f)

		# Fast path: valid cache with same panel count
		if utils.is_valid_json(output_path):
			with open(output_path, "r", encoding="utf-8") as f:
				cached = json.load(f)
			if isinstance(cached, list): #and len(cached) == len(panels):
				logger_config.info(f"panel_animations.json loaded ({len(cached)} panels), skipping LLM.")
				return cached

		page_w, page_h = page_size
		llm_panels = []
		for i, p in enumerate(panels):
			entry = {
				"panel_index": i,
				"narration_text": p.get("narration_text", ""),
				"scene_caption": p.get("scene_caption", ""),
				"duration_seconds": p.get("duration", 0),
				"bubble_bbox": p.get("bubble_bbox", []),
			}
			# Include word-level timestamps from STT if available
			audio_path = p.get("audio", "")
			stt_json_path = audio_path.replace(".wav", ".json") if audio_path else ""
			if utils.is_valid_json(stt_json_path):
				with open(stt_json_path, "r", encoding="utf-8") as f:
					stt_data = json.load(f)
				# Structure: segments.word = [{word, start, end, ...}, ...]
				words = stt_data.get("segments", {}).get("word", [])
				entry["words"] = [{"word": w["word"], "start": w["start"], "end": w["end"]} for w in words]
			llm_panels.append(entry)

		user_prompt = json.dumps({
			"comic_name": self.config.comic_title,
			"page_number": int(os.path.basename(self.config.page_specific_dir)),
			"page_size": {"width": page_w, "height": page_h},
			"panels": llm_panels,
		}, indent=2, ensure_ascii=False)

		with open(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "panelflow", "prompt", "panel_animation_system_prompt.md"), "r") as f:
			system_prompt = f.read()

		logger_config.info("Stage 4.5: Picking per-panel animations...")

		retry_times = 0
		chat_source = [AIStudioUIChat, GeminiUIChat]
		parsed = None
		while parsed is None and retry_times < 5:
			try:
				retry_times += 1
				baseUIChat = chat_source[retry_times % len(chat_source)]()
				response = baseUIChat.quick_chat(
					user_prompt=user_prompt,
					system_prompt=system_prompt
				)

				if isinstance(response, str):
					response = response.encode('utf-8', errors='surrogatepass').decode('utf-8', errors='replace')

				parsed = utils.parse_json(response, schema={
					"type": dict,
					"required": ["panels"],
				})
				if not parsed:
					parsed = json_repair.loads(response)
			except Exception as e:
				logger_config.error(f"Failed to parse response: {e}")
				parsed = None

		if parsed is None:
			raise ValueError("Failed to get panel animations after retries")
		animations = parsed.get("panels")

		if len(animations) != len(panels):
			raise ValueError("Animation count mismatch")

		with open(output_path, "w", encoding="utf-8") as f:
			json.dump(animations, f, indent=4, ensure_ascii=False)

		logger_config.info(f"Panel animations saved: {[a.get('animation') for a in animations]}")
		return animations

	def generate_remotion_manifest(self, mapping_path: str, panel_animations: list) -> str:
		"""Generate the remotion_manifest.json to be consumed by Remotion for video rendering."""
		output_path = f"{self.config.page_specific_dir}/remotion_manifest.json"

		with open(mapping_path, "r", encoding="utf-8") as f:
			panels = json.load(f)

		# Build animation + events + transition lookup by panel_index
		anim_by_index = {a["panel_index"]: a.get("animation", "ken_burns") for a in panel_animations}
		events_by_index = {a["panel_index"]: a.get("events", []) for a in panel_animations}
		transition_by_index = {a["panel_index"]: a.get("transitionIn", "none") for a in panel_animations}

		width, height = self.config.resolution
		TRANSITION_DURATION = 18 / config.FPS
		panel_data = []
		for i, p in enumerate(panels):
			audio_path = p.get("audio", "")
			base_duration = p.get("duration", 0)

			next_transition_in = transition_by_index.get(i + 1, "none") if (i + 1) < len(panels) else "none"
			final_duration = base_duration
			if next_transition_in != "none":
				final_duration += TRANSITION_DURATION

			entry = {
				"imageSrc": "render_assets/" + utils.to_rel(p["image_path"], config.BASE_PATH) if p.get("image_path") else None,
				"audioSrc": "render_assets/" + utils.to_rel(audio_path, config.BASE_PATH) if audio_path else None,
				"originalWidth": Image.open(p["image_path"]).width if p.get("image_path") else 0,
				"originalHeight": Image.open(p["image_path"]).height if p.get("image_path") else 0,
				"durationInSeconds": final_duration,
				"bubbleBbox": p.get("bubble_bbox", []),
				"narrationText": p.get("narration_text", ""),
				"sceneCaption": p.get("scene_caption", ""),
				"animation": anim_by_index.get(i, "ken_burns"),
				"transitionIn": transition_by_index.get(i, "none") if i > 0 else "none",
				"events": [
					e for e in events_by_index.get(i, [])
					if e.get("startSeconds", 0) < p.get("duration", 0)
				],
			}
			panel_data.append(entry)

		manifest = {
			"fps": config.FPS,
			"width": width,
			"height": height,
			"comicTitle": self.config.comic_title,
			"pageNumber": int(os.path.basename(self.config.page_specific_dir)),
			"panels": panel_data,
		}

		with open(output_path, "w", encoding="utf-8") as f:
			json.dump({"manifest": manifest}, f, indent=4, ensure_ascii=False)

		logger_config.info(f"Remotion manifest saved: {output_path}")
		return output_path

	def _ensure_remotion_ready(self, remotion_dir: str):
		"""Ensure npm dependencies are installed in the remotion-comic directory."""
		import subprocess
		node_modules = os.path.join(remotion_dir, "node_modules")
		if not os.path.isdir(node_modules):
			logger_config.info("Remotion node_modules not found — running npm install...")
			result = subprocess.run(["npm", "install"], cwd=remotion_dir, capture_output=False)
			if result.returncode != 0:
				raise RuntimeError("npm install failed for remotion-comic")
			logger_config.info("npm install complete.")
		else:
			logger_config.info("Remotion dependencies already installed.")

	def render_with_remotion(self, manifest_path: str) -> str:
		"""Invoke Remotion CLI to render the video using the manifest."""
		import subprocess

		remotion_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "remotion-comic")
		output_path = self.config.output_video

		self._ensure_remotion_ready(remotion_dir)

		# Create a symlink inside remotion-comic/public/ pointing to the page assets dir.
		# React components use staticFile("render_assets/...") to reference these files.
		public_dir = os.path.join(remotion_dir, "public")
		os.makedirs(public_dir, exist_ok=True)
		render_link = os.path.join(public_dir, "render_assets")
		if os.path.islink(render_link):
			os.unlink(render_link)
		os.symlink(utils.to_abs(config.BASE_PATH, config.BASE_PATH), render_link)
		logger_config.info(f"Symlinked render_assets -> {utils.to_abs(config.BASE_PATH, config.BASE_PATH)} to {render_link}")

		cmd = [
			"npx", "remotion", "render", "ComicVideo",
			"--props", utils.to_abs(manifest_path, config.BASE_PATH),
			"--output", utils.to_abs(output_path, config.BASE_PATH),
			"--codec", "h264",
			"--log", "verbose",
		]

		logger_config.info(f"Running Remotion: {' '.join(cmd)}")
		try:
			result = subprocess.run(cmd, cwd=remotion_dir, capture_output=False)
		finally:
			if os.path.islink(render_link):
				os.unlink(render_link)
				logger_config.info("Cleaned up render_assets symlink.")

		if result.returncode != 0:
			raise RuntimeError(f"Remotion render failed with exit code {result.returncode}")

		logger_config.info(f"Remotion render complete: {output_path}")
		return output_path

	def run(self, narration_text: str) -> str:
		"""Run the complete pipeline."""
		logger_config.info("Starting Comic-to-Video Pipeline...")
		
		# Stage 1: Text detection and grouping
		logger_config.info("Stage 1: Detecting and grouping text...")
		with TextDetector(self.config) as text_detector:
			bubbles_path = text_detector.detect_and_group_text(self.config.comic_image)

		logger_config.info("Stage 2: Generating Caption...")
		caption_generator_map = self.caption_generator(narration_text)

		# Stage 3: Narration processing
		logger_config.info("Stage 3: Processing narration text...")
		narration_lines = self.process_narration_text(narration_text)

		# stage 3.5: match scene caption to narration
		caption_generator_map, narration_caption_map = self.match_scene_caption_to_narration(caption_generator_map, narration_lines)

		# Stage 4: Narration mapping
		logger_config.info("Stage 4: Mapping narration to bubbles...")
		with NarrationMapper(self.config) as narration_mapper:
			is_path, mappings = narration_mapper.create_narration_mappings(
				bubbles_path, narration_lines, narration_caption_map
			)
		if is_path:
			mapping_path = mappings
		else:
			with NarrationMapper(self.config) as narration_mapper:
				mapping_path = narration_mapper.generate_audio_for_mappings(
					mappings
				)
		
		# Stage 4.5: Pick per-panel animations
		panel_animations = self.pick_panel_animations(mapping_path, self.config.resolution)

		# Stage 4.6: Generate Remotion manifest
		manifest_path = self.generate_remotion_manifest(mapping_path, panel_animations)

		# Stage 5: Render video via Remotion
		logger_config.info("Stage 5: Rendering video via Remotion...")
		output_path = self.render_with_remotion(manifest_path)
		
		logger_config.info(f"Comic video pipeline completed! Output: {output_path}")
		return output_path


def generate_intro_video(image_path: str, audio_path: str, duration: float, cvp_config: Config, content_bbox: list = None) -> str:
	"""Generate the Remotion intro video with 'assemble' animation."""
	pipeline = ComicVideoPipeline(cvp_config)
	output_path = f"{cvp_config.page_specific_dir}/remotion_manifest.json"

	width, height = cvp_config.resolution

	manifest = {
		"fps": config.FPS,
		"width": width,
		"height": height,
		"comicTitle": cvp_config.comic_title,
		"pageNumber": 1,
		"panels": [
			{
				"imageSrc": f"render_assets/{utils.to_rel(image_path, config.BASE_PATH)}",
				"originalWidth": Image.open(image_path).width,
				"originalHeight": Image.open(image_path).height,
				"audioSrc": f"render_assets/{utils.to_rel(audio_path, config.BASE_PATH)}",
				"durationInSeconds": duration,
				"bubbleBbox": content_bbox if content_bbox else [0, 0, width, height],
				"narrationText": "",
				"sceneCaption": "",
				"animation": "assemble",
				"transitionIn": "none",
				"events": []
			}
		]
	}

	with open(output_path, "w", encoding="utf-8") as f:
		json.dump({"manifest": manifest}, f, indent=4, ensure_ascii=False)

	return pipeline.render_with_remotion(output_path)


def generate_three_part_build_up(image_path: str, audio_path: str, duration: float, cvp_config: Config, content_bbox: list = None) -> str:
	"""Generate the Remotion video with 'three_part_build_up' animation."""
	pipeline = ComicVideoPipeline(cvp_config)
	output_path = f"{cvp_config.page_specific_dir}/remotion_manifest.json"

	width, height = cvp_config.resolution

	manifest = {
		"fps": config.FPS,
		"width": width,
		"height": height,
		"comicTitle": cvp_config.comic_title,
		"pageNumber": 1,
		"panels": [
			{
				"imageSrc": f"render_assets/{utils.to_rel(image_path, config.BASE_PATH)}",
				"originalWidth": Image.open(image_path).width,
				"originalHeight": Image.open(image_path).height,
				"audioSrc": f"render_assets/{utils.to_rel(audio_path, config.BASE_PATH)}",
				"durationInSeconds": duration,
				"bubbleBbox": content_bbox if content_bbox else [0, 0, width, height],
				"narrationText": "",
				"sceneCaption": "",
				"animation": "three_part_build_up",
				"transitionIn": "none",
				"events": []
			}
		]
	}

	with open(output_path, "w", encoding="utf-8") as f:
		json.dump({"manifest": manifest}, f, indent=4, ensure_ascii=False)

	return pipeline.render_with_remotion(output_path)


def main(narration_text, config):
	"""Main execution function."""

	# Run pipeline
	pipeline = ComicVideoPipeline(config)
	output_video = pipeline.run(narration_text)
	
	# Final cleanup
	utils.manage_gpu("clear_cache")
	
	print(f"\n🎬 Comic video generated: {output_video}\n")
	return output_video


if __name__ == "__main__":
	narration_text = """Now, in New York City. It was over for us the day you tried to convince me the devil was a man. A once beautiful creature who fell from grace. I laughed at your unwavering faith. The devil was senseless murder, prejudice, and genocide; abuse, rape. The evils men do and get away with. But that day, when my face was covered in blood, and he looked at me with the power of life and death in his hands, and the face of every terrible thing in the world. I realized that every one of us had a personal devil. A voice cuts through the din, raspy and grating: 'I told you! It's her! It's...' 'But you never listen, Al--' A sickening crunch cuts her off. 'This one is mine,' I growl. 'I'm going to end him.' After I punish him… 'Hnh-ha, ha-hahaha-ha!'"""
	main(narration_text)
