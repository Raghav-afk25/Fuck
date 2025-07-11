import os
import logging
import random
import asyncio
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from celery import Celery
from yt_dlp import YoutubeDL

app = FastAPI(title="YouTube Audio Downloader", version="5.0.0")

# CORS setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

# Directories
DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Celery config
celery_app = Celery("tasks", broker="redis://localhost:6379/0", backend="redis://localhost:6379/0")

# Download helpers
def get_audio_path(video_id):
    for ext in ["m4a", "webm", "mp3", "opus"]:
        path = os.path.join(DOWNLOAD_DIR, f"{video_id}.{ext}")
        if os.path.exists(path) and os.path.getsize(path) > 100000:
            return path
    return None

@celery_app.task(name="download_task")
def download_task(video_id):
    url = f"https://www.youtube.com/watch?v={video_id}"
    filepath = os.path.join(DOWNLOAD_DIR, f"{video_id}.%(ext)s")
    opts = {
        "format": "bestaudio[ext=m4a]/bestaudio/best",
        "outtmpl": filepath,
        "quiet": True,
        "no_warnings": True,
        "retries": 5,
        "fragment_retries": 5,
        "concurrent_fragment_downloads": 5,
        "noplaylist": True,
        "cookiefile": "cookies/cookies.txt" if os.path.exists("cookies/cookies.txt") else None,
    }

    try:
        with YoutubeDL(opts) as ydl:
            ydl.download([url])
    except Exception as e:
        logger.error(f"[ERROR] Failed to download: {e}")
        return "failed"

    return "done"

# API endpoints

@app.get("/")
def root():
    return {"status": "API is live"}

@app.get("/song/{video_id}")
async def get_song(video_id: str, api: str = ""):
    file_path = get_audio_path(video_id)
    if file_path:
        return FileResponse(file_path, media_type="audio/mpeg")

    task = download_task.delay(video_id)

    # Wait max 30s for file
    for _ in range(30):
        await asyncio.sleep(1)
        file_path = get_audio_path(video_id)
        if file_path:
            return FileResponse(file_path, media_type="audio/mpeg")

    raise HTTPException(status_code=202, detail="Processing, try again in few seconds.")
