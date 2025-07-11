import os
import random
import logging
import asyncio
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from celery import Celery
from yt_dlp import YoutubeDL

# ---- Config ----
DOWNLOAD_DIR = "downloads"
COOKIES_FILE = "cookies.txt"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Mobile/15E148 Safari/604.1"
]
YOUTUBE_CLIENTS = ["mweb", "web", "web_music", "android", "ios", "tv"]

# ---- Logging ----
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("api_logs.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("celery_api")

# ---- FastAPI & CORS ----
app = FastAPI(title="Celery YT Audio API", version="6.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- Celery Setup ----
celery_app = Celery(
    "yt_dl_tasks",
    broker="redis://localhost:6379/0",
    backend="redis://localhost:6379/0"
)

# ---- Utility Functions ----
def get_filepath(video_id):
    return os.path.join(DOWNLOAD_DIR, f"{video_id}.m4a")

def is_valid_file(path):
    return os.path.exists(path) and os.path.getsize(path) > 100000

# ---- Celery Task ----
@celery_app.task(name="download_audio_task")
def download_audio_task(video_id):
    url = f"https://www.youtube.com/watch?v={video_id}"
    output = get_filepath(video_id)

    ydl_opts = {
        "format": "bestaudio[ext=m4a]/bestaudio",
        "outtmpl": output,
        "cookiefile": COOKIES_FILE if os.path.exists(COOKIES_FILE) else None,
        "quiet": True,
        "retries": 10,
        "fragment_retries": 10,
        "file_access_retries": 10,
        "nocheckcertificate": True,
        "noplaylist": True,
        "prefer_ffmpeg": True,
        "concurrent_fragment_downloads": 5,
        "addheader": [f"User-Agent:{random.choice(USER_AGENTS)}"],
        "extractor_args": {
            "youtube": {"player_client": random.choice(YOUTUBE_CLIENTS)}
        }
    }

    try:
        with YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        if is_valid_file(output):
            return {"status": "completed", "path": output}
        return {"status": "failed", "error": "File invalid or too small"}
    except Exception as e:
        return {"status": "failed", "error": str(e)}

# ---- Routes ----
@app.get("/")
def root():
    return {"status": "API running"}

@app.get("/download")
def start_download(video_id: str):
    cached = get_filepath(video_id)
    if is_valid_file(cached):
        return JSONResponse({"status": "ready", "url": f"/serve/{video_id}"})
    task = download_audio_task.delay(video_id)
    return JSONResponse({"status": "queued", "task_id": task.id})

@app.get("/status")
def get_status(task_id: str, video_id: str):
    task = celery_app.AsyncResult(task_id)
    if task.state == "PENDING":
        return {"status": "pending"}
    elif task.state == "FAILURE":
        return {"status": "failed", "error": str(task.info)}
    elif task.state == "SUCCESS":
        path = get_filepath(video_id)
        if is_valid_file(path):
            return JSONResponse({"status": "done", "url": f"/serve/{video_id}"})
        return {"status": "done", "note": "file not found"}
    return {"status": task.state}

@app.get("/serve/{video_id}")
def serve_file(video_id: str):
    path = get_filepath(video_id)
    if os.path.exists(path):
        return FileResponse(path, media_type="audio/m4a", filename=f"{video_id}.m4a")
    raise HTTPException(status_code=404, detail="File not found")
