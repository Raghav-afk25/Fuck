import os
import time
import asyncio
import random
from yt_dlp import YoutubeDL
from asyncio import Semaphore

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# ✅ Limit concurrent downloads to avoid 429 errors
semaphore = Semaphore(5)

# ✅ Clean old downloaded files
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

    # ✅ Return if already cached
    if os.path.exists(output_path):
        return output_path

    # ✅ Background cleanup
    asyncio.create_task(asyncio.to_thread(cleanup_downloads))

    # ✅ Random delay (anti-bot pattern)
    await asyncio.sleep(random.uniform(1, 2))

    async with semaphore:
        cookies_path = os.path.abspath("cookies/cookies.txt")

        ydl_opts = {
            "format": "bestaudio[ext=m4a]/bestaudio/best",
            "quiet": True,
            "noplaylist": True,
            "outtmpl": output_path,
            "cookiefile": cookies_path,  # ✅ Correct key (NOT plural)
            "external_downloader": "aria2c",
            "external_downloader_args": [
                "--min-split-size=1M",
                "--max-connection-per-server=8",
                "--split=8",
                "--allow-overwrite=true",
                "--summary-interval=0"
            ],
            "concurrent_fragment_downloads": 4,
            "retries": 5,
            "fragment_retries": 10,
            "continuedl": True,
            "overwrites": True,
            "noprogress": True,
            "http_chunk_size": "1M",
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "http_headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept": "*/*",
                "Connection": "keep-alive",
            }
        }

        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: YoutubeDL(ydl_opts).download([f"https://www.youtube.com/watch?v={video_id}"])
            )
            return output_path if os.path.exists(output_path) else None
        except Exception as e:
            print(f"❌ Download Error: {e}")
            return None
