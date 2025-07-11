import os
import json
import time
import asyncio
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pyrogram import Client
from yt_dlp import YoutubeDL

from dotenv import load_dotenv
load_dotenv()

# 🔧 Config from .env
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")  # must be str like '-100123...'

# 🗂️ Paths
DOWNLOAD_DIR = "downloads"
CACHE_FILE = "cache.json"
COOKIE_FILE = "cookies/cookies.txt"

os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# ⚙️ Cache init
cache = {}
if os.path.exists(CACHE_FILE):
    with open(CACHE_FILE, "r") as f:
        try:
            cache = json.load(f)
        except:
            cache = {}

# 📦 FastAPI
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 🤖 Pyrogram Bot
app_client = Client("bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

@app.on_event("startup")
async def startup():
    await app_client.start()

@app.on_event("shutdown")
async def shutdown():
    await app_client.stop()

# 📥 Download endpoint
@app.get("/download")
async def download(video_id: str):
    if video_id in cache:
        filename = cache[video_id]
        return FileResponse(filename, media_type="audio/mpeg")

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": f"{DOWNLOAD_DIR}/%(title)s.%(ext)s",
        "noplaylist": True,
        "quiet": True,
        "nocheckcertificate": True,
        "cookies": COOKIE_FILE,
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "320",
        }],
    }

    url = f"https://www.youtube.com/watch?v={video_id}"
    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info).replace(".webm", ".mp3").replace(".m4a", ".mp3")

    # ✅ Send to Telegram channel (with peer resolution)
    peer = await app_client.resolve_peer(CHANNEL_ID)
    await app_client.send_audio(peer, filename)

    # 🔐 Cache this result
    cache[video_id] = filename
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f)

    return FileResponse(filename, media_type="audio/mpeg")
