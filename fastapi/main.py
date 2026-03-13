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
    source: str = "all"

@app.get("/")
async def read_root():
    return FileResponse(os.path.join(STATIC_DIR, 'index.html'))

@app.post("/api/search")
async def search(request: SearchRequest):
    try:
        keyword = request.keyword
        source = request.source
        
        # Determine sources to use
        if source == "all" or source not in SOURCES:
            search_sources = SOURCES
            current_client = client
        else:
            search_sources = [source]
            # Create a new client for specific source to avoid waiting for others
            # Or use the global client if we don't mind
            # For better performance on single source search, a new client is better 
            # as it won't spawn threads for other sources.
            current_client = MusicClient(music_sources=search_sources, requests_overrides=REQUESTS_OVERRIDES)

        raw_results = current_client.search(keyword)
        
        results = []
        for src, song_infos in raw_results.items():
            for song_info in song_infos:
                if isinstance(song_info, SongInfo):
                    results.append(song_info.todict())
                else:
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
        
        # Custom filename: SongName(Singers).ext
        # Sanitize filename components
        def sanitize(name):
            return "".join([c for c in name if c.isalnum() or c in (' ', '-', '_', '.', '(', ')', '[', ']')]).strip()
        
        song_name = sanitize(song_info.song_name or "Unknown")
        singers = sanitize(song_info.singers or "Unknown")
        ext = (song_info.ext or "mp3").lstrip('.')
        
        filename = f"{song_name}({singers}).{ext}"
        save_path = os.path.join(DOWNLOAD_DIR, filename)
        
        # Check if file already exists
        if not os.path.exists(save_path):
            # Force set _save_path so musicdl uses it
            song_info._save_path = save_path
            # Download
            client.download([song_info])
        
        # Verify file exists (it should now)
        if os.path.exists(save_path):
            filename = os.path.basename(save_path)
            # Use standard FileResponse with filename parameter which handles quoting correctly
            return FileResponse(
                save_path, 
                filename=filename, 
                media_type='application/octet-stream'
            )
        else:
            raise HTTPException(status_code=404, detail="File not found after download")
            
    except Exception as e:
        print(f"Download error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
