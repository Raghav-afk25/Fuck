import os
from yt_dlp import YoutubeDL
import asyncio

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

async def download_song_from_video_id(video_id: str) -> str:
    filename = f"{video_id}.m4a"
    output_path = os.path.join(DOWNLOAD_DIR, filename)

    if os.path.exists(output_path):
        return output_path

    cookies_path = os.path.abspath("cookies/cookies.txt")

    ydl_opts = {
        "format": "bestaudio[ext=m4a]/bestaudio/best",
        "quiet": True,
        "noplaylist": True,
        "outtmpl": output_path,
        "cookiefile": cookies_path,
        "concurrent_fragment_downloads": 15,         # ⏩ Max fragments
        "retries": 3,                                # Retry if fail
        "fragment_retries": 5,
        "continuedl": True,                          # Resume partial
        "nopart": False,                             # Enable part files
        "noprogress": True,                          # No stdout delay
        "http_chunk_size": "1M",                     # Smaller chunks = faster parallel
        "hls_use_mpegts": True,                      # Better on live/vod
        "overwrites": True                           # Always overwrite
    }

    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: YoutubeDL(ydl_opts).download([f"https://www.youtube.com/watch?v={video_id}"]))
        return output_path if os.path.exists(output_path) else None
    except Exception as e:
        print(f"❌ Error: {e}")
        return None
