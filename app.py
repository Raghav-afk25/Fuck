import os
import logging
import random
import asyncio
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from celery import Celery
import yt_dlp

# Setup logging
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
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Version/17.1 Safari/605.1.15",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4) AppleWebKit/605.1.15 Version/17.1 Safari/604.1"
]
YOUTUBE_CLIENTS = ["mweb", "web", "web_music", "android", "ios", "tv"]

# FastAPI setup
app = FastAPI(title="Advanced YouTube Audio Downloader API", version="4.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Celery setup
celery_app = Celery("yt_dl_tasks", broker="redis://localhost:6379/0", backend="redis://localhost:6379/0")

# Utilities
def get_random_user_agent():
    return random.choice(USER_AGENTS)

def find_downloaded_file(video_id):
    for ext in COMMON_EXTS:
        file_path = os.path.join(DOWNLOAD_DIR, f"{video_id}.{ext}")
        if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
            return file_path
    return None

def validate_downloaded_file(file_path, video_id):
    return os.path.exists(file_path) and os.path.getsize(file_path) > 100000

def get_task_file_name(video_id):
    return os.path.join(DOWNLOAD_DIR, f"{video_id}_ready.txt")

# Celery Task
@celery_app.task(name="download_audio_task")
def download_audio_task(video_id):
    url = f"https://www.youtube.com/watch?v={video_id}"
    output_template = os.path.join(DOWNLOAD_DIR, f"{video_id}.%(ext)s")

    ydl_opts = {
        "format": "bestaudio[ext=m4a]/bestaudio/best",
        "outtmpl": output_template,
        "quiet": True,
        "no_warnings": True,
        "cookiefile": "cookies/cookies.txt" if os.path.exists("cookies/cookies.txt") else None,
        "retries": 10,
        "fragment_retries": 10,
        "file_access_retries": 10,
        "nocheckcertificate": True,
        "prefer_insecure": True,
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

        downloaded_file = find_downloaded_file(video_id)
        if downloaded_file and validate_downloaded_file(downloaded_file, video_id):
            with open(get_task_file_name(video_id), "w") as f:
                f.write(downloaded_file)
            return {"status": "completed", "file_path": downloaded_file}
        return {"status": "failed", "error": "Download failed or file invalid."}
    except Exception as e:
        return {"status": "failed", "error": str(e)}

# Endpoints
@app.get("/")
def root():
    return {"status": "API running"}

@app.get("/download")
async def queue_download(video_id: str):
    cached_file = find_downloaded_file(video_id)
    if cached_file and validate_downloaded_file(cached_file, video_id):
        return {"status": "ready", "path": f"/serve/{video_id}"}
    task = download_audio_task.delay(video_id)
    return {"status": "queued", "task_id": task.id}

@app.get("/status")
async def get_status(task_id: str, video_id: str):
    task = celery_app.AsyncResult(task_id)
    if task.state == "PENDING":
        return {"status": "pending"}
    elif task.state == "FAILURE":
        return {"status": "failed", "error": str(task.info)}
    elif task.state == "SUCCESS":
        marker_file = get_task_file_name(video_id)
        if os.path.exists(marker_file):
            with open(marker_file, "r") as f:
                path = f.read().strip()
            if os.path.exists(path):
                return {"status": "ready", "path": f"/serve/{video_id}"}
        return {"status": "done", "note": "file not found yet"}
    else:
        return {"status": task.state}

@app.get("/serve/{video_id}")
async def serve_downloaded_song(video_id: str):
    file = find_downloaded_file(video_id)
    if file and validate_downloaded_file(file, video_id):
        return FileResponse(file, media_type="audio/mpeg")
    raise HTTPException(status_code=404, detail="File not found")

# ✅ NEW: Bot-Compatible Endpoint
@app.get("/song/{video_id}")
async def song_compatible(video_id: str):
    cached_file = find_downloaded_file(video_id)
    if cached_file and validate_downloaded_file(cached_file, video_id):
        return FileResponse(cached_file, media_type='audio/mpeg')

    # If not cached, queue and return JSON response
    task = download_audio_task.delay(video_id)
    return {
        "status": "queued",
        "task_id": task.id,
        "message": "File is being prepared. Try again shortly."
    }
