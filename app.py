from fastapi import FastAPI
from fastapi.responses import JSONResponse, FileResponse
import os
import tempfile
import httpx
import aiofiles
import yt_dlp
from scraper import scrap_pagalworld, scrap_jiosaavn, scrap_hungama, scrap_youtube

app = FastAPI()


# 🔍 Multi-source song search
async def get_song_data(query: str):
    for source_func in [scrap_pagalworld, scrap_jiosaavn, scrap_hungama, scrap_youtube]:
        try:
            result = await source_func(query)
            if result and result.get("url"):
                return {"status": "success", "data": result}
        except:
            continue
    return {"status": "fail", "reason": "No song found from any source"}


# ✅ Song metadata API
@app.get("/song")
async def song(query: str):
    result = await get_song_data(query)
    return JSONResponse(content=result)


# 🎧 MP3 File download route
@app.get("/download")
async def download_song(query: str):
    result = await get_song_data(query)
    if result["status"] != "success":
        return {"status": "fail", "reason": "Song not found"}

    url = result["data"]["url"]
    title = result["data"]["title"].replace(" ", "_").replace("|", "_")

    if not url:
        return {"status": "fail", "reason": "Invalid URL"}

    tempdir = tempfile.mkdtemp()
    filepath = os.path.join(tempdir, f"{title}.mp3")

    if "youtube.com" in url:
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': filepath,
            'quiet': True,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    else:
        async with httpx.AsyncClient() as client:
            r = await client.get(url)
            async with aiofiles.open(filepath, 'wb') as f:
                await f.write(r.content)

    return FileResponse(filepath, filename=f"{title}.mp3", media_type='audio/mpeg')
