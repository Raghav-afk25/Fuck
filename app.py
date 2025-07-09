from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from yt_dlp import YoutubeDL
import os

app = FastAPI()

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

@app.get("/download/song/{video_id}")
async def download_song(video_id: str):
    try:
        output_path = os.path.join(DOWNLOAD_DIR, f"{video_id}.m4a")

        if not os.path.exists(output_path):
            # ✅ Corrected path for cookies
            cookies_path = os.path.abspath("cookies/cookies.txt")

            ydl_opts = {
                "format": "bestaudio[ext=m4a]/bestaudio",
                "quiet": True,
                "cookiefile": cookies_path,
                "outtmpl": output_path
            }

            with YoutubeDL(ydl_opts) as ydl:
                ydl.download([f"https://www.youtube.com/watch?v={video_id}"])

        if os.path.exists(output_path):
            return FileResponse(
                path=output_path,
                filename=f"{video_id}.m4a",
                media_type="audio/mp4"
            )

        raise HTTPException(status_code=404, detail="File not found")

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
