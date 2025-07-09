from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import os
import glob
import subprocess

app = FastAPI()

# Allow CORS from your deployed frontend URL
origins = [
    "https://proxi-ab7q.onrender.com"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

@app.get("/")
async def root():
    return {"message": "API is running at https://proxi-ab7q.onrender.com/"}

def download_audio(video_id: str):
    try:
        cookies_path = os.path.abspath("cookies/cookies.txt")
        output_path = os.path.join(DOWNLOAD_DIR, f"{video_id}.%(ext)s")

        command = [
            "yt-dlp",
            f"https://www.youtube.com/watch?v={video_id}",
            "-f", "bestaudio",
            "--extract-audio",
            "--audio-format", "opus",
            "--audio-quality", "0",
            "--cookies", cookies_path,
            "--external-downloader", "aria2c",
            "--external-downloader-args", "-x 16 -k 1M",
            "--ffmpeg-location", "/usr/bin/ffmpeg",
            "--quiet",
            "--no-warnings",
            "--no-post-overwrites",
            "--no-mtime",
            "-o", output_path
        ]

        subprocess.run(command, check=True)
    except Exception as e:
        print(f"Download error for {video_id}: {str(e)}")

@app.get("/download/song/{video_id}")
async def download_song(video_id: str, background_tasks: BackgroundTasks):
    if len(video_id) != 11:
        raise HTTPException(status_code=400, detail="❌ Invalid YouTube video ID")

    file_pattern = os.path.join(DOWNLOAD_DIR, f"{video_id}.*")
    cached = glob.glob(file_pattern)
    if cached:
        return FileResponse(
            path=cached[0],
            filename=os.path.basename(cached[0]),
            media_type="audio/webm"
        )

    background_tasks.add_task(download_audio, video_id)
    return {
        "status": "processing",
        "message": "⏳ Download started in background. Please try again in a few seconds.",
        "video_id": video_id
    }
