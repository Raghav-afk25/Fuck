import os
import glob
import logging
import asyncio
import random
import time
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import yt_dlp
from concurrent.futures import ThreadPoolExecutor

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("api.log", encoding="utf-8")]
)
logger = logging.getLogger("yt-api")

# Directories
DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Constants
COMMON_EXTS = ["mp3", "m4a", "webm", "opus"]
COOKIE_FILES = sorted(glob.glob("cookies/*.txt"))
executor = ThreadPoolExecutor(max_workers=100)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Mozilla/5.0 (X11; Linux x86_64)",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
]

YOUTUBE_CLIENTS = ["web", "web_music", "android", "ios", "tv", "mweb"]

# FastAPI setup
app = FastAPI(title="Turbo YT MP3 API", version="5.5")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"]
)

def get_random_user_agent():
    return random.choice(USER_AGENTS)

def find_file(video_id):
    for ext in COMMON_EXTS:
        path = os.path.join(DOWNLOAD_DIR, f"{video_id}.{ext}")
        if os.path.exists(path):
            if os.path.getsize(path) >= 1_000_000:
                return path
            else:
                os.remove(path)
                logger.warning(f"🗑️ Deleted broken file (<1MB): {path}")
    return None

def delete_file_later(path: str, delay: int = 3600):
    time.sleep(delay)
    if os.path.exists(path):
        try:
            os.remove(path)
            logger.info(f"🧹 Auto-deleted: {path}")
        except Exception as e:
            logger.warning(f"⚠️ Failed auto-delete: {path} - {e}")

def sync_download(video_id):
    url = f"https://www.youtube.com/watch?v={video_id}"
    outtmpl = os.path.join(DOWNLOAD_DIR, f"{video_id}.%(ext)s")

    # Cookie shuffle logic
    shuffled = COOKIE_FILES.copy()
    random.shuffle(shuffled)
    first = random.choice(shuffled)
    try_order = [first] + [c for c in shuffled if c != first] + [None]

    for cookiefile in try_order:
        logger.info(f"🍪 Trying cookie: {cookiefile}")
        ydl_opts = {
            "format": "bestaudio[ext=m4a]/bestaudio/best",
            "outtmpl": outtmpl,
            "quiet": True,
            "no_warnings": True,
            "cookiefile": cookiefile,
            "retries": 5,
            "fragment_retries": 5,
            "file_access_retries": 3,
            "nocheckcertificate": True,
            "prefer_insecure": True,
            "no_cache_dir": True,
            "ignoreerrors": True,
            "concurrent_fragment_downloads": 10,
            "force_overwrites": True,
            "noplaylist": True,
            "nopart": True,
            "addheader": [f"User-Agent:{get_random_user_agent()}"],
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }],
            "extractor_args": {
                "youtube": {
                    "player_client": random.choice(YOUTUBE_CLIENTS)
                }
            }
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
        except Exception as e:
            logger.warning(f"❌ Cookie failed: {cookiefile} → {str(e)}")
            continue

        for ext in COMMON_EXTS:
            path = os.path.join(DOWNLOAD_DIR, f"{video_id}.{ext}")
            if os.path.exists(path):
                size = os.path.getsize(path)
                if size > 1_000_000:
                    logger.info(f"✅ Downloaded: {path} (Size: {size/1024/1024:.2f} MB)")
                    break
                else:
                    os.remove(path)
                    logger.warning(f"🗑️ Deleted broken file: {path}")
        else:
            continue
        break

    # Clean temp
    for ext in ["webm", "m4a", "opus"]:
        temp = os.path.join(DOWNLOAD_DIR, f"{video_id}.{ext}")
        if os.path.exists(temp):
            try:
                os.remove(temp)
                logger.info(f"🧹 Removed temp file: {temp}")
            except:
                pass

@app.get("/download/song/{video_id}")
async def download_song(video_id: str, background_tasks: BackgroundTasks):
    file = find_file(video_id)
    if not file:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(executor, sync_download, video_id)
        file = find_file(video_id)
        if not file:
            raise HTTPException(status_code=500, detail="Download failed.")
    background_tasks.add_task(delete_file_later, file)
    return FileResponse(
        path=file,
        media_type="application/octet-stream",
        filename=f"{video_id}.mp3",
        headers={"Content-Disposition": f'attachment; filename="{video_id}.mp3"'}
    )

@app.get("/cookie-health")
async def cookie_health():
    test_url = "https://www.youtube.com/watch?v=2Vv-BfVoq4g"
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
                ydl.extract_info(test_url, download=False)
            results.append({"cookie": os.path.basename(cookie), "status": "✅ Working"})
        except Exception as e:
            results.append({"cookie": os.path.basename(cookie), "status": f"❌ {str(e).splitlines()[0]}"})
    return JSONResponse(results)

@app.get("/")
def root():
    return {"status": "✅ Turbo YouTube MP3 API Running"}
