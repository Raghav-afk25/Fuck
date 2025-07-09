from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from yt_dlp import YoutubeDL
import os
import asyncio
import glob
import time

app = FastAPI()

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

@app.get("/download/song/{video_id}")
async def download_song(video_id: str):
    try:
        filename_pattern = os.path.join(DOWNLOAD_DIR, f"{video_id}.*")

        # Return existing file if available
        existing_files = glob.glob(filename_pattern)
        if existing_files:
            return FileResponse(
                path=existing_files[0],
                filename=os.path.basename(existing_files[0]),
                media_type="audio/mp4"
            )

        # Make sure cookies.txt exists
        cookies_path = os.path.abspath("cookies/cookies.txt")
        if not os.path.exists(cookies_path):
            raise HTTPException(status_code=500, detail="❌ cookies.txt not found")

        # Set yt-dlp options
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
            ]
        }

        # Download asynchronously
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: YoutubeDL(ydl_opts).download([f"https://www.youtube.com/watch?v={video_id}"])
        )

        # After download, search again for file
        downloaded_files = glob.glob(filename_pattern)
        if downloaded_files:
            return FileResponse(
                path=downloaded_files[0],
                filename=os.path.basename(downloaded_files[0]),
                media_type="audio/mp4"
            )

        # If still not found, throw error
        raise HTTPException(status_code=404, detail="❌ File not found after download")

    except Exception as e:
        print("❌ Error:", str(e))
        raise HTTPException(status_code=500, detail=str(e))
