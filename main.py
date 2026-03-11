from jebin_lib import load_env
load_env()

import gc
import time
import traceback
from custom_logger import logger_config
import custom_env
import argparse
from content_map import content_map
from content_creator import ContentCreator

class MainContent:
	create_new = False
	id = None
	source_name = None

	allowed_types = content_map.get_types()

	allowed_publish = content_map.get_publish_type()

	id_not_in = '-1'

	def __init__(self, allowed_types, allowed_publish, create_new = False, id=None, source_name=None):
		self.create_new = create_new
		if len(allowed_types) > 0:
			self.allowed_types = allowed_types

		self.allowed_publish = allowed_publish
		self.source_name = source_name
		try:
			self.id = int(id)
		except:self.id = id

		logger_config.debug(f'Starting with {self.allowed_types} create_new: {self.create_new} and publish: {self.allowed_publish}')

	def create(self, interval: int = 10):
		while True:
			self.id_not_in = "-1"
			try:
				is_success = False
				content_ref = None
				for type in self.allowed_types:
					content_ref = content_map.get_class_instance(type)(self, self.create_new)
					contentCreator = ContentCreator(content_ref)
					is_success = contentCreator.start()
					contentCreator = None
					logger_config.debug(f'skipped id {self.id_not_in}')
					gc.collect()
					logger_config.debug(f"Waiting {interval} seconds before next type of content generation", seconds=interval)
				
				content_ref = None

				if interval == 0 or (is_success and self.id):
					break

			except Exception as e:
				logger_config.error(f"Error in MainContent::create: {e}\n{traceback.format_exc()}")
				time.sleep(interval)

def parse_arguments() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="Content Generation Utility")

	# Shared args
	parser.add_argument("--id", type=str, help="Id for constraints", default=None)
	parser.add_argument("--source-name", type=str, help="source_name for constraints", default=None)
	parser.add_argument("--new-content", action="store_true", help="Create new content without audio/video")
	parser.add_argument("--headless-mode", action="store_true", help="Run in headless mode")

	# Dynamically add content type args
	for key, value in content_map.get_type_class_map().items():
		parser.add_argument(
			value["parse_arguments"],
			value["long_parse_arguments"],
			action="store_true",
			help=f"Enable {key} generation"
		)

	# Dynamically add publisher args
	for key, value in content_map.get_publish_type_class_map().items():
		parser.add_argument(
			value["parse_arguments"],
			value["long_parse_arguments"],
			action="store_true",
			help=f"Enable {key} publishing"
		)

	return parser.parse_args()

def main():
	args = parse_arguments()

	allowed_types = []
	allowed_publish = []

	# Set allowed content types
	for key, value in content_map.get_type_class_map().items():
		if getattr(args, value["long_parse_arguments"].lstrip("--").replace("-", "_")):
			allowed_types.append(key)
			if key == custom_env.COMIC_REVIEW:
				allowed_types.append(custom_env.COMIC_SHORTS)

	# Set allowed publishers
	for key, value in content_map.get_publish_type_class_map().items():
		if getattr(args, value["long_parse_arguments"].lstrip("--").replace("-", "_")):
			allowed_publish.append(key)

	if args.headless_mode:
		custom_env.HEADLESS_MODE = True

	mainContent = MainContent(allowed_types, allowed_publish, create_new=args.new_content, id=args.id, source_name=args.source_name)

	if allowed_publish:
		if args.new_content:
			while True:
				mainContent.create(0)
				if args.id == "onetime":
					break
	else:
		mainContent.create()

# main entry point
if __name__ == "__main__":
	main()