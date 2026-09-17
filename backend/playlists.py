from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Dict, Any
from pydantic import BaseModel

import os
from database import get_db
import models
from tidal_auth import global_session
import sync_engine

router = APIRouter()

class PlaylistConfigUpdate(BaseModel):
    item_type: str | None = "playlist"
    name: str | None = None
    artist_name: str | None = None
    picture_url: str | None = None
    sync_enabled: bool
    qualities: List[str]
    schedule: str | None = None

@router.get("/")
def get_playlists(db: Session = Depends(get_db)):
    if not global_session.check_login():
        raise HTTPException(status_code=401, detail="Not authenticated with Tidal")
    
    # 1. Fetch remote playlists from Tidal
    remote_playlists = []
    try:
        remote_playlists = global_session.user.playlists()
    except Exception as e:
        print(f"Failed to fetch from Tidal: {str(e)}")

    # 2. Fetch local configs & verify disk existence for synced items
    local_configs = db.query(models.PlaylistConfig).all()
    for config in local_configs:
        if config.last_synced:
            safe_name = sync_engine.sanitize_filename(config.name) if config.name else ""
            target_dir = os.path.join(sync_engine.MUSIC_DIR, safe_name) if safe_name else ""
            has_files = False
            if target_dir and os.path.exists(target_dir):
                for root, _, files in os.walk(target_dir):
                    if any(f.lower().endswith(('.flac', '.m4a', '.mp3', '.opus')) for f in files):
                        has_files = True
                        break
            if not has_files:
                config.last_synced = None
                config.sync_status = "idle"
                db.commit()

    local_dict = {config.tidal_id: config.to_dict() for config in local_configs}

    # 3. Merge them
    result = []
    seen_ids = set()
    for p in remote_playlists:
        p_id = str(p.id)
        seen_ids.add(p_id)
        if p_id in local_dict:
            merged = local_dict[p_id]
            merged["name"] = p.name
            merged["is_remote"] = True
            try:
                merged["picture_url"] = p.image(320) if hasattr(p, 'image') and callable(p.image) else None
            except:
                pass
            result.append(merged)
        else:
            pic_url = None
            try:
                pic_url = p.image(320) if hasattr(p, 'image') and callable(p.image) else None
            except:
                pass
            result.append({
                "tidal_id": p_id,
                "item_type": "playlist",
                "name": p.name,
                "artist_name": None,
                "picture_url": pic_url,
                "sync_enabled": False,
                "qualities": [],
                "schedule": None,
                "last_synced": None,
                "sync_status": "idle",
                "is_remote": True
            })

    # Add any local items (albums, tracks, or deleted remote playlists) that weren't in remote_playlists
    for config in local_configs:
        if config.tidal_id not in seen_ids:
            result.append(config.to_dict())

    return result

@router.post("/{playlist_id}/config")
def update_playlist_config(playlist_id: str, config: PlaylistConfigUpdate, db: Session = Depends(get_db)):
    if not global_session.check_login():
        raise HTTPException(status_code=401, detail="Not authenticated with Tidal")
        
    db_config = db.query(models.PlaylistConfig).filter(models.PlaylistConfig.tidal_id == playlist_id).first()
    
    if not db_config:
        db_config = models.PlaylistConfig(
            tidal_id=playlist_id,
            item_type=config.item_type,
            name=config.name or "Unknown",
            artist_name=config.artist_name,
            picture_url=config.picture_url,
            sync_enabled=config.sync_enabled,
            qualities=config.qualities,
            schedule=config.schedule
        )
        db.add(db_config)
    else:
        db_config.sync_enabled = config.sync_enabled
        db_config.qualities = config.qualities
        db_config.schedule = config.schedule
        
    db.commit()
    return {"status": "success"}

@router.delete("/{playlist_id}")
def delete_playlist_config(playlist_id: str, db: Session = Depends(get_db)):
    db_config = db.query(models.PlaylistConfig).filter(models.PlaylistConfig.tidal_id == playlist_id).first()
    if db_config:
        db.delete(db_config)
        db.commit()
        return {"status": "success"}
    raise HTTPException(status_code=404, detail="Item not found in library")
