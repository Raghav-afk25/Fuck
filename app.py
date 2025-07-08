from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import os
from scrapper import download_song_from_video_id

app = FastAPI()

# ✅ CORS (allow all for now — lock it if needed)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Replace * with specific domains for security
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/download/song/{video_id}")
async def download_song(video_id: str):
    try:
        path = await download_song_from_video_id(video_id)

        if path and os.path.exists(path):
            filename = os.path.basename(path)
            return FileResponse(
                path=path,
                filename=filename,
                media_type="audio/mp4",  # or audio/m4a
                headers={
                    "Content-Disposition": f"attachment; filename={filename}",
                    "Cache-Control": "no-cache"
                }
            )
        
        return JSONResponse(status_code=404, content={"status": "fail", "message": "Download failed or video not found."})

    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": f"❌ Internal Error: {str(e)}"})
