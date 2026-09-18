from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, Depends, Body
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import List, Optional
from ws_manager import manager
import sync_engine
from database import get_db, SessionLocal
import models
import os

router = APIRouter()

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # We don't really expect messages from client in this simple setup,
            # just keeping the connection open
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

@router.post("/start/{playlist_id}")
async def start_sync(playlist_id: str, item_type: str = "playlist", qualities: Optional[List[str]] = Body(None), db: Session = Depends(get_db)):
    from backend.tidal_auth import ensure_valid_session
    ensure_valid_session()
    
    config = db.query(models.PlaylistConfig).filter(models.PlaylistConfig.tidal_id == playlist_id).first()
    real_name = None
    real_pic = None
    real_artist = None
    try:
        if item_type == "album":
            p = sync_engine.global_session.album(playlist_id)
            if p:
                real_name = p.name
                real_artist = getattr(p.artist, 'name', None) if getattr(p, 'artist', None) else None
                real_pic = p.image(320) if hasattr(p, 'image') and callable(p.image) else None
        elif item_type == "track":
            p = sync_engine.global_session.track(playlist_id)
            if p:
                real_name = p.name
                real_artist = getattr(p.artist, 'name', None) if getattr(p, 'artist', None) else None
        else:
            p = sync_engine.global_session.playlist(playlist_id)
            if p:
                real_name = p.name
                real_pic = p.image(320) if hasattr(p, 'image') and callable(p.image) else None
    except Exception as e:
        print(f"[START_SYNC] Error fetching item metadata: {e}", flush=True)

    if not config:
        config = models.PlaylistConfig(
            tidal_id=playlist_id, 
            item_type=item_type, 
            name=real_name or "Unknown", 
            artist_name=real_artist,
            picture_url=real_pic,
            qualities=["HIGH"]
        )
        db.add(config)
        db.commit()
        db.refresh(config)
    else:
        if real_name and (not config.name or config.name in ["Unknown", "Unknown Item", "Unknown Playlist"]):
            config.name = real_name
            if real_pic and not config.picture_url: config.picture_url = real_pic
            if real_artist and not config.artist_name: config.artist_name = real_artist
            db.commit()
        
    dl_qualities = qualities if qualities else (config.qualities if config.qualities else ["HIGH"])
    
    # check if already running
    if sync_engine.active_jobs.get(playlist_id) in ["running", "paused"]:
        return {"status": "already running"}
        
    sync_engine.sync_queue.put({
        "playlist_id": playlist_id,
        "qualities": dl_qualities
    })
    return {"status": "queued"}

@router.post("/track/{playlist_id}/{track_id}")
async def start_single_track_sync(playlist_id: str, track_id: int, qualities: Optional[List[str]] = Body(None), db: Session = Depends(get_db)):
    from backend.tidal_auth import ensure_valid_session
    ensure_valid_session()
    
    config = db.query(models.PlaylistConfig).filter(models.PlaylistConfig.tidal_id == playlist_id).first()
    item_type = "playlist"
    real_name = None
    real_pic = None
    real_artist = None
    try:
        p = sync_engine.global_session.playlist(playlist_id)
        if p: 
            real_name = p.name
            real_pic = p.image(320) if hasattr(p, 'image') and callable(p.image) else None
    except: pass
    if not real_name:
        try:
            a = sync_engine.global_session.album(playlist_id)
            if a:
                real_name = a.name
                real_artist = getattr(a.artist, 'name', None) if getattr(a, 'artist', None) else None
                real_pic = a.image(320) if hasattr(a, 'image') and callable(a.image) else None
                item_type = "album"
        except: pass

    if not config:
        config = models.PlaylistConfig(
            tidal_id=playlist_id, 
            name=real_name or "Unknown", 
            artist_name=real_artist,
            picture_url=real_pic,
            item_type=item_type, 
            qualities=["HIGH"]
        )
        db.add(config)
        db.commit()
        db.refresh(config)
    else:
        if real_name and (not config.name or config.name in ["Unknown", "Unknown Item", "Unknown Playlist"]):
            config.name = real_name
            if real_pic and not config.picture_url: config.picture_url = real_pic
            if real_artist and not config.artist_name: config.artist_name = real_artist
            db.commit()
    
    # Use provided qualities if given, otherwise fall back to config
    dl_qualities = qualities if qualities else (config.qualities if config.qualities else ["HIGH"])
    
    # Put a special job in the queue that only targets this track
    sync_engine.sync_queue.put({
        "playlist_id": playlist_id,
        "qualities": dl_qualities,
        "track_id": track_id
    })
    return {"status": "queued"}

