import os
import glob
import logging
import asyncio
import random
import time
from threading import Lock
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import yt_dlp
from concurrent.futures import ThreadPoolExecutor

# Logging setup
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

COOKIE_DIR = "cookies"
COOKIE_FILES = [f for f in glob.glob(f"{COOKIE_DIR}/*.txt")]

executor = ThreadPoolExecutor(max_workers=16)
download_locks = {}

# FastAPI setup
app = FastAPI(title="Ultra Optimized API", version="1.1.4")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[""],
    allow_credentials=True,
    allow_methods=[""],
    allow_headers=["*"],
)

def get_random_user_agent():
    return random.choice(USER_AGENTS)

def find_file(video_id):
    for ext in COMMON_EXTS:
        path = os.path.join(DOWNLOAD_DIR, f"{video_id}.{ext}")
        if os.path.exists(path):
            size = os.path.getsize(path)
            if size >= 200_000:
                return path
            else:
                logger.warning(f"⚠️ Skipping too small file (<200KB): {path}")
    return None

def sync_download(video_id):
    url = f"https://www.youtube.com/watch?v={video_id}"
    out = os.path.join(DOWNLOAD_DIR, f"{video_id}.%(ext)s")

    for cookiefile in COOKIE_FILES + [None]:
        ydl_opts = {
            "format": "bestaudio[ext=m4a]",
            "outtmpl": out,
            "quiet": True,
            "no_warnings": True,
            "cookiefile": cookiefile,
            "retries": 3,
            "ignoreerrors": True,
            "noplaylist": True,
            "nopart": True,
            "no_cache_dir": True,
            "addheader": [f"User-Agent:{get_random_user_agent()}"],
            "extractor_args": {
                "youtube": {
                    "player_client": random.choice(YOUTUBE_CLIENTS)
                }
            }
        }

        try:
            logger.info(f"➡️ Downloading: {video_id} with cookie: {cookiefile}")
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            if find_file(video_id):
                logger.info(f"✅ Success: {video_id}")
                break
        except Exception as e:
            logger.warning(f"❌ Failed with {cookiefile}: {str(e)}")
            continue

async def delete_file_later(path: str, delay: int = 3600):
    await asyncio.sleep(delay)
    try:
        if os.path.exists(path):
            size = os.path.getsize(path)
            if size < 1_000_000:
                os.remove(path)
                logger.info(f"🧹 Deleted incomplete (under 1MB) file: {path}")
            elif time.time() - os.path.getmtime(path) >= 3600:
                os.remove(path)
                logger.info(f"🧹 Deleted old file: {path}")
    except Exception as e:
        logger.warning(f"⚠️ Failed deleting {path}: {e}")

@app.get("/download/song/{video_id}")
async def download_song(video_id: str, background_tasks: BackgroundTasks):
    logger.info(f"📥 API Hit: {video_id}")
    file = find_file(video_id)
    if file:
        background_tasks.add_task(delete_file_later, file)
        return FileResponse(
            path=file,
            media_type="application/octet-stream",
            filename=f"{video_id}.mp3",
            headers={"Content-Disposition": f'attachment; filename="{video_id}.mp3"'}
        )

    lock = download_locks.setdefault(video_id, Lock())
    with lock:
        file = find_file(video_id)
        if file:
            background_tasks.add_task(delete_file_later, file)
            return FileResponse(
                path=file,
                media_type="application/octet-stream",
                filename=f"{video_id}.mp3",
                headers={"Content-Disposition": f'attachment; filename="{video_id}.mp3"'}
            )

        loop = asyncio.get_event_loop()
        await asyncio.sleep(random.uniform(0.05, 0.2))  # minor stagger
        await loop.run_in_executor(executor, sync_download, video_id)

        file = find_file(video_id)
        if not file:
            raise HTTPException(status_code=500, detail="Download failed")

        background_tasks.add_task(delete_file_later, file)
        return FileResponse(
            path=file,
            media_type="application/octet-stream",
            filename=f"{video_id}.mp3",
            headers={"Content-Disposition": f'attachment; filename="{video_id}.mp3"'}
        )

@app.get("/cookie-health")
async def cookie_health_check():
    sample_url = "https://www.youtube.com/watch?v=2Vv-BfVoq4g"
    results = []
    for cookie in COOKIE_FILES:
        ydl_opts = {
            "quiet": True,
            "cookiefile": cookie,
            "simulate": True,
            "skip_download": True,
            "no_warnings": True,
            "extract_flat": True,
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.extract_info(sample_url, download=False)
            results.append({"cookie": os.path.basename(cookie), "status": "✅ Working"})
        except Exception as e:
            results.append({
                "cookie": os.path.basename(cookie),
                "status": f"❌ Dead - {str(e).splitlines()[0]}"
            })
    return JSONResponse(results)

@app.get("/")
def root():
    return {"status": "Ultra Optimized API 🧠💨"}
