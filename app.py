from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
import os
import asyncio
import glob
import subprocess

app = FastAPI()

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

@app.get("/download/song/{video_id}")
async def download_song(video_id: str):
    try:
        if len(video_id) != 11:
            raise HTTPException(status_code=400, detail="❌ Invalid YouTube video ID")

        # 🔄 Check existing cached file
        file_pattern = os.path.join(DOWNLOAD_DIR, f"{video_id}.*")
        existing_files = glob.glob(file_pattern)
        if existing_files:
            return FileResponse(
                path=existing_files[0],
                filename=os.path.basename(existing_files[0]),
                media_type="audio/mp4"
            )

        # ✅ Absolute path for cookies
        cookies_path = os.path.abspath("cookies/cookies.txt")
        if not os.path.exists(cookies_path):
            raise HTTPException(status_code=500, detail="❌ cookies.txt not found")

        # 🔧 Set yt-dlp output path
        output_path = os.path.join(DOWNLOAD_DIR, f"{video_id}.%(ext)s")

        # ✅ yt-dlp Command (fixed --cookies)
        command = [
            "yt-dlp",
            f"https://www.youtube.com/watch?v={video_id}",
            "-f", "bestaudio/best",
            "--extract-audio",
            "--audio-format", "m4a",
            "--audio-quality", "0",
            "--cookies", cookies_path,
            "-o", output_path,
            "--quiet",
            "--no-warnings",
            "--ffmpeg-location", "/usr/bin/ffmpeg",
            "--retries", "3",
            "--fragment-retries", "5",
            "--concurrent-fragment-downloads", "10"
        ]

        # 🔁 Run yt-dlp asynchronously
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: subprocess.run(command))

        # ✅ Check if file was downloaded
        downloaded_files = glob.glob(os.path.join(DOWNLOAD_DIR, f"{video_id}.*"))
        if downloaded_files:
            return FileResponse(
                path=downloaded_files[0],
                filename=os.path.basename(downloaded_files[0]),
                media_type="audio/mp4"
            )

        raise HTTPException(status_code=404, detail="❌ File not found after download")

    except Exception as e:
        print("❌ Error:", str(e))
        raise HTTPException(status_code=500, detail=str(e))
