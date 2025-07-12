import os
import glob
import time
import logging
import random
import threading
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
import yt_dlp

# === Config ===
DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
COMMON_EXTS = ["mp3", "m4a", "webm", "opus"]
COOKIE_FILES = sorted(glob.glob("cookies/*.txt"))

# === Logging ===
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ytapi")

# === FastAPI App ===
app = FastAPI(title="Fast VC Downloader API", version="5.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"]
)

# === Helpers ===
def find_file(video_id):
    for ext in COMMON_EXTS:
        path = os.path.join(DOWNLOAD_DIR, f"{video_id}.{ext}")
        if os.path.exists(path) and os.path.getsize(path) >= 1_000_000:
            return path
    return None

def download_song(video_id):
    url = f"https://www.youtube.com/watch?v={video_id}"
    outtmpl = os.path.join(DOWNLOAD_DIR, f"{video_id}.%(ext)s")

    for cookie in COOKIE_FILES + [None]:
        opts = {
            "format": "bestaudio[ext=m4a]/bestaudio/best",
            "outtmpl": outtmpl,
            "quiet": True,
            "no_warnings": True,
            "cookiefile": cookie,
            "retries": 1,
            "fragment_retries": 1,
            "file_access_retries": 1,
            "nopart": True,
            "noplaylist": True,
            "prefer_insecure": True,
            "concurrent_fragment_downloads": 10,
            "ignoreerrors": True,
            "no_cache_dir": True,
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
            logger.warning(f"❌ Cookie failed ({cookie}): {str(e).splitlines()[0]}")
            continue

        final = find_file(video_id)
        if final:
            return final

    raise Exception("❌ Download failed with all cookies")

# === Auto-cleaner ===
def clean_downloads():
    while True:
        now = time.time()
        for file in os.listdir(DOWNLOAD_DIR):
            path = os.path.join(DOWNLOAD_DIR, file)
            try:
                if not os.path.isfile(path) or file.endswith(".temp.m4a"):
                    continue

                size = os.path.getsize(path)
                age = now - os.path.getmtime(path)

                # Don't delete fresh files
                if age < 60:
                    continue

                if size < 1_000_000 and age > 60:
                    os.remove(path)
                    logger.info(f"🧹 Deleted incomplete: {path}")
                elif age > 3600:
                    os.remove(path)
                    logger.info(f"🧹 Deleted old: {path}")
            except Exception as e:
                logger.warning(f"⚠️ Cleanup error: {e}")
        time.sleep(60)

threading.Thread(target=clean_downloads, daemon=True).start()

# === Routes ===
@app.get("/")
def root():
    return {"status": "✅ Running", "cookies": COOKIE_FILES}

@app.get("/download/song/{video_id}")
def trigger_download(video_id: str):
    file = find_file(video_id)
    if not file:
        try:
            file = download_song(video_id)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # Verify file exists & big enough
    if not os.path.exists(file) or os.path.getsize(file) < 500000:
        raise HTTPException(status_code=404, detail="File not ready or too small")

    return FileResponse(
        file,
        media_type="application/octet-stream",
        filename=os.path.basename(file),
        headers={"Content-Disposition": f'attachment; filename="{os.path.basename(file)}"'}
    )
