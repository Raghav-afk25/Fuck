from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from yt_dlp import YoutubeDL
import os
import asyncio
from concurrent.futures import ThreadPoolExecutor

app = FastAPI()

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

executor = ThreadPoolExecutor(max_workers=10)

def download_audio(video_id: str, output_path: str):
    ydl_opts = {
        "format": "bestaudio[ext=m4a]/bestaudio",
        "quiet": True,
        "cookiefile": "cookies.txt",
        "outtmpl": output_path
    }
    with YoutubeDL(ydl_opts) as ydl:
        ydl.download([f"https://www.youtube.com/watch?v={video_id}"])

@app.get("/download/song/{video_id}")
async def download_song(video_id: str, background_tasks: BackgroundTasks):
    output_path = os.path.join(DOWNLOAD_DIR, f"{video_id}.m4a")

    if os.path.exists(output_path):
        return FileResponse(
            path=output_path,
            filename=f"{video_id}.m4a",
            media_type="audio/mp4"
        )

    loop = asyncio.get_running_loop()
    try:
        await loop.run_in_executor(executor, download_audio, video_id, output_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Download failed: {str(e)}")

    if os.path.exists(output_path):
        return FileResponse(
            path=output_path,
            filename=f"{video_id}.m4a",
            media_type="audio/mp4"
        )

    raise HTTPException(status_code=500, detail="Unknown error occurred during download")
