import os
import random
import time
import logging
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from yt_dlp import YoutubeDL
from threading import Thread

# Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("yt-api")

# Directories
DOWNLOAD_DIR = "downloads"
COOKIE_DIR = "cookies"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
os.makedirs(COOKIE_DIR, exist_ok=True)

# FastAPI Setup
app = FastAPI(title="YouTube Audio Downloader API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Constants
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64)...",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X)...",
    "Mozilla/5.0 (X11; Linux x86_64)...",
    "Mozilla/5.0 (iPhone; CPU iPhone OS)..."
]
COMMON_EXTS = ["m4a", "webm", "mp3", "opus"]


def get_random_user_agent():
    return random.choice(USER_AGENTS)

def get_all_cookies():
    return [os.path.join(COOKIE_DIR, f) for f in os.listdir(COOKIE_DIR) if f.endswith(".txt")]

def find_downloaded_file(video_id):
    for ext in COMMON_EXTS:
        path = os.path.join(DOWNLOAD_DIR, f"{video_id}.{ext}")
        if os.path.exists(path) and os.path.getsize(path) > 0:
            return path
    return None

def attempt_download(video_id, cookie_path=None):
    url = f"https://www.youtube.com/watch?v={video_id}"
    output_template = os.path.join(DOWNLOAD_DIR, f"{video_id}.%(ext)s")
    ydl_opts = {
        "format": "bestaudio[ext=m4a]/bestaudio/best",
        "outtmpl": output_template,
        "quiet": True,
        "no_warnings": True,
        "retries": 5,
        "ignoreerrors": True,
        "concurrent_fragment_downloads": 5,
        "noplaylist": True,
        "force_overwrites": True,
        "no_cache_dir": True,
        "addheader": [f"User-Agent:{get_random_user_agent()}"]
    }

    if cookie_path:
        ydl_opts["cookiefile"] = cookie_path

    try:
        with YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        return True
    except Exception as e:
        logger.warning(f"❌ Failed with cookie: {cookie_path} — {str(e)}")
        return False

def download_audio(video_id):
    cookies = get_all_cookies()
    tried = []

    for cookie in cookies:
        if cookie in tried:
            continue
        if attempt_download(video_id, cookie):
            return True
        tried.append(cookie)

    # Fallback without cookies
    if attempt_download(video_id, cookie_path=None):
        return True

    return False

# Auto Clean: Delete incomplete or old files
def auto_cleanup():
    while True:
        now = time.time()
        for file in os.listdir(DOWNLOAD_DIR):
            path = os.path.join(DOWNLOAD_DIR, file)
            if os.path.isfile(path):
                age = now - os.path.getmtime(path)
                size = os.path.getsize(path)
                if age > 3600 or size < 1024 * 1024:
                    try:
                        os.remove(path)
                        logger.info(f"🧹 Deleted: {path} (Age: {int(age)}s, Size: {size} bytes)")
                    except Exception as e:
                        logger.warning(f"❌ Cleanup error: {e}")
        time.sleep(300)

Thread(target=auto_cleanup, daemon=True).start()

# Routes
@app.get("/")
def home():
    return {"status": "YouTube downloader API is running"}

@app.get("/download/song/{video_id}")
def download_and_serve(video_id: str):
    cached_file = find_downloaded_file(video_id)
    if cached_file:
        return FileResponse(cached_file, media_type="audio/mpeg", filename=os.path.basename(cached_file))

    success = download_audio(video_id)
    final_file = find_downloaded_file(video_id)
    if success and final_file:
        return FileResponse(final_file, media_type="audio/mpeg", filename=os.path.basename(final_file))

    raise HTTPException(status_code=500, detail="Download failed. All cookies tried.")
