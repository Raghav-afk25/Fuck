from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
import os
from scrapper import download_song_from_video_id

app = FastAPI()

@app.get("/download/song/{video_id}")
async def download_song(video_id: str):
    try:
        path = await download_song_from_video_id(video_id)
        if path and os.path.exists(path):
            return FileResponse(path=path, filename=os.path.basename(path), media_type="audio/mp4")
        raise HTTPException(status_code=404, detail="Download failed or video not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"❌ Error: {str(e)}")
