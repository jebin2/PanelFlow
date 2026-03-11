from content_generator import ContentGenerator
from content_processor import ContentProcessor
from custom_logger import logger_config
import traceback

class ContentCreator:
    type_instance = None

    def __init__(self, type_instance):
        self.type_instance = type_instance
    
    def start(self):
        try:
            if self.type_instance.per_day_limit_exceeded():
                logger_config.warning(f'Per day limit exceeded for {self.type_instance.get_type()}')
                return False

            db_entry = None
            if self.type_instance.allowed_to_create_new_content():
                contentGenerator = ContentGenerator(self.type_instance)
                db_entry = contentGenerator.get_new_content()
            else:
                logger_config.warning(f'Not allowed to create content for {self.type_instance.get_type()}')

            logger_config.info(f"Processing {'Old' if db_entry == None else 'New'} Content...")
            contentProcessor = ContentProcessor(self.type_instance)
            return contentProcessor.process_content(db_entry)

        except Exception as e:
            if isinstance(e, Warning):
                logger_config.warning(f"{e}")
            else:
                logger_config.error(f"Error in ContentCreator::start : {e}\n{traceback.format_exc()}")
            return False