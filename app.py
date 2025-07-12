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

# Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("api.log", encoding="utf-8")]
)
logger = logging.getLogger("yt-fast")

# Constants
DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
COMMON_EXTS = ["mp3", "m4a", "webm", "opus"]
COOKIE_FILES = sorted(glob.glob("cookies/*.txt"))
executor = ThreadPoolExecutor(max_workers=200)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Mozilla/5.0 (X11; Linux x86_64)",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
]

# App Setup
app = FastAPI(title="Turbo YouTube MP3 API", version="6.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

# Utils
def get_random_user_agent():
    return random.choice(USER_AGENTS)

def find_file(video_id):
    for ext in COMMON_EXTS:
        path = os.path.join(DOWNLOAD_DIR, f"{video_id}.{ext}")
        if os.path.exists(path) and os.path.getsize(path) >= 1_000_000:
            return path
        elif os.path.exists(path):
            os.remove(path)
            logger.warning(f"🗑️ Deleted small file (<1MB): {path}")
    return None

def delete_file_later(path: str, delay: int = 3600):
    time.sleep(delay)
    if os.path.exists(path):
        try:
            os.remove(path)
            logger.info(f"🧹 Auto-deleted: {path}")
        except Exception as e:
            logger.warning(f"⚠️ Delete failed: {path} → {e}")

def sync_download(video_id):
    url = f"https://www.youtube.com/watch?v={video_id}"
    outtmpl = os.path.join(DOWNLOAD_DIR, f"{video_id}.%(ext)s")

    cookie_list = COOKIE_FILES.copy()
    random.shuffle(cookie_list)
    cookie_list.append(None)

    for cookie in cookie_list:
        logger.info(f"🍪 Trying cookie: {cookie}")
        ydl_opts = {
            "format": "bestaudio[ext=m4a]/bestaudio/best",
            "outtmpl": outtmpl,
            "quiet": True,
            "no_warnings": True,
            "cookiefile": cookie,
            "retries": 2,
            "fragment_retries": 2,
            "file_access_retries": 1,
            "nocheckcertificate": True,
            "no_cache_dir": True,
            "prefer_insecure": True,
            "ignoreerrors": True,
            "concurrent_fragment_downloads": 15,
            "force_overwrites": True,
            "noplaylist": True,
            "nopart": True,
            "addheader": [f"User-Agent:{get_random_user_agent()}"],
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "128",
            }]
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
        except Exception as e:
            logger.warning(f"❌ Failed with cookie: {cookie} → {str(e)}")
            continue

        # Check if downloaded successfully
        file = find_file(video_id)
        if file:
            break

    # Cleanup temp
    for ext in ["webm", "m4a", "opus"]:
        temp = os.path.join(DOWNLOAD_DIR, f"{video_id}.{ext}")
        if os.path.exists(temp):
            try:
                os.remove(temp)
                logger.info(f"🧹 Removed temp: {temp}")
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
    test_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    result = []
    for cookie in COOKIE_FILES:
        try:
            with yt_dlp.YoutubeDL({
                "quiet": True,
                "cookiefile": cookie,
                "simulate": True,
                "extract_flat": True
            }) as ydl:
                ydl.extract_info(test_url, download=False)
            result.append({"cookie": cookie, "status": "✅ Working"})
        except Exception as e:
            result.append({"cookie": cookie, "status": f"❌ {str(e).splitlines()[0]}"})
    return JSONResponse(result)

@app.get("/")
def root():
    return {"status": "✅ Turbo API Running", "cookies": len(COOKIE_FILES)}
