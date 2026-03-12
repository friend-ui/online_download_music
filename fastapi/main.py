import sys
import os
import shutil
from typing import List, Dict, Any
from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from a2wsgi import ASGIMiddleware

# Add musicdl to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../musicdl')))

try:
    from musicdl.musicdl import MusicClient
    from musicdl.modules.utils.data import SongInfo
except ImportError as e:
    print(f"Error importing musicdl: {e}")
    print("Please make sure you have installed the requirements.")
    sys.exit(1)

app = FastAPI()

# Mount static files
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
if not os.path.exists(STATIC_DIR):
    os.makedirs(STATIC_DIR)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize MusicClient
# Set proxy if needed
proxy = os.environ.get("HTTP_PROXY")
PROXIES = {"http": proxy, "https": proxy} if proxy else None
SOURCES = ['MiguMusicClient', 'NeteaseMusicClient', 'QQMusicClient', 'KuwoMusicClient', 'QianqianMusicClient', 'KugouMusicClient']
REQUESTS_OVERRIDES = {source: {"proxies": PROXIES} for source in SOURCES} if proxy else {}

# Initialize client globally
client = MusicClient(music_sources=SOURCES, requests_overrides=REQUESTS_OVERRIDES)

DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")
if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

# WSGI app for PythonAnywhere
application = ASGIMiddleware(app)


class SearchRequest(BaseModel):
    keyword: str

@app.get("/")
async def read_root():
    return FileResponse(os.path.join(STATIC_DIR, 'index.html'))

@app.post("/api/search")
async def search(request: SearchRequest):
    try:
        keyword = request.keyword
        # Call musicdl search
        # search returns a dict: {source: [song_info_dict, ...]}
        # Note: client.search returns list of SongInfo objects in recent versions?
        # Let's check the code again.
        # MusicClient.search returns a dict from ThreadPoolExecutor map if run in parallel,
        # BUT wait, the MusicClient.search method in musicdl.py:
        # returns dict(ex.map(search_func, self.music_sources))
        # where search_func returns (ms, results_list)
        # So it returns {source: [SongInfo, ...]}
        
        raw_results = client.search(keyword)
        
        results = []
        for source, song_infos in raw_results.items():
            for song_info in song_infos:
                # song_info is a SongInfo object
                # We need to convert it to dict for JSON response
                if isinstance(song_info, SongInfo):
                    results.append(song_info.todict())
                else:
                    # Fallback if it's already a dict (should not happen based on code read)
                    results.append(song_info)
                    
        return {"results": results}
    except Exception as e:
        print(f"Search error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/download")
async def download(song_info_data: Dict[str, Any]):
    try:
        # Reconstruct SongInfo object
        song_info = SongInfo.fromdict(song_info_data)
        
        # Override work_dir to our download directory
        song_info.work_dir = DOWNLOAD_DIR
        # Reset _save_path to ensure it recalculates based on new work_dir
        song_info._save_path = None
        
        # Download
        # client.download expects a list of dicts or SongInfo objects?
        # The signature says list[dict] in type hint, but code uses SongInfo object attributes.
        # Let's check musicdl.py again.
        # download(self, song_infos: list[dict]) -> calls self.music_clients[source].download
        # BaseMusicClient.download takes list[SongInfo]
        # So we should pass a list of SongInfo objects.
        
        client.download([song_info])
        
        file_path = song_info.save_path
        
        if os.path.exists(file_path):
            filename = os.path.basename(file_path)
            return FileResponse(file_path, filename=filename, media_type='application/octet-stream')
        else:
            raise HTTPException(status_code=404, detail="File not found after download")
            
    except Exception as e:
        print(f"Download error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
