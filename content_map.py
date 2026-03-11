import importlib
import custom_env

class ContentMap:
	def __init__(self):
		# Define mapping without loading modules/classes
		self._type_class_map = {
			# Comic
			custom_env.COMIC_REVIEW: {"module": "comic_review", "class_name": "ComicReview", "parse_arguments": "-cr", "long_parse_arguments": "--comic-review"},
			custom_env.COMIC_SHORTS: {"module": "comic_shorts_review", "class_name": "ComicShortsReview", "parse_arguments": "-csr", "long_parse_arguments": "--comic-shorts"},
		}

		self._publisher_map = {
			custom_env.YOUTUBE_PUBLISHER: {"module": "youtube_publisher", "class_name": "YoutubePublisher", "parse_arguments": "-upyt", "long_parse_arguments": "--upload-yt"},
			custom_env.X_PUBLISHER: {"module": "x_publisher", "class_name": "XPublisher", "parse_arguments": "-upx", "long_parse_arguments": "--upload-x"}
		}

	def get_types(self):
		return list(self._type_class_map.keys())

	def get_type_class_map(self):
		return self._type_class_map

	def get_class_instance(self, content_type):
		mapping = self._type_class_map.get(content_type)
		if not mapping:
			raise ValueError(f"Unknown content type: {content_type}")
		module = importlib.import_module(mapping["module"])
		cls = getattr(module, mapping["class_name"])
		return cls

	def get_publish_type(self):
		return list(self._publisher_map.keys())

	def get_publish_type_class_map(self):
		return self._publisher_map

	def get_publisher_instance(self, publisher_type):
		mapping = self._publisher_map.get(publisher_type)
		if not mapping:
			raise ValueError(f"Unknown publisher type: {publisher_type}")
		module = importlib.import_module(mapping["module"])
		cls = getattr(module, mapping["class_name"])
		return cls

# ✅ Singleton shared instance
content_map = ContentMap()
