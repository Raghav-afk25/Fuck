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

# ========================= 🔧 Logging Setup ============================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("api_logs.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("api")

# ========================= 📁 Configs & Globals ============================
DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
COMMON_EXTS = ["m4a", "webm", "mp3", "opus"]

USER_AGENTS = [
    # Chrome - Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.6422.112 Safari/537.36",
    # Chrome - MacOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.6422.113 Safari/537.36",
    # Chrome - Linux
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.6422.114 Safari/537.36",
    # Edge - Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.6422.113 Safari/537.36 Edg/125.0.2535.92",
    # Chrome - Android
    "Mozilla/5.0 (Linux; Android 12; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.6422.112 Mobile Safari/537.36",
    # Chrome - iPhone
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/125.0.6422.112 Mobile/15E148 Safari/604.1",
]

YOUTUBE_CLIENTS = ["mweb", "web", "web_music", "android", "ios", "tv"]

COOKIE_DIR = "cookies"
COOKIE_FILES = [f for f in glob.glob(f"{COOKIE_DIR}/*.txt")]

executor = ThreadPoolExecutor(max_workers=16)
download_locks = {}

# ========================= 🌐 FastAPI Setup ============================
app = FastAPI(title="Ultra Optimized API", version="1.1.5")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ========================= 🧠 Helper Functions ============================

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

    cookie_try_list = COOKIE_FILES + [None]
    random.shuffle(cookie_try_list)

    for cookiefile in cookie_try_list:
        ydl_opts = {
            "format": "bestaudio[ext=m4a]/bestaudio/best",
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
            },
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }
            ],
        }

        try:
            cookie_name = os.path.basename(cookiefile) if cookiefile else "❌ No Cookie"
            logger.info(f"➡️ Trying: {video_id} with cookie: {cookie_name}")
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            if find_file(video_id):
                logger.info(f"✅ Downloaded: {video_id} with cookie: {cookie_name}")
                break
        except Exception as e:
            logger.warning(f"❌ Failed with cookie {cookie_name}: {e}")
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

# ========================= 🚀 API Routes ============================

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
