import os
import logging
import random
import asyncio
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from celery import Celery
import yt_dlp

# Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("api_logs.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("api")

# Constants
DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
COMMON_EXTS = ["m4a", "webm", "mp3", "opus"]
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Mobile/15E148 Safari/604.1"
]
YOUTUBE_CLIENTS = ["mweb", "web", "web_music", "android", "ios", "tv"]
DOMAIN = os.getenv("API_DOMAIN", "http://localhost:8000")

# FastAPI app
app = FastAPI(title="Advanced YouTube Audio Downloader API", version="5.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Celery setup
celery_app = Celery("yt_dl_tasks", broker="redis://localhost:6379/0", backend="redis://localhost:6379/0")

# Utility functions
def get_random_user_agent():
    return random.choice(USER_AGENTS)

def find_downloaded_file(video_id):
    for ext in COMMON_EXTS:
        path = os.path.join(DOWNLOAD_DIR, f"{video_id}.{ext}")
        if os.path.exists(path) and os.path.getsize(path) > 0:
            return path
    return None

def validate_file(path):
    return os.path.exists(path) and os.path.getsize(path) > 100000

# Celery Task
@celery_app.task(name="download_audio_task")
def download_audio_task(video_id):
    url = f"https://www.youtube.com/watch?v={video_id}"
    output_template = os.path.join(DOWNLOAD_DIR, f"{video_id}.%(ext)s")

    ydl_opts = {
        "format": "bestaudio[ext=m4a]/bestaudio",
        "outtmpl": output_template,
        "quiet": True,
        "cookiefile": "cookies/cookies.txt" if os.path.exists("cookies/cookies.txt") else None,
        "retries": 5,
        "fragment_retries": 5,
        "file_access_retries": 5,
        "nocheckcertificate": True,
        "no_cache_dir": True,
        "ignoreerrors": True,
        "concurrent_fragment_downloads": 5,
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
        downloaded = find_downloaded_file(video_id)
        if downloaded and validate_file(downloaded):
            return {"status": "completed", "file_path": downloaded}
        return {"status": "failed", "error": "File invalid or missing"}
    except Exception as e:
        return {"status": "failed", "error": str(e)}

# FastAPI Endpoints
@app.get("/")
def root():
    return {"status": "API running"}

@app.get("/status")
def status(task_id: str):
    task = celery_app.AsyncResult(task_id)
    return {"task_id": task_id, "state": task.state, "info": str(task.info)}

@app.get("/serve/{video_id}")
def serve_file(video_id: str):
    file = find_downloaded_file(video_id)
    if file and validate_file(file):
        return FileResponse(file, media_type="audio/mpeg")
    raise HTTPException(status_code=404, detail="File not found")

@app.get("/song/{video_id}")
async def song(video_id: str):
    file = find_downloaded_file(video_id)
    if file and validate_file(file):
        return {
            "status": "ready",
            "url": f"{DOMAIN}/serve/{video_id}"
        }
    task = download_audio_task.delay(video_id)
    return {
        "status": "queued",
        "task_id": task.id,
        "message": "File is being prepared. Try again shortly."
    }
