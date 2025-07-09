from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
import os
import glob
import subprocess
import asyncio

app = FastAPI()

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

download_locks = {}

@app.get("/")
async def root():
    return {"message": "API is running!"}

async def _download_audio_task(video_id: str, lock: asyncio.Lock):
    try:
        cookies_path = os.path.abspath("cookies/cookies.txt")
        temp_output_path = os.path.join(DOWNLOAD_DIR, f"{video_id}.temp_%(ext)s")

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
            "-o", temp_output_path
        ]

        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            error_message = stderr.decode().strip()
            print(f"Download error for {video_id}: {error_message}")
            raise Exception(f"yt-dlp failed with error: {error_message}")

        downloaded_files = glob.glob(os.path.join(DOWNLOAD_DIR, f"{video_id}.temp_*"))
        if downloaded_files:
            temp_file = downloaded_files[0]
            final_ext = os.path.basename(temp_file).split('.temp_')[-1]
            final_file_path = os.path.join(DOWNLOAD_DIR, f"{video_id}.{final_ext}")
            os.rename(temp_file, final_file_path)
        else:
            raise Exception(f"Temporary file not found for {video_id}")

    except Exception as e:
        print(f"Download error for {video_id}: {str(e)}")
    finally:
        if lock.locked():
            lock.release()
        if video_id in download_locks and not lock.locked():
            del download_locks[video_id]

@app.get("/download/song/{video_id}")
async def download_song(video_id: str, background_tasks: BackgroundTasks):
    if len(video_id) != 11:
        raise HTTPException(status_code=400, detail="Invalid YouTube video ID")

    file_pattern = os.path.join(DOWNLOAD_DIR, f"{video_id}.*")
    cached_files = glob.glob(file_pattern)

    if cached_files:
        return FileResponse(
            path=cached_files[0],
            filename=os.path.basename(cached_files[0]),
            media_type="audio/webm"
        )

    if video_id not in download_locks:
        download_locks[video_id] = asyncio.Lock()
        await download_locks[video_id].acquire()
        background_tasks.add_task(_download_audio_task, video_id, download_locks[video_id])
        return {
            "status": "processing",
            "message": "Download started in background. Please try again in a few seconds.",
            "video_id": video_id
        }
    else:
        await download_locks[video_id].acquire()
        download_locks[video_id].release()

        cached_files_after_wait = glob.glob(file_pattern)
        if cached_files_after_wait:
            return FileResponse(
                path=cached_files_after_wait[0],
                filename=os.path.basename(cached_files_after_wait[0]),
                media_type="audio/webm"
            )
        else:
            raise HTTPException(status_code=500, detail="Download completed but file not found.")
