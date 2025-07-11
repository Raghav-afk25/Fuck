# app.py

import os
import json
import asyncio
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from yt_dlp import YoutubeDL
from dotenv import load_dotenv
from pyrogram import Client

# Load environment variables from .env
load_dotenv()

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))

# Constants
DOWNLOAD_DIR = "downloads"
CACHE_FILE = "cache.json"
COOKIE_FILE = "cookies/cookies.txt"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Load download cache
if os.path.exists(CACHE_FILE):
    with open(CACHE_FILE, "r") as f:
        cache = json.load(f)
else:
    cache = {}

# Telegram Bot Client
app_client = Client("uploader", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# FastAPI App
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# YouTubeDL Options
def get_ydl_opts(filename: str):
    return {
        "format": "bestaudio/best",
        "outtmpl": filename,
        "quiet": True,
        "nocheckcertificate": True,
        "noplaylist": True,
        "cookiefile": COOKIE_FILE,
    }

# Download route
@app.get("/download")
async def download(video_id: str):
    if video_id in cache:
        return {"status": "cached", "file": cache[video_id]}

    filename = os.path.join(DOWNLOAD_DIR, f"{video_id}.mp3")
    ydl_opts = get_ydl_opts(filename)

    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=True)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error: {str(e)}")

    if not os.path.exists(filename):
        raise HTTPException(status_code=500, detail="Download failed")

    # Upload to Telegram and get file_id
    async with app_client:
        sent = await app_client.send_audio(CHANNEL_ID, filename)
        file_id = sent.audio.file_id

    # Save to cache
    cache[video_id] = file_id
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f)

    return {"status": "downloaded", "file": file_id}

# Serve downloaded file
@app.get("/file/{video_id}")
def get_file(video_id: str):
    path = os.path.join(DOWNLOAD_DIR, f"{video_id}.mp3")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path)
