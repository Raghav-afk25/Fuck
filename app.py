from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from yt_dlp import YoutubeDL
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
        # ✅ 1. Check for valid YouTube video ID
        if len(video_id) != 11:
            raise HTTPException(status_code=400, detail="❌ Invalid YouTube video ID (must be 11 characters)")

        # ✅ 2. Check if file already exists (cache)
        file_pattern = os.path.join(DOWNLOAD_DIR, f"{video_id}.*")
        existing_files = glob.glob(file_pattern)
        if existing_files:
            return FileResponse(
                path=existing_files[0],
                filename=os.path.basename(existing_files[0]),
                media_type="audio/mp4"
            )

        # ✅ 3. Check cookies
        cookies_path = os.path.abspath("cookies/cookies.txt")
        if not os.path.exists(cookies_path):
            raise HTTPException(status_code=500, detail="❌ cookies.txt not found")

        # ✅ 4. Build yt-dlp command
        output_path = os.path.join(DOWNLOAD_DIR, f"{video_id}.%(ext)s")
        command = [
            "yt-dlp",
            f"https://www.youtube.com/watch?v={video_id}",
            "-f", "bestaudio[ext=m4a]/bestaudio/best",
            "--quiet",
            "--no-warnings",
            "--extract-audio",
            "--audio-format", "m4a",
            "--audio-quality", "0",
            "--retries", "3",
            "--fragment-retries", "5",
            "--concurrent-fragment-downloads", "10",
            "--cookiefile", cookies_path,
            "-o", output_path,
            "--ffmpeg-location", "/usr/bin/ffmpeg"
        ]

        # ✅ 5. Run yt-dlp as external subprocess
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))

        # ✅ 6. After download, find the actual file
        final_files = glob.glob(os.path.join(DOWNLOAD_DIR, f"{video_id}.m4a"))
        if final_files:
            return FileResponse(
                path=final_files[0],
                filename=os.path.basename(final_files[0]),
                media_type="audio/mp4"
            )

        raise HTTPException(status_code=404, detail="❌ File not found after download")

    except Exception as e:
        print("❌ Error:", str(e))
        raise HTTPException(status_code=500, detail=str(e))
