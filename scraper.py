import httpx
from bs4 import BeautifulSoup

async def scrap_jiosaavn(query: str):
    async with httpx.AsyncClient() as client:
        res = await client.get(f"https://www.jiosaavn.com/api.php?__call=autocomplete.get&_format=json&_marker=0&query={query}")
        data = res.json()
        try:
            song = data['songs']['data'][0]
            return {
                "title": song['title'],
                "artist": song['more_info']['artistMap']['primary_artists'][0]['name'],
                "media_url": song['more_info']['media_url']
            }
        except:
            return None

async def scrap_youtube(query: str):
    import yt_dlp
    ydl_opts = {
        'format': 'bestaudio/best',
        'quiet': True,
        'noplaylist': True,
        'skip_download': True,
        'extract_flat': 'in_playlist',
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(f"ytsearch:{query}", download=False)['entries'][0]
            return {
                "title": info['title'],
                "url": f"https://www.youtube.com/watch?v={info['id']}"
            }
        except:
            return None

async def get_song_data(query: str):
    for source in [scrap_jiosaavn, scrap_youtube]:
        result = await source(query)
        if result:
            return {"status": "success", "data": result}
    return {"status": "fail", "reason": "No source found"}
