from jebin_lib import load_env
load_env()

import gc
import time
import traceback
from custom_logger import logger_config
from panelflow import config as custom_env
import argparse
from panelflow.categories.content_map import content_map
from panelflow.content_creator import ContentCreator

class MainContent:
	create_new = False

	allowed_types = content_map.get_types()

	def __init__(self, allowed_types, create_new = False):
		self.create_new = create_new
		if len(allowed_types) > 0:
			self.allowed_types = allowed_types

		logger_config.debug(f'Starting with {self.allowed_types} create_new: {self.create_new}')

	def create(self, interval: int = 10):
		while True:
			try:
				is_success = False
				content_ref = None
				for type in self.allowed_types:
					content_ref = content_map.get_class_instance(type)(self.create_new)
					contentCreator = ContentCreator(content_ref)
					is_success = contentCreator.start()
					contentCreator = None
					gc.collect()
					logger_config.debug(f"Waiting {interval} seconds before next type of content generation", seconds=interval)
				
				content_ref = None

				if interval == 0 or (is_success):
					break

			except Exception as e:
				logger_config.error(f"Error in MainContent::create: {e}\n{traceback.format_exc()}")
				time.sleep(interval)

def parse_arguments() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="Content Generation Utility")

	# Shared args
	parser.add_argument("--new-content", action="store_true", help="Create new content without audio/video")

	# Dynamically add content type args
	for key, value in content_map.get_type_class_map().items():
		parser.add_argument(
			value["parse_arguments"],
			value["long_parse_arguments"],
			action="store_true",
			help=f"Enable {key} generation"
		)

	return parser.parse_args()

def main():
	args = parse_arguments()

	allowed_types = []

	# Set allowed content types
	for key, value in content_map.get_type_class_map().items():
		if getattr(args, value["long_parse_arguments"].lstrip("--").replace("-", "_")):
			allowed_types.append(key)
			if key == custom_env.COMIC_REVIEW:
				allowed_types.append(custom_env.COMIC_SHORTS)

	mainContent = MainContent(allowed_types, create_new=args.new_content)
	mainContent.create()

# main entry point
if __name__ == "__main__":
	main()