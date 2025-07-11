import os
import time
import json
from fastapi import FastAPI, Query, HTTPException
from pyrogram import Client
from yt_dlp import YoutubeDL
from dotenv import load_dotenv

# Load environment variables from .env

load_dotenv()

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))

app = FastAPI()

DOWNLOAD_DIR = "downloads"
CACHE_FILE = "cache.json"
COOKIE_FILE = "cookies/cookies.txt"

os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Load download cache

if os.path.exists(CACHE_FILE): with open(CACHE_FILE, "r") as f: cache = json.load(f) else: cache = {}

Telegram Bot Client

bot = Client("tg_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

Download from YouTube using cookies & aria2c

def download_audio(video_id: str): url = f"https://youtube.com/watch?v={video_id}"

ydl_opts = {
    "format": "bestaudio/best",
    "outtmpl": f"{DOWNLOAD_DIR}/%(title).50s.%(ext)s",
    "noplaylist": True,
    "quiet": True,
    "no_warnings": True,
    "prefer_ffmpeg": True,
    "geo_bypass": True,
    "nocheckcertificate": True,
    "socket_timeout": 10,
    "retries": 3,
    "cookiefile": COOKIE_FILE,
    "source_address": "0.0.0.0",
    "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "external_downloader": "aria2c",
    "external_downloader_args": ["-x", "16", "-k", "1M"],
    "postprocessors": [
        {
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }
    ]
}

try:
    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        filename = os.path.splitext(filename)[0] + ".mp3"
        return filename, info.get("title")
except Exception as e:
    print(f"[ERROR] yt-dlp failed: {e}")
    return None, None

# Delete old files to save space

def cleanup_downloads(max_age=3600): now = time.time() for f in os.listdir(DOWNLOAD_DIR): path = os.path.join(DOWNLOAD_DIR, f) if os.path.isfile(path) and now - os.path.getmtime(path) > max_age: os.remove(path)

@app.get("/download") async def download(video_id: str = Query(..., min_length=6)): cleanup_downloads()

if video_id in cache:
    return {
        "status": "cached",
        "telegram_file_id": cache[video_id]
    }

filename, title = download_audio(video_id)
if not filename:
    raise HTTPException(status_code=400, detail="Download failed or video is blocked")

await bot.start()
try:
    sent = await bot.send_audio(
        chat_id=CHANNEL_ID,
        audio=filename,
        caption=f"\ud83c\udfb5 {title or 'Unknown'}"
    )
    file_id = sent.audio.file_id
    cache[video_id] = file_id
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f)
    return {
        "status": "uploaded",
        "telegram_file_id": file_id
    }
except Exception as e:
    raise HTTPException(status_code=500, detail=f"Telegram upload failed: {e}")
finally:
    await bot.stop()

