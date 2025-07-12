import os
import logging
import random
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from celery import Celery
import yt_dlp

# 🧾 Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("api_logs.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("api")

# 📁 Setup
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

# 🚀 FastAPI App
app = FastAPI(title="YouTube Audio Downloader", version="1.0.0")

# 🌍 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 🧠 Celery App
celery_app = Celery("yt_dl_tasks", broker="redis://localhost:6379/0", backend="redis://localhost:6379/0")

# 🔍 Utils
def get_random_user_agent():
    return random.choice(USER_AGENTS)

def find_downloaded_file(video_id):
    for ext in COMMON_EXTS:
        candidate = os.path.join(DOWNLOAD_DIR, f"{video_id}.{ext}")
        if os.path.exists(candidate) and os.path.getsize(candidate) > 0:
            return candidate
    return None

def validate_downloaded_file(file_path, video_id):
    return os.path.exists(file_path) and os.path.getsize(file_path) > 100000

# 🎯 Celery Background Download Task
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
            return {"status": "completed", "file_path": downloaded_file}
        return {"status": "failed", "error": "Download failed or file invalid."}
    except Exception as e:
        return {"status": "failed", "error": str(e)}

# ✅ /download/song/{video_id} — Exactly Like You Wanted
@app.get("/download/song/{video_id}")
async def song_download_like_prod(video_id: str):
    cached_file = find_downloaded_file(video_id)

    if cached_file and validate_downloaded_file(cached_file, video_id):
        return FileResponse(
            path=cached_file,
            media_type="application/octet-stream",
            filename=f"{video_id}.mp3",
            headers={
                "Content-Disposition": f"attachment; filename={video_id}.mp3"
            }
        )

    # 🔇 Silent background task (no message if file not ready)
    try:
        download_audio_task.delay(video_id)
    except Exception as e:
        logger.error(f"Celery task error: {e}")
        pass

    return  # Silent fallback (no 202, no error)

# 🫡 Healthcheck
@app.get("/")
def root():
    return {"status": "running"}
