import os
import glob
import logging
import asyncio
import random
import time
import platform
from datetime import datetime
from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from celery import Celery
import yt_dlp

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("api_logs.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("api")

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
COMMON_EXTS = ["m4a", "webm", "mp3", "opus"]
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
    "Mozilla/5.0 (X11; Linux x86_64)"
]
YOUTUBE_CLIENTS = ["mweb", "web", "web_music", "android", "ios", "tv"]

app = FastAPI(title="Celery Boosted API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

celery_app = Celery("yt_dl", broker="redis://localhost:6379/0", backend="redis://localhost:6379/0")

def get_random_user_agent():
    return random.choice(USER_AGENTS)

def find_file(video_id):
    for ext in COMMON_EXTS:
        path = os.path.join(DOWNLOAD_DIR, f"{video_id}.{ext}")
        if os.path.exists(path) and os.path.getsize(path) > 100000:
            return path
    return None

def delayed_delete(path, delay=3600):
    try:
        time.sleep(delay)
        if os.path.exists(path):
            os.remove(path)
    except Exception as e:
        print(f"❌ Delete failed: {e}")

@celery_app.task
def download_audio_task(video_id):
    url = f"https://www.youtube.com/watch?v={video_id}"
    out = os.path.join(DOWNLOAD_DIR, f"{video_id}.%(ext)s")

    ydl_opts = {
        "format": "bestaudio[ext=m4a]/bestaudio/best",
        "outtmpl": out,
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
        downloaded_file = find_file(video_id)
        if downloaded_file:
            return {"status": "completed", "file": downloaded_file}
        return {"status": "failed", "error": "No valid file found"}
    except Exception as e:
        return {"status": "failed", "error": str(e)}

@app.get("/download/song/{video_id}")
async def download_audio(video_id: str, background_tasks: BackgroundTasks):
    file = find_file(video_id)
    if file:
        background_tasks.add_task(delayed_delete, file, delay=3600)
        return FileResponse(
            path=file,
            media_type="application/octet-stream",
            filename=f"{video_id}.mp3",
            headers={"Content-Disposition": f'attachment; filename="{video_id}.mp3"'},
            background=background_tasks
        )

    try:
        download_audio_task.delay(video_id)
    except:
        pass

    return ""

@app.get("/")
def root():
    return {"status": "running ✅"}
