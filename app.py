import os
import logging
import random
import asyncio
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, FileResponse
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
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Mobile/15E148 Safari/604.1"
]
YOUTUBE_CLIENTS = ["mweb", "web", "web_music", "android", "ios", "tv"]

# FastAPI app
app = FastAPI(title="YT Downloader API", version="5.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Celery setup
celery_app = Celery("yt_dl_tasks", broker="redis://localhost:6379/0", backend="redis://localhost:6379/0")

# Utils
def get_random_user_agent():
    return random.choice(USER_AGENTS)

def find_downloaded_file(video_id):
    for ext in COMMON_EXTS:
        file_path = os.path.join(DOWNLOAD_DIR, f"{video_id}.{ext}")
        if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
            return file_path
    return None

def validate_file(path):
    return os.path.exists(path) and os.path.getsize(path) > 100000

def get_marker_file(video_id):
    return os.path.join(DOWNLOAD_DIR, f"{video_id}_ready.txt")

# Celery Task
@celery_app.task(name="download_audio_task")
def download_audio_task(video_id):
    url = f"https://www.youtube.com/watch?v={video_id}"
    output = os.path.join(DOWNLOAD_DIR, f"{video_id}.%(ext)s")
    opts = {
        "format": "bestaudio[ext=m4a]/bestaudio/best",
        "outtmpl": output,
        "quiet": True,
        "no_warnings": True,
        "retries": 10,
        "fragment_retries": 10,
        "concurrent_fragment_downloads": 5,
        "force_overwrites": True,
        "noplaylist": True,
        "addheader": [f"User-Agent:{get_random_user_agent()}"],
        "extractor_args": {"youtube": {"player_client": random.choice(YOUTUBE_CLIENTS)}}
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])
        fpath = find_downloaded_file(video_id)
        if fpath and validate_file(fpath):
            with open(get_marker_file(video_id), "w") as f:
                f.write(fpath)
            return {"status": "completed", "file_path": fpath}
        return {"status": "failed", "error": "Download failed or invalid."}
    except Exception as e:
        return {"status": "failed", "error": str(e)}

# Routes
@app.get("/")
def root():
    return {"status": "API is running"}

@app.get("/download")
async def start_download(video_id: str):
    file = find_downloaded_file(video_id)
    if file and validate_file(file):
        return {"status": "ready", "url": f"/serve/{video_id}"}
    task = download_audio_task.delay(video_id)
    return {"status": "queued", "task_id": task.id}

@app.get("/status")
async def get_status(task_id: str, video_id: str):
    task = celery_app.AsyncResult(task_id)
    if task.state == "PENDING":
        return {"status": "pending"}
    if task.state == "FAILURE":
        return {"status": "failed", "error": str(task.info)}
    if task.state == "SUCCESS":
        marker = get_marker_file(video_id)
        if os.path.exists(marker):
            with open(marker) as f:
                fpath = f.read().strip()
            if os.path.exists(fpath):
                return {"status": "ready", "url": f"/serve/{video_id}"}
        return {"status": "done", "note": "file missing"}
    return {"status": task.state}

@app.get("/serve/{video_id}")
async def serve_file(video_id: str):
    fpath = find_downloaded_file(video_id)
    if fpath and validate_file(fpath):
        return FileResponse(fpath, media_type="audio/mpeg")
    raise HTTPException(status_code=404, detail="File not found")
