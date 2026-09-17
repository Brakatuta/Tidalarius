from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, Depends
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import List
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
async def start_sync(playlist_id: str, db: Session = Depends(get_db)):
    config = db.query(models.PlaylistConfig).filter(models.PlaylistConfig.tidal_id == playlist_id).first()
    if not config:
        name = "Unknown Playlist"
        try:
            p = sync_engine.global_session.playlist(playlist_id)
            if p: name = p.name
        except: pass
        config = models.PlaylistConfig(tidal_id=playlist_id, name=name, qualities=["HIGH"])
        db.add(config)
        db.commit()
        db.refresh(config)
        
    qualities = config.qualities if config.qualities else ["HIGH"]
    
    # check if already running
    if sync_engine.active_jobs.get(playlist_id) in ["running", "paused"]:
        return {"status": "already running"}
        
    sync_engine.sync_queue.put({
        "playlist_id": playlist_id,
        "qualities": qualities
    })
    return {"status": "queued"}

@router.post("/track/{playlist_id}/{track_id}")
async def start_single_track_sync(playlist_id: str, track_id: int, db: Session = Depends(get_db)):
    config = db.query(models.PlaylistConfig).filter(models.PlaylistConfig.tidal_id == playlist_id).first()
    if not config:
        name = "Unknown Playlist"
        try:
            p = sync_engine.global_session.playlist(playlist_id)
            if p: name = p.name
        except: pass
        config = models.PlaylistConfig(tidal_id=playlist_id, name=name, qualities=["HIGH"])
        db.add(config)
        db.commit()
        db.refresh(config)
    
    qualities = config.qualities if config.qualities else ["HIGH"]
    
    # Put a special job in the queue that only targets this track
    sync_engine.sync_queue.put({
        "playlist_id": playlist_id,
        "qualities": qualities,
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
        
    playlist = sync_engine.global_session.playlist(playlist_id)
    playlist_name = playlist.name if playlist else config.name
    safe_name = sync_engine.sanitize_filename(playlist_name)
    playlist_dir = os.path.join(sync_engine.MUSIC_DIR, safe_name)
    
    if os.path.exists(playlist_dir):
        try:
            shutil.rmtree(playlist_dir)
            return {"status": "success", "message": "Deleted downloaded files"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    else:
        return {"status": "not_found", "message": "No files to delete"}

@router.delete('/track/{playlist_id}/{track_id}')
def delete_single_track(playlist_id: str, track_id: int):
    # Retrieve track details from Tidal to construct filename
    playlist = sync_engine.global_session.playlist(playlist_id)
    if not playlist:
        raise HTTPException(status_code=404, detail='Playlist not found')
    
    target_track = None
    seen_ids = set()
    offset = 0
    limit = 1000
    while True:
        batch = playlist.tracks(limit=limit, offset=offset)
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

            
    if not target_track:
        raise HTTPException(status_code=404, detail='Track not found in playlist')
        
    safe_name = sync_engine.sanitize_filename(playlist.name)
    playlist_dir = os.path.join(sync_engine.MUSIC_DIR, safe_name)
    
    track_num = target_track.track_num or 1
    artist_name = sync_engine.sanitize_filename(target_track.artist.name if target_track.artist else "Unknown Artist")
    album_name = sync_engine.sanitize_filename(target_track.album.name if target_track.album else "Unknown Album")
    track_title = sync_engine.sanitize_filename(target_track.name)
    
    expected_prefix = os.path.join(playlist_dir, artist_name, album_name, f"{track_num:02d} - {track_title}")
    
    deleted = False
    for ext in [".flac", ".m4a"]:
        full_path = expected_prefix + ext
        if os.path.exists(full_path):
            try:
                os.remove(full_path)
                deleted = True
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))
                
    if deleted:
        from ws_manager import manager
        manager.broadcast_sync({"type": "track_deleted", "playlist_id": playlist_id, "track_id": track_id})
        return {"status": "success", "message": "Track deleted"}
    else:
        return {"status": "not_found", "message": "File not found"}
