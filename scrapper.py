import os
import time
import asyncio
from yt_dlp import YoutubeDL
from asyncio import Semaphore

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# ✅ Limit to 10 concurrent downloads (you can increase)
semaphore = Semaphore(10)

# ✅ Auto delete old files older than 1 hour
def cleanup_downloads(max_age_sec=3600):
    now = time.time()
    for f in os.listdir(DOWNLOAD_DIR):
        path = os.path.join(DOWNLOAD_DIR, f)
        if os.path.isfile(path) and now - os.path.getmtime(path) > max_age_sec:
            try:
                os.remove(path)
            except:
                pass

async def download_song_from_video_id(video_id: str) -> str:
    filename = f"{video_id}.m4a"
    output_path = os.path.join(DOWNLOAD_DIR, filename)

    # ✅ Return if already exists (cached)
    if os.path.exists(output_path):
        return output_path

    # ✅ Cleanup old files in background
    asyncio.create_task(asyncio.to_thread(cleanup_downloads))

    # ✅ Use semaphore to avoid overload
    async with semaphore:
        cookies_path = os.path.abspath("cookies/cookies.txt")

        ydl_opts = {
            "format": "bestaudio[ext=m4a]/bestaudio/best",
            "quiet": True,
            "noplaylist": True,
            "outtmpl": output_path,
            "cookiefile": cookies_path,
            "external_downloader": "aria2c",  # ✅ Ultra-fast backend
            "external_downloader_args": ["-x", "16", "-k", "1M"],
            "concurrent_fragment_downloads": 15,
            "retries": 3,
            "fragment_retries": 5,
            "continuedl": True,
            "overwrites": True,
            "noprogress": True,
            "http_chunk_size": "1M"
        }

        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, lambda: YoutubeDL(ydl_opts).download([f"https://www.youtube.com/watch?v={video_id}"]))
            return output_path if os.path.exists(output_path) else None
        except Exception as e:
            print(f"❌ Download Error: {e}")
            return None
