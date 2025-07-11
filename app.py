from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
import os, asyncio, time, json
from yt_dlp import YoutubeDL
from pyrogram import Client
from config import API_ID, API_HASH, BOT_TOKEN, CHANNEL_ID

app = FastAPI()
DOWNLOAD_DIR = "downloads"
CACHE_DB = "cache.json"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Load/Save DB
if os.path.exists(CACHE_DB):
    with open(CACHE_DB, "r") as f:
        cache = json.load(f)
else:
    cache = {}

def save_cache():
    with open(CACHE_DB, "w") as f:
        json.dump(cache, f)

client = Client("tg_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

YDL_OPTS = {
    "format": "bestaudio/best",
    "outtmpl": f"{DOWNLOAD_DIR}/%(id)s.%(ext)s",
    "quiet": True,
    "no_warnings": True,
    "geo_bypass": True,
    "nocheckcertificate": True,
    "noplaylist": True,
    "forceipv4": True,
    "retries": 5,
    "fragment_retries": 5,
    "concurrent_fragment_downloads": 5,
    "external_downloader": "aria2c",
    "external_downloader_args": {
        "aria2c": [
            "--summary-interval=0",
            "--min-split-size=1M",
            "--split=5",
            "--max-connection-per-server=5",
            "--timeout=30",
            "--retry-wait=3",
            "--max-tries=5"
        ]
    },
    "user_agent": "Mozilla/5.0",
    "postprocessors": [{
        "key": "FFmpegExtractAudio",
        "preferredcodec": "mp3",
        "preferredquality": "192",
    }]
}

@app.get("/download")
async def download_video_id(video_id: str):
    if video_id in cache:
        print(f"[CACHE] Found in Telegram: {video_id}")
        return {"status": "cached", "telegram_file_id": cache[video_id]}
    
    url = f"https://www.youtube.com/watch?v={video_id}"
    try:
        loop = asyncio.get_event_loop()
        path = await loop.run_in_executor(None, lambda: _download(url))
        if not path:
            raise HTTPException(status_code=404, detail="Download failed.")
        
        async with client:
            sent = await client.send_audio(CHANNEL_ID, path, caption=f"🎵 Cached: {video_id}")
            file_id = sent.audio.file_id
            cache[video_id] = file_id
            save_cache()
            print(f"[UPLOAD] Uploaded {video_id} to channel and cached")
        
        return FileResponse(path, filename=os.path.basename(path))

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")

def _download(url: str):
    with YoutubeDL(YDL_OPTS) as ydl:
        info = ydl.extract_info(url, download=True)
        file_id = info.get("id")
        path = os.path.join(DOWNLOAD_DIR, f"{file_id}.mp3")
        return path if os.path.exists(path) else None

# Cleanup same as before
def cleanup_downloads(max_age_sec=3600):
    now = time.time()
    for f in os.listdir(DOWNLOAD_DIR):
        path = os.path.join(DOWNLOAD_DIR, f)
        if os.path.isfile(path):
            if now - os.path.getmtime(path) > max_age_sec:
                os.remove(path)
                print(f"[CLEANUP] Deleted: {path}")

@app.on_event("startup")
async def start_cleanup_loop():
    asyncio.create_task(auto_cleanup())

async def auto_cleanup():
    while True:
        cleanup_downloads()
        await asyncio.sleep(1800)