@router.post("/pause/{playlist_id}")
async def pause_sync(playlist_id: str):
    if playlist_id in sync_engine.active_jobs:
        sync_engine.active_jobs[playlist_id] = "paused"
        return {"status": "paused"}
    return {"status": "not running"}

@router.post("/resume/{playlist_id}")
async def resume_sync(playlist_id: str):
    if playlist_id in sync_engine.active_jobs:
        sync_engine.active_jobs[playlist_id] = "running"
        return {"status": "resumed"}
    return {"status": "not running"}

@router.post("/cancel/{playlist_id}")
async def cancel_sync(playlist_id: str):
    if playlist_id in sync_engine.active_jobs:
        sync_engine.active_jobs[playlist_id] = "cancelled"
        return {"status": "cancelled"}
    return {"status": "not running"}

@router.get("/status/{playlist_id}")
def get_sync_status(playlist_id: str):
    job_status = sync_engine.active_jobs.get(playlist_id, "idle")
    if job_status == "running":
        job_status = "syncing"
        
    logs = sync_engine.active_logs.get(playlist_id, [])
    progress = sync_engine.active_progress.get(playlist_id, 0)
    return {
        "status": job_status,
        "logs": logs,
        "progress": progress
    }

@router.get("/report")
def get_report(path: str):
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Report not found")
    
    filename = os.path.basename(path)
    return FileResponse(path, media_type='text/plain', filename=filename)


@router.get('/report/latest/{playlist_id}')
def get_latest_report(playlist_id: str, db: Session = Depends(get_db)):
    config = db.query(models.PlaylistConfig).filter(models.PlaylistConfig.tidal_id == playlist_id).first()
    if not config:
        raise HTTPException(status_code=404, detail='Playlist not found')

    safe_name = sync_engine.sanitize_filename(config.name)
    playlist_dir = os.path.join(sync_engine.MUSIC_DIR, safe_name)

    if not os.path.exists(playlist_dir):
        raise HTTPException(status_code=404, detail='No downloads found')

    sync_engine.prune_sync_reports(playlist_dir, max_keep=3)
    log_files = [f for f in os.listdir(playlist_dir) if f.startswith('sync_report_') and f.endswith('.log')]
    if not log_files:
        raise HTTPException(status_code=404, detail='No reports found')

    latest_log = sorted(log_files, reverse=True)[0]
    path = os.path.join(playlist_dir, latest_log)
    return FileResponse(path, media_type='text/plain', filename=latest_log)

@router.delete('/delete/{playlist_id}')
def delete_downloads(playlist_id: str, db: Session = Depends(get_db)):
    import shutil
    config = db.query(models.PlaylistConfig).filter(models.PlaylistConfig.tidal_id == playlist_id).first()
    if not config:
        raise HTTPException(status_code=404, detail='Playlist not found')
        
    try:
        if getattr(config, 'item_type', 'playlist') == 'album':
            item = sync_engine.global_session.album(playlist_id)
        elif getattr(config, 'item_type', 'playlist') == 'track':
            item = sync_engine.global_session.track(playlist_id)
        else:
            item = sync_engine.global_session.playlist(playlist_id)
    except Exception:
        item = None
        
    dirs_to_check = []
    if item and getattr(item, 'name', None):
        dirs_to_check.append(os.path.join(sync_engine.MUSIC_DIR, sync_engine.sanitize_filename(item.name)))
    if config.name:
        dirs_to_check.append(os.path.join(sync_engine.MUSIC_DIR, sync_engine.sanitize_filename(config.name)))

    deleted_any = False
    for d in set(dirs_to_check):
        if os.path.exists(d):
            try:
                shutil.rmtree(d)
                deleted_any = True
            except Exception as e:
                print(f"Error removing {d}: {e}")
                
    config.last_synced = None
    config.sync_status = "idle"
    db.commit()
    
    manager.broadcast_sync({"type": "playlist_downloads_deleted", "playlist_id": playlist_id})
    manager.broadcast_sync({"type": "track_deleted", "playlist_id": playlist_id, "track_id": playlist_id})
    manager.broadcast_sync({"type": "library_updated", "playlist_id": playlist_id, "action": "downloads_deleted"})
    return {"status": "success", "message": "Deleted downloaded files" if deleted_any else "No files to delete"}

