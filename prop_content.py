import databasecon
import custom_env
import json
from custom_logger import logger_config
import common
import time
from datetime import datetime, timedelta

class PropContent:

    def __init__(self, main_instance=None, create_new=False, db_entry=None):
        self.main_instance = main_instance
        self.create_new = create_new
        self._current_db_entry = db_entry

    def allowed_to_create_new_content(self):
        return self.create_new

    def per_day_limit_exceeded(self):
        today_start_ms = int(datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000)
        db_entry = databasecon.execute(f"""SELECT * FROM {custom_env.TABLE_NAME} WHERE type = '{self.get_type()}' AND lastModifiedTime >= {today_start_ms} and video_processed = 1""", type="get")
        return db_entry is not None

    def allowed_to_publish_in_yt(self):
        return True

    def allowed_to_publish_in_x(self):
        return True

    def is_audio_allowed(self):
        return True

    def is_audio_creation_allowed(self):
        return True

    def add_bg_music(self):
        try:
            json_data = json.loads(self.get_db_entry()[databasecon.getId("json_data")])
            return not "add_bg_music" in json_data
        except: pass
        return True

    def is_video_allowed(self):
        return True

    def content_sequence(self):
        return [
            [custom_env.COMIC_REVIEW, custom_env.COMIC_SHORTS],
            [custom_env.COMIC_REVIEW, custom_env.COMIC_SHORTS],
            [custom_env.COMIC_REVIEW, custom_env.COMIC_SHORTS],
            [custom_env.COMIC_REVIEW, custom_env.COMIC_SHORTS]
        ]

    def set_db_entry(self, db_entry):
        self._current_db_entry = db_entry
        return self.get_db_entry()
    
    def get_db_entry(self):
        return self._current_db_entry

    def update_db_entry(self, db_entry):
        columns_to_update = [col_info["name"] for col_name, col_info in databasecon.COLUMNS.items() if col_name != "id"]
        update_query = f"UPDATE {custom_env.TABLE_NAME} SET {', '.join([col + ' = ?' for col in columns_to_update])}, lastModifiedTime = {int(time.time() * 1000)} WHERE id = ?"
        values = list(db_entry[1:])
        values.append(db_entry[0])
        id = databasecon.execute(update_query, values, type="lastrowid")
        db_entry = databasecon.execute(f"select * from {custom_env.TABLE_NAME} where id = '{id}'", type="get")
        return self.set_db_entry(db_entry)
    
    def refresh_db_entry(self):
        id = self.get_db_entry()[databasecon.getId("id")]
        db_entry = databasecon.execute(f"select * from {custom_env.TABLE_NAME} where id = '{id}'", type="get")
        return self.set_db_entry(db_entry)
    
    def get_type(self):
        return self.get_db_entry()[databasecon.getId("type")]
    
    def get_start_phrase(self):
        return None

    def get_custom_instruction(self):
        return None
    
    def get_source(self):
        return None

    def get_system_prompt(self):
        return None

    def get_user_prompt(self):
        return None

    def get_images_prompt(self):
        return None

    def json_schema():
        return None

    def format(self):
        None

    def from_online(self):
        return False

    def merge_audio(self, audioPath):
        return None

    def post_process(self, start_show_answer=None):
        return None

    def get_video_for_frames(self, frame_params=None):
        return []

    def get_yt_category(self):
        return '24'

    def get_yt_title(self):
        return self.get_db_entry()[databasecon.getId('title')]
    
    def get_syt_start_desc(self):
        description = self.get_db_entry()[databasecon.getId('description')]
        return f"Puzzle: {description}"
    
    def get_yt_description(self):
        return f"""{self.get_syt_start_desc()}

Welcome to Think Solve Now – Your Ultimate Destination for Riddles, Puzzles, and Chess Challenges!

Are you ready to challenge your mind with brain teasers, riddles, and chess puzzles? On this channel, we dive into intriguing riddles, clever puzzles, and fun chess challenges that will push your critical thinking and strategy skills to the limit. Whether you love logic puzzles, word riddles, or solving chess positions, we’ve got something for everyone!

In each video, we’ll present a new puzzle or chess scenario, give you a chance to solve it, and then break down the solution step by step. From classic riddles to tricky chess puzzles, this channel is perfect for curious minds, chess lovers, and puzzle enthusiasts alike.

🔍 Why Subscribe?

- Fresh riddles, puzzles, and chess challenges uploaded regularly.
- Step-by-step explanations to enhance both your problem-solving and chess skills.
- Interactive puzzles designed to engage and challenge your mind.
- Perfect for anyone who enjoys mental challenges, brain workouts, and chess strategy.

🧩 Topics We Cover:

Logic riddles
- Math puzzles
- Lateral thinking puzzles
- Chess puzzles and tactics
- Brain teasers
- Wordplay and conundrums

♟️ Chess Enthusiasts:

- Dive into chess puzzles that sharpen your game strategy.
- Solve complex positions and learn how to outsmart your opponent.

💡 Join our community of puzzle solvers and chess lovers today! Hit that subscribe button and ring the bell for notifications so you never miss a challenge!

#Riddles #Puzzles #ChessPuzzles #BrainTeasers #MindGames #LogicPuzzles #ChessTactics #CriticalThinking #ProblemSolving #LateralThinking #Quiz #PuzzleLovers #BrainGames #ThinkSolveNow
"""

    def get_yt_tags(self):
        return ['riddle', 'thinking', 'fun', 'challenges']
    
    def get_youtube_link(self):
        youtubeVideoId = self.get_db_entry()[databasecon.getId('youtubeVideoId')]
        return f"https://www.youtube.com/watch?v={youtubeVideoId}" if youtubeVideoId else ""
    
    def get_x_title(self):
        title = self.get_db_entry()[databasecon.getId('title')]
        if not title or title == 'null':
            title = ''

        return title.strip()

    def get_x_description(self):
        description = self.get_db_entry()[databasecon.getId('description')]
        if not description or description == 'null':
            description = ''
        
        description = f'{description} {self.get_youtube_link()}'

        return description.strip()
    
    def get_hours_to_wait(self):
        return 20

    def get_animate_type(self):
        return None

    def get_yt_publish_time(self, type, add_day = 0, pub_hour=18):
        publish_at_ist = datetime.now().replace(hour=pub_hour, minute=0, second=0, microsecond=0)
        publish_at_ist = publish_at_ist + timedelta(days=add_day)
        publish_at_utc = publish_at_ist - timedelta(hours=5, minutes=30)
        publish_at_utc_iso = publish_at_utc.isoformat() + 'Z'
        publish_at_time_mills = int(publish_at_ist.timestamp() * 1000)

        publish_at_ist_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        publish_at_ist_start = publish_at_ist_start + timedelta(days=add_day)
        publish_at_time_mills_start = int(publish_at_ist_start.timestamp() * 1000)

        publish_at_ist_end = datetime.now().replace(hour=23, minute=59, second=59, microsecond=999)
        publish_at_ist_end = publish_at_ist_end + timedelta(days=add_day)
        publish_at_time_mills_end = int(publish_at_ist_end.timestamp() * 1000)

        filter = f" AND type = '{type}'"

        entries = databasecon.execute(f"SELECT id FROM {custom_env.TABLE_NAME} WHERE youtubeUploadedTime >= '{publish_at_time_mills_start}' AND youtubeUploadedTime <= '{publish_at_time_mills_end}' {filter}", type="get")

        if self.is_publish_day(publish_at_time_mills) and not entries:
            return publish_at_utc_iso, publish_at_time_mills

        return self.get_yt_publish_time(type, add_day + 1)

    def is_publish_day(self, timestamp_in_mills):
        """Return True if the timestamp falls on Fri/Sat/Sun (IST).

        The rest of the codebase previously used ``skip_day`` which returned
        False on publishable days and True otherwise. For clarity we now
        provide this positive helper.
        """
        timestamp_seconds = timestamp_in_mills / 1000
        date_object = datetime.utcfromtimestamp(timestamp_seconds)
        date_str = date_object.strftime('%Y-%m-%d')
        logger_config.debug(f"Checking for date - {date_str}")

        # weekday: 0=Mon, ..., 6=Sun
        weekday = date_object.weekday()
        return weekday in (4, 5, 6)

    def skip_day(self, timestamp_in_mills):
        """Backward-compatible alias for ``not is_publish_day``.

        Older code uses ``skip_day`` to decide whether to move to the next
        day.  It returns ``True`` when a day should be skipped (i.e. not
        Friday‑Sunday) and ``False`` on publishable days.
        """
        return not self.is_publish_day(timestamp_in_mills)
