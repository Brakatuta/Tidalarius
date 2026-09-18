from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Dict, Any
from pydantic import BaseModel

import os
import datetime
from database import get_db
import models
from tidal_auth import global_session
import sync_engine
from ws_manager import manager
from music_api import get_cached_image_url, invalidate_metadata_cache

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
        if config.last_synced or config.item_type == "track":
            safe_name = sync_engine.sanitize_filename(config.name) if config.name else ""
            target_dir = os.path.join(sync_engine.MUSIC_DIR, safe_name) if safe_name else ""
            has_files = False
            detected_quality = None
            if target_dir and os.path.exists(target_dir):
                for root, _, files in os.walk(target_dir):
                    for f in files:
                        if f.lower().endswith(('.flac', '.m4a', '.mp3', '.opus')):
                            has_files = True
                            full_path = os.path.join(root, f)
                            try:
                                import mutagen
                                audio = mutagen.File(full_path)
                                if audio:
                                    comments = audio.get("COMMENT", audio.get("\xa9cmt", []))
                                    for c in comments:
                                        if isinstance(c, str) and c.startswith("QUALITY="):
                                            detected_quality = c.replace("QUALITY=", "").strip()
                                            break
                            except Exception:
                                pass
                            if not detected_quality:
                                detected_quality = "LOSSLESS" if f.lower().endswith('.flac') else "HIGH"
                            break
                    if has_files:
                        break
            if not has_files:
                config.last_synced = None
                config.sync_status = "idle"
                db.commit()
            elif config.item_type == "track":
                changed = False
                if not config.last_synced:
                    config.last_synced = datetime.datetime.utcnow()
                    changed = True
                if detected_quality and config.qualities != [detected_quality]:
                    config.qualities = [detected_quality]
                    changed = True
                if changed:
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
                raw_pic = p.image(320) if hasattr(p, 'image') and callable(p.image) else None
                if raw_pic:
                    merged["picture_url"] = raw_pic
            except:
                pass
            merged["picture_url"] = get_cached_image_url(merged.get("picture_url"))
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
                "picture_url": get_cached_image_url(pic_url),
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
            item_dict = config.to_dict()
            item_dict["picture_url"] = get_cached_image_url(item_dict.get("picture_url"))
            result.append(item_dict)

    return result

@router.post("/{playlist_id}/config")
def update_playlist_config(playlist_id: str, config: PlaylistConfigUpdate, db: Session = Depends(get_db)):
    if not global_session.check_login():
        raise HTTPException(status_code=401, detail="Not authenticated with Tidal")
        
    db_config = db.query(models.PlaylistConfig).filter(models.PlaylistConfig.tidal_id == playlist_id).first()
    
    if not db_config:
        name = config.name
        picture_url = config.picture_url
        item_type = config.item_type or "playlist"
        artist_name = config.artist_name
        if not name or name in ["Unknown", "Unknown Item", "Unknown Playlist"]:
            try:
                p = global_session.playlist(playlist_id)
                if p and p.name:
                    name = p.name
                    picture_url = p.image(320) if hasattr(p, 'image') and callable(p.image) else None
                    item_type = "playlist"
            except:
                pass
            if not name or name in ["Unknown", "Unknown Item", "Unknown Playlist"]:
                try:
                    a = global_session.album(playlist_id)
                    if a and a.name:
                        name = a.name
                        picture_url = a.image(320) if hasattr(a, 'image') and callable(a.image) else None
                        artist_name = a.artist.name if hasattr(a, 'artist') and a.artist else None
                        item_type = "album"
                except:
                    pass

        db_config = models.PlaylistConfig(
            tidal_id=playlist_id,
            item_type=item_type,
            name=name or "Unknown",
            artist_name=artist_name,
            picture_url=picture_url,
            sync_enabled=config.sync_enabled,
            qualities=config.qualities,
            schedule=config.schedule
        )
        db.add(db_config)
    else:
        db_config.sync_enabled = config.sync_enabled
        db_config.qualities = config.qualities
        db_config.schedule = config.schedule
        if config.name and config.name not in ["Unknown", "Unknown Item", "Unknown Playlist"]:
            db_config.name = config.name
        elif not db_config.name or db_config.name in ["Unknown", "Unknown Item", "Unknown Playlist"]:
            try:
                p = global_session.playlist(playlist_id)
                if p and p.name: db_config.name = p.name
            except:
                try:
                    a = global_session.album(playlist_id)
                    if a and a.name: db_config.name = a.name
                except: pass
        if config.artist_name: db_config.artist_name = config.artist_name
        if config.picture_url: db_config.picture_url = config.picture_url
        if config.item_type: db_config.item_type = config.item_type
        
    db.commit()
    invalidate_metadata_cache(playlist_id)
    manager.broadcast_sync({
        "type": "library_updated",
        "playlist_id": playlist_id,
        "action": "saved",
        "item_type": db_config.item_type,
        "name": db_config.name
    })
    return {"status": "success"}

@router.delete("/{playlist_id}")
def delete_playlist_config(playlist_id: str, db: Session = Depends(get_db)):
    db_config = db.query(models.PlaylistConfig).filter(models.PlaylistConfig.tidal_id == playlist_id).first()
    if db_config:
        item_type = db_config.item_type
        name = db_config.name
        db.delete(db_config)
        db.commit()
        invalidate_metadata_cache(playlist_id)
        manager.broadcast_sync({
            "type": "library_updated",
            "playlist_id": playlist_id,
            "action": "deleted",
            "item_type": item_type,
            "name": name
        })
        return {"status": "success"}
    raise HTTPException(status_code=404, detail="Item not found in library")