def cleanup_artist_folder_if_empty(deleted_file_path: str, playlist_dir: str):
    """
    Checks the parent album and artist folders of the deleted file.
    If the artist folder contains no other audio tracks, deletes the entire artist folder samt Inhalt.
    If only the album folder has no other audio tracks, deletes the album folder.
    Also cleans up playlist_dir if no audio files remain.
    """
    import shutil
    try:
        AUDIO_EXTS = (".flac", ".m4a", ".mp3", ".opus")
        playlist_dir_real = os.path.realpath(playlist_dir)
        music_dir_real = os.path.realpath(sync_engine.MUSIC_DIR)

        album_dir = os.path.realpath(os.path.dirname(deleted_file_path))
        artist_dir = os.path.realpath(os.path.dirname(album_dir))

        target_artist_dir = None
        if artist_dir != playlist_dir_real and artist_dir != music_dir_real:
            try:
                rel = os.path.relpath(artist_dir, playlist_dir_real)
                if not rel.startswith(".."):
                    target_artist_dir = artist_dir
            except ValueError:
                pass

        if not target_artist_dir and album_dir != playlist_dir_real and album_dir != music_dir_real:
            try:
                rel = os.path.relpath(album_dir, playlist_dir_real)
                if not rel.startswith(".."):
                    target_artist_dir = album_dir
            except ValueError:
                pass

        if target_artist_dir and os.path.exists(target_artist_dir):
            remaining_audio = []
            for root, _, files in os.walk(target_artist_dir):
                for f in files:
                    if f.lower().endswith(AUDIO_EXTS):
                        remaining_audio.append(os.path.join(root, f))

            if not remaining_audio:
                shutil.rmtree(target_artist_dir, ignore_errors=True)
                print(f"[CLEANUP] Deleted artist folder with all contents: {target_artist_dir}", flush=True)
            else:
                if album_dir != target_artist_dir and os.path.exists(album_dir):
                    album_audio = []
                    for root, _, files in os.walk(album_dir):
                        for f in files:
                            if f.lower().endswith(AUDIO_EXTS):
                                album_audio.append(os.path.join(root, f))
                    if not album_audio:
                        shutil.rmtree(album_dir, ignore_errors=True)
                        print(f"[CLEANUP] Deleted empty album folder: {album_dir}", flush=True)

        # In addition, check if playlist_dir has any audio files left (e.g. for single-track items)
        if os.path.exists(playlist_dir_real) and playlist_dir_real != music_dir_real:
            playlist_audio = []
            for root, _, files in os.walk(playlist_dir_real):
                for f in files:
                    if f.lower().endswith(AUDIO_EXTS):
                        playlist_audio.append(os.path.join(root, f))
            if not playlist_audio:
                shutil.rmtree(playlist_dir_real, ignore_errors=True)
                print(f"[CLEANUP] Deleted empty playlist/item folder: {playlist_dir_real}", flush=True)
    except Exception as e:
        print(f"[CLEANUP] Error during folder cleanup: {e}", flush=True)

