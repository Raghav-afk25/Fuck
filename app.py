import os
import glob
import logging
import time
import random
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import yt_dlp

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("fastapi.log", encoding="utf-8")
    ]
)
logger = logging.getLogger("yt-turbo")

# Constants
DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
COMMON_EXTS = ["mp3", "m4a", "webm", "opus"]
COOKIE_FILES = sorted(glob.glob("cookies/*.txt"))

# FastAPI app
app = FastAPI(title="VC-Turbo YouTube API", version="7.1")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 🔁 Clean only small or old files (safe)
def clean_old_files():
    now = time.time()
    for file in os.listdir(DOWNLOAD_DIR):
        path = os.path.join(DOWNLOAD_DIR, file)
        try:
            if os.path.isfile(path):
                size = os.path.getsize(path)
                age = now - os.path.getmtime(path)
                if size < 1_000_000 or age > 3600:
                    os.remove(path)
                    logger.info(f"🧹 Cleaned: {path} (Size: {size}, Age: {age:.0f}s)")
        except FileNotFoundError:
            logger.warning(f"⚠️ File already deleted: {path}")
        except Exception as e:
            logger.error(f"❌ Failed to delete {path}: {e}")

# ✅ Find if valid downloaded file exists
def find_file(video_id):
    for ext in COMMON_EXTS:
        path = os.path.join(DOWNLOAD_DIR, f"{video_id}.{ext}")
        if os.path.exists(path) and os.path.getsize(path) >= 1_000_000:
            return path
        elif os.path.exists(path):
            try:
                os.remove(path)
                logger.warning(f"🗑️ Deleted too small (<1MB): {path}")
            except:
                pass
    return None

# ⚡ Fast & direct download
def download_song(video_id):
    url = f"https://www.youtube.com/watch?v={video_id}"
    outtmpl = os.path.join(DOWNLOAD_DIR, f"{video_id}.%(ext)s")

    cookie = COOKIE_FILES[0] if COOKIE_FILES else None
    fallback = COOKIE_FILES[1] if len(COOKIE_FILES) > 1 else None

    for ck in [cookie, fallback, None]:
        opts = {
            "format": "bestaudio[ext=m4a]/bestaudio/best",
            "outtmpl": outtmpl,
            "quiet": True,
            "no_warnings": True,
            "cookiefile": ck,
            "retries": 1,
            "fragment_retries": 1,
            "file_access_retries": 1,
            "nocheckcertificate": True,
            "prefer_insecure": True,
            "ignoreerrors": True,
            "noplaylist": True,
            "nopart": True,
            "no_cache_dir": True,
            "concurrent_fragment_downloads": 10,
            "force_overwrites": True,
            "addheader": ["User-Agent:Mozilla/5.0"],
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "128"
            }]
        }

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])
        except Exception as e:
            logger.warning(f"❌ Download failed with {ck}: {e}")
            continue

        found = find_file(video_id)
        if found:
            return found

    raise Exception("All attempts failed or file invalid.")

# 🧠 Main endpoint for VC bots
@app.get("/download/song/{video_id}")
def trigger_download(video_id: str):
    clean_old_files()

    file = find_file(video_id)
    if not file:
        try:
            file = download_song(video_id)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    return FileResponse(
        file,
        media_type="application/octet-stream",
        filename=f"{video_id}.mp3",
        headers={"Content-Disposition": f'attachment; filename="{video_id}.mp3"'}
    )

# Check cookie status
@app.get("/cookie-health")
def cookie_status():
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
            result.append({"cookie": os.path.basename(cookie), "status": "✅ Working"})
        except Exception as e:
            result.append({"cookie": os.path.basename(cookie), "status": f"❌ {str(e).splitlines()[0]}"})
    return JSONResponse(result)

# Root
@app.get("/")
def root():
    return {"status": "✅ API Live", "cookies": len(COOKIE_FILES)}
