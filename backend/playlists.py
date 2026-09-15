from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Dict, Any
from pydantic import BaseModel

from database import get_db
import models
from tidal_auth import global_session

router = APIRouter()

class PlaylistConfigUpdate(BaseModel):
    sync_enabled: bool
    qualities: List[str]
    schedule: str | None = None

@router.get("/")
def get_playlists(db: Session = Depends(get_db)):
    if not global_session.check_login():
        raise HTTPException(status_code=401, detail="Not authenticated with Tidal")
    
    # 1. Fetch remote playlists from Tidal
    try:
        # User created playlists
        remote_playlists = global_session.user.playlists()
        # You might also want favorites: global_session.user.favorites.playlists()
        # For now, let's just use user.playlists() 
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch from Tidal: {str(e)}")

    # 2. Fetch local configs
    local_configs = db.query(models.PlaylistConfig).all()
    local_dict = {config.tidal_id: config.to_dict() for config in local_configs}

    # 3. Merge them
    result = []
    for p in remote_playlists:
        p_id = str(p.id)
        if p_id in local_dict:
            config = local_dict[p_id]
            # Ensure name is updated in case it changed on Tidal
            if config["name"] != p.name:
                db_item = db.query(models.PlaylistConfig).filter(models.PlaylistConfig.tidal_id == p_id).first()
                if db_item:
                    db_item.name = p.name
                    db.commit()
                    config["name"] = p.name
        else:
            config = {
                "tidal_id": p_id,
                "name": p.name,
                "sync_enabled": False,
                "qualities": ["HIGH"], # Default quality
                "schedule": None,
                "last_synced": None,
                "sync_status": "idle"
            }
            
        # Combine with remote info (track count, picture, etc. if available)
        # tidalapi Playlist object usually has `num_tracks`, `picture`, `creator` etc.
        item = {
            **config,
            "num_tracks": getattr(p, "num_tracks", 0),
            "picture_url": p.image(320) if hasattr(p, 'image') and callable(p.image) else None
        }
        result.append(item)
        
    return result

@router.post("/{playlist_id}/config")
def update_playlist_config(playlist_id: str, config: PlaylistConfigUpdate, db: Session = Depends(get_db)):
    if not global_session.check_login():
        raise HTTPException(status_code=401, detail="Not authenticated with Tidal")
        
    db_config = db.query(models.PlaylistConfig).filter(models.PlaylistConfig.tidal_id == playlist_id).first()
    
    if not db_config:
        # Fetch name from tidal if possible to save it
        name = "Unknown Playlist"
        try:
            p = global_session.playlist(playlist_id)
            if p:
                name = p.name
        except:
            pass
            
        db_config = models.PlaylistConfig(
            tidal_id=playlist_id,
            name=name
        )
        db.add(db_config)
    
    db_config.sync_enabled = config.sync_enabled
    db_config.qualities = config.qualities
    db_config.schedule = config.schedule
    
    db.commit()
    db.refresh(db_config)
    
    return db_config.to_dict()

