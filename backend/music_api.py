import os
import re
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
import models
from tidal_auth import global_session
from typing import List, Dict

router = APIRouter()
MUSIC_DIR = os.environ.get("MUSIC_DIR", "/music")

def sanitize_filename(name):
    # Same implementation as in sync_engine.py
    return re.sub(r'[\\/*?:"<>|]', "", name)

@router.get("/playlists")
def get_downloaded_playlists(db: Session = Depends(get_db)):
    """Returns a list of playlists that actually exist in the local music directory."""
    if not os.path.exists(MUSIC_DIR):
        return []
        
    downloaded_folders = [f.name for f in os.scandir(MUSIC_DIR) if f.is_dir()]
    
    local_configs = db.query(models.PlaylistConfig).all()
    
    result = []
    for config in local_configs:
        safe_name = sanitize_filename(config.name)
        if safe_name in downloaded_folders:
            picture_url = None
            if global_session.check_login():
                try:
                    p = global_session.playlist(config.tidal_id)
                    picture_url = p.image(320) if hasattr(p, 'image') and callable(p.image) else None
                except:
                    pass
            
            result.append({
                "tidal_id": config.tidal_id,
                "name": config.name,
                "folder_name": safe_name,
                "picture_url": picture_url,
                "last_synced": config.last_synced.isoformat() if config.last_synced else None
            })
            
    return result

@router.get("/playlist/{playlist_id}")
def get_playlist_details(playlist_id: str, db: Session = Depends(get_db)):
    """Returns the tracklist for a playlist, indicating which tracks are available locally."""
    if not global_session.check_login():
        raise HTTPException(status_code=401, detail="Not authenticated with Tidal. Cannot fetch track metadata.")
        
    try:
        p = global_session.playlist(playlist_id)
        
        # Fetch tracks with pagination to avoid tidalapi limit bugs and duplicate pages
        tracks = []
        seen_ids = set()
        offset = 0
        limit = 1000
        while True:
            batch = p.tracks(limit=limit, offset=offset)
            if not batch:
                break
            for t in batch:
                if t.id not in seen_ids:
                    tracks.append(t)
                    seen_ids.add(t.id)
            offset += len(batch)
            if len(batch) < limit:
                break
                
        playlist_name = p.name
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch playlist from Tidal: {str(e)}")
        
    config = db.query(models.PlaylistConfig).filter(models.PlaylistConfig.tidal_id == playlist_id).first()
    if config:
        playlist_name = config.name
        
    safe_name = sanitize_filename(playlist_name)
    playlist_dir = os.path.join(MUSIC_DIR, safe_name)
        
    local_files = []
    if os.path.exists(playlist_dir):
        local_files = [f.name for f in os.scandir(playlist_dir) if f.is_file()]
        
    result_tracks = []
    for idx, track in enumerate(tracks, start=1):
        track_num = track.track_num or 1
        artist_name = sanitize_filename(track.artist.name if track.artist else "Unknown Artist")
        album_name = sanitize_filename(track.album.name if track.album else "Unknown Album")
        track_title = sanitize_filename(track.name)
        
        expected_prefix = os.path.join(artist_name, album_name, f"{track_num:02d} - {track_title}")
        
        local_filename = None
        quality_label = "Unknown"
        
        # Check possible extensions
        for ext in [".flac", ".m4a"]:
            rel_path = expected_prefix + ext
            full_path = os.path.join(playlist_dir, rel_path)
            if os.path.exists(full_path):
                local_filename = rel_path
                # Default guess based on extension in case tag is missing
                quality_label = "LOSSLESS" if ext == ".flac" else "HIGH"
                
                # Try to extract the true quality from mutagen tag
                try:
                    import mutagen
                    audio = mutagen.File(full_path)
                    if audio is not None:
                        # FLAC uses COMMENT, MP4 uses \xa9cmt
                        comments = audio.get("COMMENT", audio.get("\xa9cmt", []))
                        for c in comments:
                            if isinstance(c, str) and c.startswith("QUALITY="):
                                quality_label = c.replace("QUALITY=", "").strip()
                                break
                except Exception:
                    pass
                break
                
        # Must url encode the filename and playlist name for the URL!
        import urllib.parse
        encoded_safe_name = urllib.parse.quote(safe_name)
        
        stream_url = None
        if local_filename:
            # We must quote each part of the relative path separately to preserve the forward slashes
            encoded_local_filename = "/".join([urllib.parse.quote(p) for p in local_filename.replace('\\', '/').split('/')])
            stream_url = f"/music_files/{encoded_safe_name}/{encoded_local_filename}"
        else:
            quality_label = "Unknown"
                
        result_tracks.append({
            "id": track.id,
            "title": track.name,
            "artist": track.artist.name if track.artist else "Unknown Artist",
            "album": track.album.name if track.album else "Unknown Album",
            "duration": track.duration, # in seconds
            "track_num": track_num,
            "playlist_pos": idx,
            "picture_url": track.album.image(320) if track.album and hasattr(track.album, 'image') and callable(track.album.image) else None,
            "is_downloaded": local_filename is not None,
            "stream_url": stream_url,
            "quality": quality_label
        })
        
    return {
        "tidal_id": playlist_id,
        "name": playlist_name,
        "picture_url": p.image(640) if hasattr(p, 'image') and callable(p.image) else None,
        "tracks": result_tracks
    }

