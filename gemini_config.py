from custom_logger import logger_config
import os

pre_model_wrapper=None
try:
	from functools import partial
	from gemiwrap import GeminiWrapper
	from gemiwrap.utils import compress_video as geminiwrap_compress_video
	import custom_env

	pre_model_wrapper = partial(GeminiWrapper, model_name=custom_env.MODEL_NAME)

	def compress(
		input_path
	):
		# Step 1: Compress the video
		compressed_path = geminiwrap_compress_video(
			input_path=input_path
		)

		# Ensure compression succeeded
		if not compressed_path or not os.path.exists(compressed_path):
			raise RuntimeError(f"Compression failed: {compressed_path}")

		return compressed_path


except:
	logger_config.warning("Gemini Wrapper is not initialised.")