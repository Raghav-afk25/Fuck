import os
import random
import asyncio
import logging
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from celery import Celery
from yt_dlp import YoutubeDL

# === Logging Setup ===
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("api_logs.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("api")

# === Constants ===
DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

COMMON_EXTS = ["m4a", "webm", "mp3", "opus"]
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Mobile/15E148 Safari/604.1"
]
YOUTUBE_CLIENTS = ["web", "web_music", "mweb", "android", "ios", "tv"]

# === FastAPI Setup ===
app = FastAPI(title="DeadlineTech Downloader", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# === Celery Setup ===
celery_app = Celery("yt_dl_tasks", broker="redis://localhost:6379/0", backend="redis://localhost:6379/0")


# === Helper Functions ===
def get_random_user_agent():
    return random.choice(USER_AGENTS)

def find_downloaded_file(video_id):
    for ext in COMMON_EXTS:
        path = os.path.join(DOWNLOAD_DIR, f"{video_id}.{ext}")
        if os.path.exists(path) and os.path.getsize(path) > 100000:
            return path
    return None

def get_marker_file(video_id):
    return os.path.join(DOWNLOAD_DIR, f"{video_id}_ready.txt")


# === Celery Task ===
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
        "prefer_insecure": True,
        "no_cache_dir": True,
        "ignoreerrors": True,
        "noplaylist": True,
        "concurrent_fragment_downloads": 5,
        "force_overwrites": True,
        "addheader": [f"User-Agent:{get_random_user_agent()}"],
        "extractor_args": {
            "youtube": {
                "player_client": random.choice(YOUTUBE_CLIENTS)
            }
        }
    }

    try:
        with YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        path = find_downloaded_file(video_id)
        if path:
            with open(get_marker_file(video_id), "w") as f:
                f.write(path)
            return {"status": "completed", "file": path}
        else:
            return {"status": "failed", "error": "file not found"}

    except Exception as e:
        return {"status": "failed", "error": str(e)}


# === API Endpoints ===

@app.get("/")
def home():
    return {"status": "API Running", "uptime": f"{os.uname().sysname} {os.uname().release}"}

@app.get("/song/{video_id}")
async def song_stream(video_id: str):
    cached = find_downloaded_file(video_id)
    if cached:
        return FileResponse(cached, media_type="audio/mpeg")

    task = download_audio_task.delay(video_id)
    timeout = 30  # seconds
    waited = 0

    while waited < timeout:
        result = celery_app.AsyncResult(task.id)
        if result.ready() and result.successful():
            cached = find_downloaded_file(video_id)
            if cached:
                return FileResponse(cached, media_type="audio/mpeg")
        await asyncio.sleep(1)
        waited += 1

    raise HTTPException(status_code=202, detail="Still processing, try again later")
