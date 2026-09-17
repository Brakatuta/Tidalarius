from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os
from tidal_auth import router as auth_router
from playlists import router as playlists_router
from music_api import router as music_router
from sync_api import router as sync_router
from database import engine
import models

from sqlalchemy import text

# Create database tables
models.Base.metadata.create_all(bind=engine)

# Migration: add new columns if they don't exist
with engine.connect() as conn:
    try:
        conn.execute(text("ALTER TABLE playlist_configs ADD COLUMN item_type VARCHAR DEFAULT 'playlist'"))
    except:
        pass
    try:
        conn.execute(text("ALTER TABLE playlist_configs ADD COLUMN artist_name VARCHAR"))
    except:
        pass
    try:
        conn.execute(text("ALTER TABLE playlist_configs ADD COLUMN picture_url VARCHAR"))
    except:
        pass
    conn.commit()

app = FastAPI(title="Tidalarius")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/api/auth", tags=["auth"])
app.include_router(playlists_router, prefix="/api/playlists", tags=["playlists"])
app.include_router(sync_router, prefix="/api/sync", tags=["sync"])
app.include_router(music_router, prefix="/api/music", tags=["music"])

@app.get("/api/health")
def health_check():
    return {"status": "ok"}

# Serve music files statically
MUSIC_DIR = os.environ.get("MUSIC_DIR", "/music")
os.makedirs(MUSIC_DIR, exist_ok=True)
app.mount("/music_files", StaticFiles(directory=MUSIC_DIR), name="music_files")

# Serve frontend statically in production
frontend_dist = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.exists(frontend_dist):
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

