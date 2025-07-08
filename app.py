from fastapi import FastAPI, Query
from scraper import get_song_data

app = FastAPI()

@app.get("/song")
async def fetch_song(query: str = Query(..., description="Enter song name")):
    result = await get_song_data(query)
    return result
