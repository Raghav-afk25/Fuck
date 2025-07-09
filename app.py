from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from yt_dlp import YoutubeDL
import os
import asyncio
import time
import glob

app = FastAPI()

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

def cleanup_downloads(max_age_sec=3600):
    now = time.time()
    for file in os.listdir(DOWNLOAD_DIR):
        path = os.path.join(DOWNLOAD_DIR, file)
        if os.path.isfile(path) and now - os.path.getmtime(path) > max_age_sec:
            try:
                os.remove(path)
            except:
                pass

@app.get("/download/song/{video_id}")
async def download_song(video_id: str):
    try:
        filename_pattern = os.path.join(DOWNLOAD_DIR, f"{video_id}.*")
        matched_files = glob.glob(filename_pattern)

        # ✅ Return already existing file
        if matched_files:
            return FileResponse(
                path=matched_files[0],
                filename=os.path.basename(matched_files[0]),
                media_type="audio/mp4"
            )

        asyncio.create_task(asyncio.to_thread(cleanup_downloads))

        cookies_path = os.path.abspath("cookies/cookies.txt")
        if not os.path.exists(cookies_path):
            raise HTTPException(status_code=500, detail="❌ cookies.txt not found")

        ydl_opts = {
            "format": "bestaudio/best",
            "quiet": True,
            "cookiefile": cookies_path,
            "outtmpl": os.path.join(DOWNLOAD_DIR, f"{video_id}.%(ext)s"),
            "noplaylist": True,
            "continuedl": True,
            "retries": 3,
            "fragment_retries": 5,
            "concurrent_fragment_downloads": 15,
            "http_chunk_size": 1048576,
            "noprogress": True,
            "overwrites": True,
            "ffmpeg_location": "/usr/bin/ffmpeg",
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "m4a",
                    "preferredquality": "192"
                }
            ],
            "threads": 8
        }

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: YoutubeDL(ydl_opts).download([f"https://www.youtube.com/watch?v={video_id}"]))

        # ✅ After download, search again for final file
        matched_files = glob.glob(filename_pattern)
        if matched_files:
            return FileResponse(
                path=matched_files[0],
                filename=os.path.basename(matched_files[0]),
                media_type="audio/mp4"
            )

        raise HTTPException(status_code=404, detail="❌ File not found after download")

    except Exception as e:
        print("❌ Error:", str(e))
        raise HTTPException(status_code=500, detail=str(e))
