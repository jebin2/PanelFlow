from fastapi import FastAPI, Request, HTTPException, Form, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import sqlite3
import os
from custom_logger import logger_config
import custom_env
import databasecon
import time
import subprocess
import queue
import sys
import signal
from pathlib import Path
import shutil
import mimetypes
import traceback
import common
from content_map import content_map
import fcntl
import asyncio
from typing import List
import json

app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_text(json.dumps(message, ensure_ascii=False))
            except:
                # Remove disconnected connections
                if connection in self.active_connections:
                    self.active_connections.remove(connection)

manager = ConnectionManager()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            # Handle any websocket messages if needed
    except WebSocketDisconnect:
        manager.disconnect(websocket)

@app.get("/", response_class=HTMLResponse)
async def main_page():
    logger_config.debug("Serving main page...")
    if os.path.exists("views/index.html"):
        return FileResponse("views/index.html")
    else:
        raise HTTPException(status_code=404, detail="Main Page Not Found")

@app.get("/media", response_class=HTMLResponse)
async def media():
    logger_config.debug("Serving media page...")
    if os.path.exists("views/media.html"):
        return FileResponse("views/media.html")
    else:
        raise HTTPException(status_code=404, detail="Media Page Not Found")

@app.post("/submit")
async def submit_entry(
    audioPath: str = Form(...),
    videoPath: str = Form(...),
    title: str = Form(...),
    description: str = Form(...),
    thumbnailText: str = Form(...),
    answer: str = Form(...),
    type: str = Form(...)
):
    logger_config.debug("Handling entry submission...")
    try:
        lastModifiedTime = int(time.time() * 1000)
        databasecon.execute(
            f'''INSERT INTO {custom_env.TABLE_NAME} (audioPath, videoPath, title, description, thumbnailText, answer, type, lastModifiedTime) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
            (audioPath, videoPath, title, description, thumbnailText, answer, type, lastModifiedTime)
        )
        logger_config.success(f"Entry submitted: {title}")
        return {"message": "Entry submitted successfully!"}
    except Exception as e:
        logger_config.error(f"Error during entry submission: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@app.delete("/delete/{entry_id}")
async def delete_entry(entry_id: int):
    logger_config.debug(f"Deleting entry with ID {entry_id}...")
    try:
        databasecon.execute(f"DELETE FROM {custom_env.TABLE_NAME} WHERE id = ?", (entry_id,))
        logger_config.success(f"Entry with ID {entry_id} deleted.")
        return {"message": "Entry deleted successfully"}
    except Exception as e:
        logger_config.error(f"Error deleting entry: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@app.put("/update/{entry_id}")
async def update_entry(entry_id: int, request: Request):
    logger_config.debug(f"Updating entry with ID {entry_id}...")
    try:
        data = await request.json()
        type_result = databasecon.execute(f"select type from {custom_env.TABLE_NAME} where id = '{entry_id}'", type='get')
        if not type_result:
            raise HTTPException(status_code=404, detail="Entry not found")
        
        type_value = type_result[0]
        
        if type_value in [custom_env.COMIC_REVIEW, custom_env.COMIC_SHORTS]:
            databasecon.execute(
                f'''UPDATE {custom_env.TABLE_NAME} SET audioPath = ?, title = ?, description = ?, thumbnailText = ?, 
                generatedVideoPath = ?, generatedThumbnailPath = ?, youtubeVideoId = ?, xId = ?, lastModifiedTime = {int(time.time() * 1000)} 
                WHERE id = ?''',
                (data["audioPath"], data["title"], data["description"], data["thumbnailText"], 
                 data.get("generatedVideoPath"), data.get("generatedThumbnailPath"),
                 data.get("youtubeVideoId", ""), data.get("xId", ""), entry_id)
            )
        else:
            databasecon.execute(
                f'''UPDATE {custom_env.TABLE_NAME} SET audioPath = ?, title = ?, description = ?, thumbnailText = ?, 
                answer = ?, generatedVideoPath = ?, generatedThumbnailPath = ?, youtubeVideoId = ?, xId = ?, lastModifiedTime = {int(time.time() * 1000)} 
                WHERE id = ?''',
                (data["audioPath"], data["title"], data["description"], data["thumbnailText"],
                 data["answer"], data.get("generatedVideoPath"), data.get("generatedThumbnailPath"),
                 data.get("youtubeVideoId", ""), data.get("xId", ""), entry_id)
            )
        logger_config.success(f"Entry with ID {entry_id} updated.")
        return {"message": "Entry updated successfully!"}
    except Exception as e:
        logger_config.error(f"Error updating entry: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to update entry.")

@app.get("/entries")
async def get_entries():
    logger_config.debug("Fetching all entries...")
    try:
        databasecon.execute(f'''SELECT * FROM {custom_env.TABLE_NAME}''')
        with sqlite3.connect(custom_env.DATABASE) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(f'''SELECT * FROM {custom_env.TABLE_NAME} ORDER BY lastModifiedTime DESC''').fetchall()
            entries = [dict(row) for row in rows]
        logger_config.success(f"Fetched {len(entries)} entries.")
        return entries
    except Exception as e:
        logger_config.error(f"Error fetching entries: {str(e)}")
        raise HTTPException(
            status_code=500, 
            detail=f"Internal Server Error {str(e)} pwd:: {os.getcwd()} database_path:: {custom_env.DATABASE} isexits:: {common.file_exists(custom_env.DATABASE)} {os.listdir(os.getcwd())}"
        )

@app.get("/video_files")
async def get_video_files():
    try:
        files = []
        allowed_files = common.list_directories_recursive(custom_env.COMIC_REVIEW_PATH)

        entries = databasecon.execute("select id, videoPath from entries where videoPath is not NULL and videoPath != ''")
        used_files = []
        for entry in entries:
            id, videoPath = entry
            used_files.append(videoPath)

        allowed_files = sorted([file for file in allowed_files if len([addedFile for addedFile in used_files if addedFile in file]) == 0])
        return allowed_files
    except Exception as e:
        logger_config.error(f"Error fetching video files: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

# Route to serve audio files
@app.get("/audio/{filename:path}")
async def serve_audio(filename: str):
    logger_config.debug(f"Serving audio file: {filename}")
    file_path = os.path.join("audio", filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Audio file not found")
    return FileResponse(file_path)

# Route to serve video files with proper streaming support
@app.get("/video/{filename:path}")
async def serve_video(filename: str):
    logger_config.debug(f"Serving video file: {filename}")
    file_path = os.path.join("video", filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Video file not found")
    
    # Get MIME type
    mime_type, _ = mimetypes.guess_type(filename)
    return FileResponse(file_path, media_type=mime_type)

# Command execution globals
allowed_cmds = {
    "test": 'while true; do echo "test"; sleep 1; done',
    "publish_to_x": 'python3 main.py -upx',
    "publish_to_youtube": 'python3 main.py -upyt',
    "gen_video": 'python3 main.py --gen-video',
    "new_content": 'python3 main.py --new-content',
    "create_publish": 'python3 main.py --new-content -upyt -upx',
    "process": 'python3 main.py',
    "refactor": 'python3 refactorData.py'
}

current_process = {}

def reset_current_process():
    global current_process
    current_process = {
        "process": None,
        "output_file": 'test.log',
        "file_position": 0,
        "output_queue": queue.Queue()
    }

reset_current_process()

# Define a function to handle cleanup
def handle_exit(signal_received, frame):
    for command in allowed_cmds.keys():
        if current_process["process"]:
            os.killpg(os.getpgid(current_process['process'].pid), signal.SIGKILL)
    sys.exit(0)

# Register the signal handler for SIGINT
signal.signal(signal.SIGINT, handle_exit)

@app.get('/run-command/{command}')
async def run_command(command: str, type: str = Query(""), id: str = Query("")):
    logger_config.debug(f"Run command called: {command}")
    
    if current_process['process'] and current_process['process'].poll() is None:
        return {"message": "Command already running!", "status": "already_running"}
    
    # Reset if there's a dead process
    if current_process['process'] and current_process['process'].poll() is not None:
        reset_current_process()
    
    if command not in allowed_cmds:
        raise HTTPException(status_code=400, detail="Invalid command")
    
    os.environ['PYTHONUNBUFFERED'] = "1"
    cmd_to_run = allowed_cmds[command]

    # Append type-based arguments
    type_map = content_map.get_type_class_map()
    for t in type.split(','):
        if t in type_map:
            cmd_to_run += f" {type_map[t]['parse_arguments']}"

            if t == custom_env.COMIC_REVIEW:
                cmd_to_run += f" {type_map[custom_env.COMIC_SHORTS]['parse_arguments']}"

    if id:
        cmd_to_run += f' --id "{id}"'

    logger_config.debug(f'Running cmd:: {cmd_to_run}')

    async def run_and_stream_output():
        process = None
        try:
            process = subprocess.Popen(
                cmd_to_run,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=1,
                universal_newlines=True,
                preexec_fn=os.setsid,
		        env={**os.environ, 'PYTHONUNBUFFERED': '1', 'CUDA_LAUNCH_BLOCKING': '1', 'USE_CPU_IF_POSSIBLE': 'true'}
            )
            
            # Set non-blocking I/O
            fd = process.stdout.fileno()
            fl = fcntl.fcntl(fd, fcntl.F_GETFL)
            fcntl.fcntl(fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)

            current_process['process'] = process

            # Stream the output and send it via WebSocket in real-time
            while True:
                try:
                    output = process.stdout.readline()
                    if output:
                        print(output.strip())
                        if "authorization_url####" in output.strip():
                            asyncio.create_task(manager.broadcast({
                                'type': 'authorization_url',
                                'url': output.strip().split("authorization_url####")[-1]
                            }))
                        else:
                            asyncio.create_task(manager.broadcast({
                                'type': 'command_output',
                                'data': output.strip()
                            }))
                        sys.stdout.flush()
                    
                    if process.poll() is not None:
                        break
                        
                    # Small delay to prevent CPU spinning
                    await asyncio.sleep(0.01)
                    
                except Exception as e:
                    logger_config.error(f"Error reading process output: {e}")
                    break

            # Process finished
            return_code = process.returncode if process else -1
            asyncio.create_task(manager.broadcast({
                'type': 'command_finished',
                'return_code': return_code
            }))
            
        except Exception as e:
            logger_config.error(f"Error in run_and_stream_output: {e}")
            asyncio.create_task(manager.broadcast({
                'type': 'command_error',
                'error': str(e)
            }))
        finally:
            current_process['process'] = None

    # Start the command execution in a separate task
    asyncio.create_task(run_and_stream_output())
    return {"message": "Command started!", "status": "started"}

@app.post('/stop-command/{command}')
async def stop_command(command: str):
    logger_config.debug(f"Stop command called for: {command}")
    logger_config.debug(f"Current process state: {current_process['process']}")
    try:
        # Check if there's actually a process to stop
        if current_process['process'] is None:
            return {'message': 'No command is currently running.', 'status': 'no_process'}

        # Check if process has already terminated naturally
        if current_process['process'].poll() is not None:
            # Process already finished, just clean up
            reset_current_process()
            return {'message': 'Command has already finished.', 'status': 'already_finished'}

        try:
            # Get the process group ID before attempting to kill
            pgid = os.getpgid(current_process['process'].pid)
            
            # Kill the entire process group
            os.killpg(pgid, signal.SIGTERM)  # Try SIGTERM first
            
            # Wait a bit for graceful shutdown
            await asyncio.sleep(1)

            # If still running, force kill
            if current_process['process'] and current_process['process'].poll() is None:
                os.killpg(pgid, signal.SIGKILL)

        except ProcessLookupError:
            # Process already dead
            logger_config.debug("Process already terminated")
        except OSError as e:
            # Handle permission errors or other OS-level issues
            logger_config.error(f"Error terminating process: {e}")
            # Try to kill just the main process if group kill fails
            try:
                current_process['process'].terminate()
                await asyncio.sleep(0.5)
                if current_process['process'].poll() is None:
                    current_process['process'].kill()
            except:
                pass
        
        # Always reset the process state
        reset_current_process()
        
        # Notify connected clients
        await manager.broadcast({
            'type': 'command_stopped',
            'message': 'Command terminated by user'
        })
        
        return {'message': 'Command terminated successfully.', 'status': 'terminated'}
        
    except Exception as e:
        logger_config.error(f"Error in stop_command: {str(e)}")
        # Force reset even if there was an error
        reset_current_process()
        raise HTTPException(status_code=500, detail=f'Error stopping command: {str(e)}')

@app.post('/save_authoriz_code')
async def save_authoriz_code_process(request: Request):
    data = await request.json()
    with open(custom_env.AUTHORIZATION_CODE_PATH, 'w') as file:
        file.write(data['code'])
    return {'message': 'code saved.'}

##############################################################
# Media handling functions (keeping your existing logic)
##############################################################

THUMBNAIL_SIZE = (300, 300)

def get_file_type(filename):
    ext = filename.lower().split('.')[-1]
    if ext in {'png', 'jpg', 'jpeg', 'gif'}:
        return 'image'
    elif ext in {'mp4', 'mov', 'avi'}:
        return 'video'
    return None

def create_thumbnail_ffmpeg(video_path, thumb_path, thumb_size_str="300x300"):
    ffmpeg_cmd = shutil.which("ffmpeg")
    if not ffmpeg_cmd:
        logger_config.error("ffmpeg not found in PATH. Cannot generate video thumbnail.")
        return False

    command = [
        ffmpeg_cmd,
        '-i', str(video_path),
        '-ss', '00:00:01.000',
        '-vframes', '1',
        '-vf', f'scale={thumb_size_str}',
        '-q:v', '3',
        str(thumb_path)
    ]
    try:
        result = common.run_ffmpeg(command)
        logger_config.debug(f"FFmpeg output: {result.stdout}")
        logger_config.debug(f"FFmpeg error: {result.stderr}")
        return True
    except subprocess.CalledProcessError as e:
        logger_config.error(f"ffmpeg failed for {video_path}: {e}")
        return False
    except subprocess.TimeoutExpired:
        logger_config.error(f"ffmpeg timed out for {video_path}")
        return False
    except Exception as e:
        logger_config.error(f"Error running ffmpeg for {video_path}: {str(e)}")
        return False

def create_thumbnail(file_path, thumb_path):
    file_type = get_file_type(file_path)
    path_obj = Path(file_path)
    thumb_path_obj = Path(thumb_path)

    if file_type == 'image':
        try:
            from PIL import Image
            with Image.open(path_obj) as img:
                img.thumbnail(THUMBNAIL_SIZE)
                thumb_path_obj.parent.mkdir(parents=True, exist_ok=True)
                img.save(thumb_path_obj, 'JPEG')
        except ImportError:
            logger_config.error("Pillow (PIL) not installed. Cannot generate image thumbnail.")
        except Exception as e:
            logger_config.error(f"Error creating image thumbnail for {file_path}: {e}")

    elif file_type == 'video':
        thumb_path_obj.parent.mkdir(parents=True, exist_ok=True)
        create_thumbnail_ffmpeg(path_obj, thumb_path_obj, f"{THUMBNAIL_SIZE[0]}x{THUMBNAIL_SIZE[1]}")
    else:
        logger_config.warning(f"Cannot create thumbnail for unsupported file type: {file_path}")

def get_media_info(file_path):
    full_name = file_path.split("/")[-1]
    file_name, _ = os.path.splitext(full_name)
    cache_name = f"{file_name}-thumbnailcache.jpg"
    
    cache_path = f'{custom_env.TEMP_OUTPUT}/{cache_name}'
    if not common.file_exists(cache_path):
        create_thumbnail(file_path, cache_path)

    return {
        'original_full_path': file_path,
        'cache_full_path': cache_path,
        'name': file_name,
        'type': mimetypes.guess_type(file_path)[0] or 'application/octet-stream',
        'name_w_ext': full_name
    }

def remove_added_file(files):
    entries = databasecon.execute(f"select id, generatedThumbnailPath, generatedVideoPath from {custom_env.TABLE_NAME}")
    files_to_remove = set()
    for entry in entries:
        id, generatedThumbnailPath, generatedVideoPath = entry
        generatedThumbnailPath = generatedThumbnailPath.split("/")[-1] if generatedThumbnailPath else None
        generatedVideoPath = generatedVideoPath.split("/")[-1] if generatedVideoPath else None
        
        for file_path in files:
            if (generatedThumbnailPath and file_path.endswith(generatedThumbnailPath)):
                files_to_remove.add(generatedThumbnailPath)
            if (generatedVideoPath and file_path.endswith(generatedVideoPath)):
                files_to_remove.add(generatedVideoPath)

    new_files = [
        file_path for file_path in files
        if not any(file_path.endswith(remove_file) for remove_file in files_to_remove)
    ]
    return new_files

@app.get('/api/media')
async def list_media(
    directory: str = Query(...),
    page: int = Query(0),
    type: str = Query("all")
):
    try:
        directory_path = Path(directory)
        if not directory_path.exists() or not directory_path.is_dir():
            raise HTTPException(status_code=400, detail='Invalid directory')
        
        files = common.list_files_recursive(directory_path)
        files = [file_path for file_path in files if '-thumbnailcache' not in file_path]
        files = remove_added_file(files)
        files = [file_path for file_path in files if get_file_type(file_path) == type or type == "all"]
        files = sorted(files)
        per_page = 50 * page
        files = files[per_page:per_page+50]

        media_files = []
        for file_path in files:
            if get_file_type(file_path):
                try:
                    media_info = get_media_info(file_path)
                    if media_info:
                        media_files.append(media_info)
                except:
                    pass
                    
        return media_files
        
    except Exception as e:
        logger_config.debug(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

@app.get('/api/media/file')
async def view_media_file(
    file_path: str = Query(...),
    as_attachment: bool = Query(False)
):
    try:
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="File not found")
        
        mime_type, _ = mimetypes.guess_type(file_path)
        
        if as_attachment:
            filename = os.path.basename(file_path)
            return FileResponse(file_path, media_type=mime_type, filename=filename)
        else:
            return FileResponse(file_path, media_type=mime_type)
    except Exception:
        raise HTTPException(status_code=404, detail="File not found")

@app.delete('/api/media/')
async def delete_media(file_path: str = Query(...)):
    try:
        common.remove_file(file_path)
        return {'success': True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post('/api/media/add')
async def add_media(
    file_path: str = Query(...),
    type: str = Query(...),
    title: str = Query(...)
):
    try:
        path = None
        full_name = file_path.split("/")[-1]
        file_name, ext = os.path.splitext(full_name)

        if path:
            target = f'{path}/{file_name}{ext}'
            if custom_env.TEMP_OUTPUT in file_path:
                shutil.move(file_path, target)

            if ext == '.mp4':
                databasecon.execute(f"""INSERT into {custom_env.TABLE_NAME} (title, generatedVideoPath, type, lastModifiedTime) VALUES (?, ?, ?, ?)""", (title, target, type, int(time.time() * 1000)))
            else:
                databasecon.execute(f"""INSERT into {custom_env.TABLE_NAME} (title, generatedThumbnailPath, type, lastModifiedTime) VALUES (?, ?, ?, ?)""", (title, target, type, int(time.time() * 1000)))
                
            return {'success': True}

        return {'success': False}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Error handlers
@app.exception_handler(404)
async def not_found_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=404,
        content={'error': 'Resource not found'}
    )

@app.exception_handler(500)
async def server_error_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=500,
        content={'error': 'Internal server error'}
    )

def start():
    import uvicorn
    try:
        from jebin_lib import load_env
        load_env()
    except Exception as e:
        logger_config.error(f"Failed to sync database during startup: {e}")

    port = custom_env.SERVER_PORT
    logger_config.success(f"Starting server on port {port}")
    uvicorn.run("server:app", host='0.0.0.0', port=port)

if __name__ == "__main__":
    start()