from fastapi import FastAPI
from fastapi.responses import FileResponse
from celery import Celery
import os
import yt_dlp
import random

app = FastAPI()

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

celery_app = Celery("yt_dl", broker="redis://localhost:6379/0", backend="redis://localhost:6379/0")

COMMON_EXTS = ["m4a", "webm", "mp3", "opus"]
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Mozilla/5.0 (X11; Linux x86_64)",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
]

def get_random_user_agent():
    return random.choice(USER_AGENTS)

def find_file(video_id):
    for ext in COMMON_EXTS:
        path = os.path.join(DOWNLOAD_DIR, f"{video_id}.{ext}")
        if os.path.exists(path) and os.path.getsize(path) > 100000:
            return path
    return None

@celery_app.task
def download_task(video_id):
    url = f"https://www.youtube.com/watch?v={video_id}"
    out = os.path.join(DOWNLOAD_DIR, f"{video_id}.%(ext)s")
    ydl_opts = {
        "format": "bestaudio[ext=m4a]/bestaudio/best",
        "outtmpl": out,
        "quiet": True,
        "no_warnings": True,
        "addheader": [f"User-Agent:{get_random_user_agent()}"],
        "noplaylist": True
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

@app.get("/download/song/{video_id}")
async def download_audio(video_id: str):
    file = find_file(video_id)
    if file:
        return FileResponse(
            path=file,
            media_type="application/octet-stream",  # Force download
            filename=f"{video_id}.mp3",
            headers={
                "Content-Disposition": f'attachment; filename="{video_id}.mp3"'
            }
        )

    # file not ready -> silently queue and return nothing (user sees nothing)
    try:
        download_task.delay(video_id)
    except:
        pass

    # return NOTHING. No JSON, no message, no response
    return ""
