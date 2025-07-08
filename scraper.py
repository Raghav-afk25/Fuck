import httpx
from bs4 import BeautifulSoup
import re
import yt_dlp

headers = {
    "User-Agent": "Mozilla/5.0"
}

async def scrap_pagalworld(query: str):
    try:
        async with httpx.AsyncClient() as client:
            search_url = f"https://www.pagalworldl.com/site_search?q={query.replace(' ', '+')}"
            res = await client.get(search_url, headers=headers, timeout=10)
            soup = BeautifulSoup(res.text, "html.parser")
            first_result = soup.select_one("div.media a")
            if not first_result:
                return None
            song_page = "https://www.pagalworldl.com" + first_result.get("href")
            res2 = await client.get(song_page, headers=headers, timeout=10)
            soup2 = BeautifulSoup(res2.text, "html.parser")
            download_link = soup2.find("a", string=re.compile(r"128kbps", re.I))
            if download_link:
                return {
                    "title": first_result.text.strip(),
                    "url": download_link.get("href"),
                    "source": "Pagalworld"
                }
    except:
        return None

async def scrap_jiosaavn(query: str):
    try:
        async with httpx.AsyncClient() as client:
            auto_url = f"https://www.jiosaavn.com/api.php?__call=autocomplete.get&query={query}&_format=json&_marker=0"
            auto_res = await client.get(auto_url, headers=headers, timeout=10)
            auto_data = auto_res.json()
            if not auto_data['songs']['data']:
                return None
            song_data = auto_data['songs']['data'][0]
            token = song_data['perma_url'].split("/")[-1]
            info_url = f"https://www.jiosaavn.com/api.php?__call=song.getDetails&token={token}&_format=json&_marker=0"
            info_res = await client.get(info_url, headers=headers, timeout=10)
            info_data = info_res.json()
            media_url = info_data['songs'][0].get('media_url', '')
            if media_url:
                return {
                    "title": info_data['songs'][0]['song'],
                    "artist": info_data['songs'][0]['singers'],
                    "url": media_url,
                    "source": "JioSaavn"
                }
    except:
        return None

async def scrap_hungama(query: str):
    try:
        async with httpx.AsyncClient() as client:
            res = await client.get(f"https://www.hungama.com/search/all/{query.replace(' ', '%20')}/songs", headers=headers, timeout=10)
            soup = BeautifulSoup(res.text, "html.parser")
            song = soup.select_one("ul[data-section='songs'] li a")
            if song:
                song_url = "https://www.hungama.com" + song['href']
                return {
                    "title": song.get('title', query),
                    "url": song_url,
                    "source": "Hungama"
                }
    except:
        return None

async def scrap_youtube(query: str):
    try:
        ydl_opts = {
            'format': 'bestaudio/best',
            'quiet': True,
            'noplaylist': True,
            'skip_download': True,
            'extract_flat': 'in_playlist',
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"ytsearch:{query}", download=False)['entries'][0]
            return {
                "title": info['title'],
                "url": f"https://www.youtube.com/watch?v={info['id']}",
                "source": "YouTube"
            }
    except:
        return None

async def get_song_data(query: str):
    for source_func in [scrap_pagalworld, scrap_jiosaavn, scrap_hungama, scrap_youtube]:
        try:
            result = await source_func(query)
            if result and result.get("url"):  # ✅ Only accept if URL is valid
                return {"status": "success", "data": result}
        except:
            continue
    return {"status": "fail", "reason": "No song found from any source"}
