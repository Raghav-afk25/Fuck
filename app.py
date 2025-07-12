import os
import random
import asyncio
import subprocess
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse, FileResponse
from dotenv import load_dotenv
import logging
import glob
from datetime import datetime
load_dotenv()
app = FastAPI()
DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
# --- In-memory status tracking ---
download_status = {}
# --- In-memory download events for synchronization ---
download_events = {}
import threading
import time as time_mod
# --- Logging ---
logging.basicConfig(
    level=logging.DEBUG,  # Changed to DEBUG for verbose logging
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("api_logs.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("api")
def get_or_create_event(video_id):
    # Clean up old events (older than 8 hours)
    now = time_mod.time()
    to_delete = []
    for vid, (event, created_at) in download_events.items():
        if now - created_at > 8 * 3600:
            to_delete.append(vid)
    for vid in to_delete:
        del download_events[vid]
    # Get or create event
    if video_id not in download_events:
        download_events[video_id] = (asyncio.Event(), now)
    return download_events[video_id][0]
def ytdlp_progress_hook(video_id):
    def hook(d):
        if d['status'] == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
            downloaded = d.get('downloaded_bytes', 0)
            percent = int((downloaded / total) * 100) if total else 0
            download_status[video_id] = {
                **download_status.get(video_id, {}),
                'status': 'downloading',
                'progress': str(percent),
                'downloaded_bytes': str(downloaded),
                'total_bytes': str(total),
                'speed': d.get('speed'),
                'eta': d.get('eta'),
            }
        elif d['status'] == 'finished':
            download_status[video_id] = {
                **download_status.get(video_id, {}),
                'status': 'processing',
                'progress': '100',
            }
    return hook
import asyncio
import os
MAX_WORKERS = int(os.environ.get("MAX_WORKERS", "50"))
download_semaphore = asyncio.Semaphore(MAX_WORKERS)
async def background_download(video_id):
    async with download_semaphore:
        cleanup_ytdl_files(video_id)
        download_status[video_id] = {
            "status": "downloading",
            "progress": "0",
            "started_at": datetime.now().isoformat(),
            "attempts": "0",
            "current_strategy": "0"
        }
        loop = asyncio.get_running_loop()
        try:
            for attempt in range(MAX_DOWNLOAD_RETRIES):
                download_status[video_id]["attempts"] = str(attempt + 1)
                download_status[video_id]["progress"] = str(int((attempt / MAX_DOWNLOAD_RETRIES) * 50))
                logger.info(f"[yt-dlp][{video_id}] Download attempt {attempt + 1}/{MAX_DOWNLOAD_RETRIES}")
                # Add progress_hooks to yt-dlp options
                def download_with_hook(video_id):
                    url = f"https://www.youtube.com/watch?v={video_id}"
                    output_template = os.path.join(DOWNLOAD_DIR, f"{video_id}.%(ext)s")
                    format_strategies = [
                        "bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio/best",
                        "bestaudio[filesize<20M]/bestaudio[ext=m4a]/bestaudio/best",
                        "bestaudio[abr<=128]/bestaudio[ext=m4a]/bestaudio/best",
                        "bestaudio"
                    ]
                    cookies_file = get_cookies_file()
                    for i, format_strategy in enumerate(format_strategies):
                        ydl_opts = {
                            "format": format_strategy,
                            "outtmpl": output_template,
                            "quiet": True,
                            "no_warnings": True,
                            "cookiefile": cookies_file,  # Always use cookies if present
                            "retries": 10,
                            "fragment_retries": 10,
                            "file_access_retries": 10,
                            "nocheckcertificate": True,
                            "prefer_insecure": True,
                            "no_cache_dir": True,
                            "ignoreerrors": True,
                            "concurrent_fragment": 1,
                            "force_overwrites": True,
                            "noplaylist": True,
                            "extractaudio": True,
                            "audioformat": "best",
                            "audioquality": "0",
                            "addheader": [
                                f"User-Agent:{get_random_user_agent()}",
                                "Accept-Language:en-US,en;q=0.9",
                                "Accept-Encoding:gzip, deflate, br",
                                "DNT:1",
                                "Connection:keep-alive",
                                "Upgrade-Insecure-Requests:1",
                                "Sec-Fetch-Dest:document",
                                "Sec-Fetch-Mode:navigate",
                                "Sec-Fetch-Site:none",
                                "Sec-Fetch-User:?1",
                                "Cache-Control:max-age=0"
                            ],
                            "extractor_args": {
                                "youtube": {
                                    "player_client": random.choice(YOUTUBE_CLIENTS)
                                }
                            },
                            "progress_hooks": [ytdlp_progress_hook(video_id)]
                        }
                        # Add PO token arguments if enabled
                        if PO_TOKEN_ENABLED:
                            po_token = os.environ.get("PO_TOKEN")
                            if po_token:
                                if po_token.startswith("bgutil:"):
                                    if po_token == "bgutil:http":
                                        ydl_opts["extractor_args"]["youtube"]["pot_provider"] = "bgutil:http"
                                        logger.info(f"[yt-dlp][{video_id}] Using bgutil HTTP provider")
                                    elif po_token == "bgutil:script":
                                        script_path = os.path.expanduser("~/bgutil-ytdlp-pot-provider/server/build/generate_once.js")
                                        ydl_opts["extractor_args"]["youtube"]["pot_provider"] = "bgutil:script"
                                        ydl_opts["extractor_args"]["youtube"]["script_path"] = script_path
                                        logger.info(f"[yt-dlp][{video_id}] Using bgutil script provider")
                                else:
                                    ydl_opts["extractor_args"]["youtube"]["player_client"] = "android"
                                    ydl_opts["extractor_args"]["youtube"]["player_skip"] = "webpage"
                                    logger.info(f"[yt-dlp][{video_id}] Using manual PO token")
                        try:
                            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                                ydl.download([url])
                            downloaded_file = find_downloaded_file(video_id)
                            if downloaded_file and validate_downloaded_file(downloaded_file, video_id):
                                logger.info(f"[yt-dlp][{video_id}] Successfully downloaded: {downloaded_file}")
                                return {"success": True, "file": downloaded_file, "strategy": i+1, "client": ydl_opts['extractor_args']['youtube']['player_client']}
                        except Exception as e:
                            logger.error(f"Download error for video_id={video_id}, strategy {i+1}: {e}")
                            continue
                    logger.error(f"[yt-dlp][{video_id}] All format strategies failed")
                    return {"success": False, "error": "all strategies failed"}
                result = await loop.run_in_executor(
                    None, functools.partial(download_with_hook, video_id)
                )
                downloaded_file = find_downloaded_file(video_id)
                if result["success"] and downloaded_file and validate_downloaded_file(downloaded_file, video_id):
                    file_size = os.path.getsize(downloaded_file)
                    logger.info(f"[yt-dlp][{video_id}] Download successful on attempt {attempt + 1}")
                    download_status[video_id] = {
                        "status": "done",
                        "progress": "100",
                        "completed_at": datetime.now().isoformat(),
                        "file_path": downloaded_file,
                        "file_size": str(file_size),
                        "strategy_used": str(result["strategy"]),
                        "client_used": result.get("client", "unknown")
                    }
                    return
                if downloaded_file and os.path.exists(downloaded_file) and not validate_downloaded_file(downloaded_file, video_id):
                    try:
                        os.remove(downloaded_file)
                        logger.warning(f"[yt-dlp][{video_id}] Cleaned up invalid/corrupted file: {downloaded_file}")
                    except Exception as e:
                        logger.warning(f"[yt-dlp][{video_id}] Failed to clean up invalid file: {e}")
            logger.error(f"[yt-dlp][{video_id}] All {MAX_DOWNLOAD_RETRIES} download attempts failed")
            download_status[video_id] = {
                "status": "error",
                "progress": "0",
                "failed_at": datetime.now().isoformat(),
                "error": "All download attempts failed",
                "file_path": "",
                "file_size": "0"
            }
        finally:
            pass
        cleanup_ytdl_files(video_id)
def get_output_path(video_id):
    return os.path.join(DOWNLOAD_DIR, f"{video_id}.m4a")
def pick_user_agent():
    # Enhanced user agent rotation for better success rates
    agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.1 Safari/605.1.15",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 Edg/122.0.0.0"
    ]
    return random.choice(agents)
async def download_audio(video_id):
    url = f"https://www.youtube.com/watch?v={video_id}"
    output_path = get_output_path(video_id)
    user_agent = pick_user_agent()
    
    # Intelligent format selection strategy
    # Priority: 140 (m4a) > 251 (webm) > 250 (webm) > 249 (webm) > bestaudio
    format_strategy = "140/251/250/249/bestaudio[ext=m4a]/bestaudio/best"
    
    sleep_interval = str(random.randint(1, 3))
    max_sleep_interval = str(random.randint(5, 10))
        
    cmd = [
        "yt-dlp",
        "--format", format_strategy,
        "--output", output_path,
        "--no-playlist",
        "--extract-audio",
        "--audio-format", "m4a",
        "--audio-quality", "0",  # Best quality
        "--retries", "10",
        "--fragment-retries", "10",
        "--file-access-retries", "10",
        "--sleep-interval", sleep_interval,
        "--max-sleep-interval", max_sleep_interval,
        "--buffer-size", "1024",
        "--no-part",
        "--force-overwrites",
        "--no-continue",
        "--write-thumbnail",  # Get thumbnail for metadata
        "--write-info-json",  # Get video info for metadata
        "--no-warnings",  # Reduce log noise
        url
    ]
    
    if user_agent:
        cmd += ["--add-headers", f"User-Agent:{user_agent}"]
    if os.path.exists("cookies.txt"):
        cmd += ["--cookies", "cookies.txt"]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
    
        # Enhanced file validation
        if proc.returncode == 0 and os.path.exists(output_path):
            file_size = os.path.getsize(output_path)
            # Require minimum 50KB for audio files (prevents incomplete downloads)
            if file_size > 50 * 1024:
                # Get additional metadata
                info_file = output_path.replace('.m4a', '.info.json')
                metadata = {}
                if os.path.exists(info_file):
                    try:
                        import json
                        with open(info_file, 'r') as f:
                            metadata = json.load(f)
                        # Clean up info file
                        os.remove(info_file)
                    except:
                        pass
                
                return {"status": "done", "meta": output_path}
            else:
                return {"status": "error", "meta": "File too small"}
        else:
            error_msg = stderr.decode() if stderr else "Unknown error"
            return {"status": "error", "meta": error_msg}
    except Exception as e:
        return {"status": "error", "meta": str(e)}
@app.get("/")
async def root():
    logger.debug("Received / request")
    return {"status": "ok", "message": "YouTube Audio Downloader API"}
@app.get("/song/{video_id}")
async def song_status(video_id: str):
    logger.debug(f"Received /song/{video_id} request")
    status = download_status.get(video_id, {}).get("status")
    progress = download_status.get(video_id, {}).get("progress", "0")
    metadata = download_status.get(video_id, {})
    file_path = find_downloaded_file(video_id)
    logger.debug(f"Status: {status}, Progress: {progress}, Metadata: {metadata}, File path: {file_path}")
    event = get_or_create_event(video_id)
    if status == "done":
        if file_path and validate_downloaded_file(file_path, video_id):
            ext = get_file_extension(file_path)
            link = f"{DOMAIN}/downloaded_file/{video_id}"
            return JSONResponse({
                "status": "done",
                "link": link,
                "format": ext,
                "file_size": os.path.getsize(file_path),
                "progress": 100,
                "metadata": metadata
            })
        else:
            download_status[video_id] = {"status": "error", "progress": "0", "error": "File not found or corrupted after download."}
            event.set()
            return JSONResponse({
                "status": "error",
                "message": "File not found or corrupted after download.",
                "progress": 0
            })
    elif status == "downloading":
        # Wait for the download to finish (up to 8 hours)
        try:
            await asyncio.wait_for(event.wait(), timeout=8*3600)
        except asyncio.TimeoutError:
            return JSONResponse({
                "status": "error",
                "message": "Download timed out after 8 hours.",
                "progress": int(progress or 0),
                "metadata": metadata
            })
        # After wait, re-check status
        status2 = download_status.get(video_id, {}).get("status")
        file_path2 = find_downloaded_file(video_id)
        if status2 == "done" and file_path2 and validate_downloaded_file(file_path2, video_id):
            ext = get_file_extension(file_path2)
            link = f"{DOMAIN}/downloaded_file/{video_id}"
            return JSONResponse({
                "status": "done",
                "link": link,
                "format": ext,
                "file_size": os.path.getsize(file_path2),
                "progress": 100,
                "metadata": download_status.get(video_id, {})
            })
        else:
            return JSONResponse({
                "status": "error",
                "message": "File not found or corrupted after download.",
                "progress": 0
            })
    elif status == "error":
        event.set()
        return JSONResponse({
            "status": "error",
            "message": metadata.get("error", "Download failed."),
            "progress": 0
        })
    else:
        # Only one download task per video_id
        if video_id not in download_status or download_status[video_id].get("status") != "downloading":
            asyncio.create_task(background_download(video_id))
        download_status[video_id] = {
            "status": "downloading",
            "progress": "0",
            "started_at": datetime.now().isoformat(),
            "attempts": "0",
            "current_strategy": "0"
        }
        # Wait for the download to finish (up to 8 hours)
        try:
            await asyncio.wait_for(event.wait(), timeout=8*3600)
        except asyncio.TimeoutError:
            return JSONResponse({
                "status": "error",
                "message": "Download timed out after 8 hours.",
                "progress": 0,
                "metadata": download_status.get(video_id, {})
            })
        # After wait, re-check status
        status2 = download_status.get(video_id, {}).get("status")
        file_path2 = find_downloaded_file(video_id)
        if status2 == "done" and file_path2 and validate_downloaded_file(file_path2, video_id):
            ext = get_file_extension(file_path2)
            link = f"{DOMAIN}/downloaded_file/{video_id}"
            return JSONResponse({
                "status": "done",
                "link": link,
                "format": ext,
                "file_size": os.path.getsize(file_path2),
                "progress": 100,
                "metadata": download_status.get(video_id, {})
            })
        else:
            return JSONResponse({
                "status": "error",
                "message": "File not found or corrupted after download.",
                "progress": 0
            })
@app.get("/downloaded_file/{video_id}")
async def serve_downloaded_file(video_id: str):
    logger.debug(f"Received /downloaded_file/{video_id} request")
    file_path = find_downloaded_file(video_id)
    logger.debug(f"File path resolved: {file_path}")
    if not file_path or not validate_downloaded_file(file_path, video_id):
        logger.warning(f"[API][{video_id}] File not found or invalid for download request (file_path={file_path})")
        download_status[video_id] = {"status": "error", "progress": "0", "error": "File not found or corrupted."}
        raise HTTPException(status_code=404, detail="File not found or corrupted")
    try:
        file_size = os.path.getsize(file_path)
        logger.debug(f"File size: {file_size}")
    except Exception as e:
        logger.error(f"[API][{video_id}] Error getting file size: {e}")
        raise HTTPException(status_code=500, detail="Error accessing file")
    ext = get_file_extension(file_path)
    media_type = {
        "m4a": "audio/mp4",
        "webm": "audio/webm",
        "mp3": "audio/mpeg",
        "opus": "audio/ogg"
    }.get(ext, "application/octet-stream")
    logger.info(f"[API][{video_id}] Serving validated file: {file_path} (size: {file_size} bytes)")
    return FileResponse(
        path=file_path,
        filename=os.path.basename(file_path),
        media_type=media_type,
        headers={
            "Cache-Control": "public, max-age=31536000, immutable",
            "Content-Disposition": f'attachment; filename=\"{os.path.basename(file_path)}\"',
            "X-File-Size": str(file_size),
            "X-Download-Time": datetime.now().isoformat(),
            "X-Validation": "passed"
        }
    )
@app.get("/health")
async def health_check():
    logger.debug("Received /health request")
    return {"status": "healthy", "downloads_dir": DOWNLOAD_DIR}
def find_downloaded_file(video_id):
    logger.debug(f"Looking for downloaded file for video_id={video_id}")
    for ext in ["m4a", "webm", "mp3", "opus"]:
        candidate = os.path.join(DOWNLOAD_DIR, f"{video_id}.{ext}")
        logger.debug(f"Checking candidate: {candidate}")
        if os.path.exists(candidate) and os.path.getsize(candidate) > 0:
            logger.info(f"Found file: {candidate}")
            return candidate
    files = glob.glob(os.path.join(DOWNLOAD_DIR, f"{video_id}.*"))
    for f in files:
        logger.debug(f"Checking file: {f}")
        if f.endswith('.part') or f.endswith('.ytdl') or f.endswith('.temp'):
            continue
        if os.path.getsize(f) > 0:
            logger.info(f"Found file: {f}")
            return f
    logger.warning(f"No valid file found for video_id={video_id}")
    return None
