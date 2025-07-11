import os
import glob
import logging
import asyncio
import argparse
import random
import json
import time
import platform
from datetime import datetime
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
import functools
import yt_dlp

# Try to import psutil for system monitoring
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    psutil = None

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
MAX_WORKERS = int(os.environ.get("MAX_WORKERS", "50"))
DOMAIN = os.environ.get("API_DOMAIN", "https://kristineapi.com")

PO_TOKEN_ENABLED = os.environ.get("PO_TOKEN_ENABLED", "false").lower() == "true"
PO_TOKEN_PROVIDER = os.environ.get("PO_TOKEN_PROVIDER", "none")

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
    "Mozilla/5.0 (Linux; Android 14; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Mobile/15E148 Safari/604.1",
]

YOUTUBE_CLIENTS = ["mweb", "web", "web_music", "android", "ios", "tv"]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("api_logs.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("api")

app = FastAPI(title="YouTube Audio Downloader API", version="3.0.0")
COMMON_EXTS = ["m4a", "webm", "mp3", "opus"]

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

def download_audio_subprocess(video_id):
    url = f"https://www.youtube.com/watch?v={video_id}"
    output_template = os.path.join(DOWNLOAD_DIR, f"{video_id}.%(ext)s")
    format_strategies = ["bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio/best"]

    for i, format_strategy in enumerate(format_strategies):
        ydl_opts = {
            "format": format_strategy,
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
            "concurrent_fragment": 1,
            "force_overwrites": True,
            "noplaylist": True,
            "extractaudio": True,
            "audioformat": "best",
            "audioquality": "0",
            "addheader": [
                f"User-Agent:{get_random_user_agent()}"
            ],
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
                return {"success": True, "file": downloaded_file}
        except Exception as e:
            logger.error(f"Download error for video_id={video_id}, strategy {i+1}: {e}")
            continue
    return {"success": False, "error": "all strategies failed"}

@app.get("/download")
async def download(video_id: str):
    result = await asyncio.to_thread(download_audio_subprocess, video_id)
    if result["success"]:
        return FileResponse(result["file"], media_type='audio/mpeg')
    else:
        raise HTTPException(status_code=500, detail=result["error"])

@app.get("/")
def root():
    return {"status": "API running"}
