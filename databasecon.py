import sqlite3
from custom_logger import logger_config
import custom_env
import gc
import traceback
import os

COLUMNS = {
    "id": {
        "index": 0,
        "name": "id",
        "type": "integer"
    },
    "audioPath": {
        "index": 1,
        "name": "audioPath",
        "type": "text"
    },
    "videoPath": {
        "index": 2,
        "name": "videoPath",
        "type": "text"
    },
    "title": {
        "index": 3,
        "name": "title",
        "type": "text"
    },
    "description": {
        "index": 4,
        "name": "description",
        "type": "text"
    },
    "thumbnailText": {
        "index": 5,
        "name": "thumbnailText",
        "type": "text"
    },
    "answer": {
        "index": 6,
        "name": "answer",
        "type": "text"
    },
    "generatedVideoPath": {
        "index": 7,
        "name": "generatedVideoPath",
        "type": "text"
    },
    "generatedThumbnailPath": {
        "index": 8,
        "name": "generatedThumbnailPath",
        "type": "text"
    },
    "youtubeVideoId": {
        "index": 9,
        "name": "youtubeVideoId",
        "type": "text"
    },
    "youtubeUploadedTime":{
        "index": 10,
        "name": "youtubeUploadedTime",
        "type": "integer"
    },
    "xId": {
        "index": 11,
        "name": "xId",
        "type": "text"
    },
    "xUploadedTime":{
        "index": 12,
        "name": "xUploadedTime",
        "type": "integer"
    },
    "type": {
        "index": 13,
        "name": "type",
        "type": "text"
    },
    "longFormId": {
        "index": 14,
        "name": "longFormId", # used to store id of long_form_text in each text. Used to decided whether to publish or not for combine_anime_review. Used to store anime_shorts
        "type": "integer"
    },
    "otherDetails": {
        "index": 15,
        "name": "otherDetails",
        "type": "text"
    },
    "lastModifiedTime": {
        "index": 16,
        "name": "lastModifiedTime",
        "type": "integer"
    },
    "json_data": {
        "index": 17,
        "name": "json_data",
        "type": "text"
    },
    "video_processed": {
        "index": 18,
        "name": "video_processed",
        "type": "integer"
    }
}

def getId(key):
    return COLUMNS[key]['index']

# Create and initialize the database
def init_database():
    os.makedirs(os.path.dirname(custom_env.DATABASE), exist_ok=True)
    with sqlite3.connect(custom_env.DATABASE) as conn:
        columns_sql = ", ".join(
            [f"{col['name']} {col['type'].upper()}" + (" PRIMARY KEY" if col['name'] == "id" else " NULL") 
            for col in COLUMNS.values()]
        )

        create_table_query = f"CREATE TABLE IF NOT EXISTS {custom_env.TABLE_NAME} ({columns_sql})"
        conn.execute(create_table_query)
        sync_all_columns()

def sync_all_columns():
    with sqlite3.connect(custom_env.DATABASE) as conn:
        cursor = conn.cursor()
        cursor.execute(f"PRAGMA table_info({custom_env.TABLE_NAME})")
        existing_columns = [info[1] for info in cursor.fetchall()]

        for key, col in COLUMNS.items():
            if col['name'] not in existing_columns:
                logger_config.debug(f"Adding missing column: {col['name']} {col['type'].upper()}")
                cursor.execute(f"ALTER TABLE {custom_env.TABLE_NAME} ADD COLUMN {col['name']} {col['type'].upper()}")
        conn.commit()

def execute(query, values=None, type='getAll'):
    conn = None  # Initialize conn variable outside the try block
    is_modification = False
    try:
        init_database()
        conn = sqlite3.connect(custom_env.DATABASE)
        cursor = conn.cursor()

        if values:
            cursor.execute(query, values)
        else:
            cursor.execute(query)

        if query:
            is_modification = query.strip().upper().startswith(("INSERT", "UPDATE", "DELETE", "REPLACE"))

        if type == 'getAll':
            return cursor.fetchall()  # Return all results for 'get' type
        if type == 'get':
            return cursor.fetchone()  # Return all results for 'get' type
        if type == "lastrowid":
            return cursor.lastrowid
        if type == 'cursor':
            return cursor

        return None
    except Exception as e:
        logger_config.error(f"Query:: {query} value:: {values}\n{traceback.format_exc()}")
        raise ValueError(f'Error in databasecon.execute:: {str(e)}')
    finally:
        if conn:  # Check if conn was successfully created
            conn.commit()
            conn.close()
            # backup_database()
            gc.collect()


# if __name__ == "__main__":
#     # Correctly format the execute call with proper type
#     results = execute("get", "SELECT audioPath FROM {custom_env.TABLE_NAME} WHERE generatedVideoPath IS NULL OR generatedVideoPath = ''")
#     if results:
#         for row in results:
#             logger_config.debug(row)  # Print the results