@router.delete('/track/{playlist_id}/{track_id}')
def delete_single_track(playlist_id: str, track_id: int, db: Session = Depends(get_db)):
    config = db.query(models.PlaylistConfig).filter(models.PlaylistConfig.tidal_id == playlist_id).first()
    item_type = getattr(config, 'item_type', 'playlist') if config else 'playlist'
    
    parent = None
    try:
        if item_type == 'album':
            parent = sync_engine.global_session.album(playlist_id)
        elif item_type == 'track':
            parent = sync_engine.global_session.track(playlist_id)
        else:
            parent = sync_engine.global_session.playlist(playlist_id)
    except Exception:
        pass
    
    target_track = None
    if parent:
        if item_type == 'track':
            if getattr(parent, 'id', None) == track_id:
                target_track = parent
        elif item_type == 'album':
            for track in parent.tracks():
                if track.id == track_id:
                    target_track = track
                    break
        else:
            seen_ids = set()
            offset = 0
            limit = 1000
            while True:
                batch = parent.tracks(limit=limit, offset=offset)
                if not batch: break
                for track in batch:
                    if track.id not in seen_ids:
                        seen_ids.add(track.id)
                        if track.id == track_id:
                            target_track = track
                            break
                if target_track: break
                offset += len(batch)
                if len(batch) < limit: break
            
    # Try to determine folder name on disk
    possible_dir_names = []
    if config and config.name:
        possible_dir_names.append(sync_engine.sanitize_filename(config.name))
    if parent and getattr(parent, 'name', None):
        possible_dir_names.append(sync_engine.sanitize_filename(parent.name))

    track_num = getattr(target_track, 'track_num', 1) or 1
    track_title = sync_engine.sanitize_filename(getattr(target_track, 'name', '')) if target_track else ''

    deleted = False
    deleted_file_path = None
    matched_playlist_dir = None
    for dir_name in possible_dir_names:
        playlist_dir = os.path.join(sync_engine.MUSIC_DIR, dir_name)
        if not os.path.exists(playlist_dir):
            continue

        # If we have target_track info, check expected paths
        if target_track:
            artist_name = sync_engine.sanitize_filename(target_track.artist.name if getattr(target_track, 'artist', None) else "Unknown Artist")
            album_name = sync_engine.sanitize_filename(target_track.album.name if getattr(target_track, 'album', None) else "Unknown Album")
            expected_prefix = os.path.join(playlist_dir, artist_name, album_name, f"{track_num:02d} - {track_title}")
            for ext in [".flac", ".m4a", ".mp3", ".opus"]:
                full_path = expected_prefix + ext
                if os.path.exists(full_path):
                    try:
                        os.remove(full_path)
                        deleted = True
                        deleted_file_path = full_path
                        matched_playlist_dir = playlist_dir
                        break
                    except Exception as e:
                        raise HTTPException(status_code=500, detail=str(e))
        
        # Fallback recursive search in playlist_dir
        if not deleted:
            for root, _, files in os.walk(playlist_dir):
                for file in files:
                    lower_f = file.lower()
                    match = False
                    if track_title and track_title.lower() in lower_f and lower_f.endswith((".flac", ".m4a", ".mp3", ".opus")):
                        match = True
                    elif str(track_id) in lower_f and lower_f.endswith((".flac", ".m4a", ".mp3", ".opus")):
                        match = True
                    elif target_track and lower_f.startswith(f"{track_num:02d} - ") and lower_f.endswith((".flac", ".m4a", ".mp3", ".opus")):
                        match = True

                    if match:
                        target_file = os.path.join(root, file)
                        try:
                            os.remove(target_file)
                            deleted = True
                            deleted_file_path = target_file
                            matched_playlist_dir = playlist_dir
                            break
                        except Exception as e:
                            raise HTTPException(status_code=500, detail=str(e))
                if deleted:
                    break
        if deleted:
            break

    if deleted and deleted_file_path and matched_playlist_dir:
        cleanup_artist_folder_if_empty(deleted_file_path, matched_playlist_dir)
                
    if config and item_type == 'track':
        config.last_synced = None
        config.sync_status = "idle"
        db.commit()

    if deleted:
        manager.broadcast_sync({"type": "track_deleted", "playlist_id": playlist_id, "track_id": track_id})
        return {"status": "success", "message": "Track deleted"}
    else:
        # Broadcast anyway so frontend removes local state if file was already gone
        manager.broadcast_sync({"type": "track_deleted", "playlist_id": playlist_id, "track_id": track_id})
        return {"status": "success", "message": "Track removed"}

