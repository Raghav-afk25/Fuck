import os
import glob
import logging
import asyncio
import random
import platform
import functools
from datetime import datetime
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from celery import Celery
import yt_dlp

# Directories & Constants
DOWNLOAD_DIR = "downloads"
COOKIES_FILE = "cookies/cookies.txt"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
COMMON_EXTS = ["m4a", "webm", "mp3", "opus"]

# Celery Setup
celery_app = Celery(
    "yt_dl_tasks",
    broker="redis://localhost:6379/0",
    backend="redis://localhost:6379/0"
)

# Logger Setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("api")

# FastAPI App
app = FastAPI(title="YT API with Celery")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# User-Agents & Clients
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Version/17.1 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36"
]
YOUTUBE_CLIENTS = ["mweb", "web", "web_music", "android", "ios", "tv"]

def get_random_user_agent():
    return random.choice(USER_AGENTS)

def find_downloaded_file(video_id):
    for ext in COMMON_EXTS:
        path = os.path.join(DOWNLOAD_DIR, f"{video_id}.{ext}")
        if os.path.exists(path) and os.path.getsize(path) > 0:
            return path
    return None

def validate_downloaded_file(file_path):
    return os.path.exists(file_path) and os.path.getsize(file_path) > 100000

# Celery Task
@celery_app.task(name="download_audio_task")
def download_audio_task(video_id):
    url = f"https://www.youtube.com/watch?v={video_id}"
    output_template = os.path.join(DOWNLOAD_DIR, f"{video_id}.%(ext)s")
    ydl_opts = {
        "format": "bestaudio[ext=m4a]/bestaudio",
        "outtmpl": output_template,
        "cookiefile": COOKIES_FILE,
        "quiet": True,
        "no_warnings": True,
        "retries": 5,
        "fragment_retries": 5,
        "file_access_retries": 5,
        "nocheckcertificate": True,
        "prefer_insecure": True,
        "no_cache_dir": True,
        "ignoreerrors": True,
        "concurrent_fragment_downloads": 4,
        "force_overwrites": True,
        "noplaylist": True,
        "addheader": [f"User-Agent:{get_random_user_agent()}"],
        "extractor_args": {
            "youtube": {
                "player_client": random.choice(YOUTUBE_CLIENTS)
            }
        }
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        downloaded_file = find_downloaded_file(video_id)
        if downloaded_file and validate_downloaded_file(downloaded_file):
            return {"status": "done", "path": downloaded_file}
        return {"status": "error", "reason": "File not found or invalid"}
    except Exception as e:
        return {"status": "error", "reason": str(e)}

# Endpoint
@app.get("/song/{video_id}")
async def get_song(video_id: str):
    cached = find_downloaded_file(video_id)
    if cached and validate_downloaded_file(cached):
        return FileResponse(cached, media_type="audio/mpeg")

    task = download_audio_task.delay(video_id)
    timeout = 30
    waited = 0
    while waited < timeout:
        result = celery_app.AsyncResult(task.id)
        if result.ready():
            if result.successful():
                data = result.result
                if data.get("status") == "done":
                    file_path = data.get("path")
                    if file_path and validate_downloaded_file(file_path):
                        return FileResponse(file_path, media_type="audio/mpeg")
            break
        await asyncio.sleep(1)
        waited += 1

    raise HTTPException(status_code=202, detail="File is being prepared. Try again shortly.")

@app.get("/")
def root():
    return {"status": "OK", "message": "YT API with Celery running"}
