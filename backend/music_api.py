import os
import re
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from database import get_db
import models
from tidal_auth import global_session
from typing import List, Dict, Optional

router = APIRouter()
MUSIC_DIR = os.environ.get("MUSIC_DIR", "/music")

def sanitize_filename(name):
    # Same implementation as in sync_engine.py
    return re.sub(r'[\\/*?:"<>|]', "", name)

def resolve_track_quality(tidal_track) -> str:
    raw_q = getattr(tidal_track, 'audio_quality', None)
    if not raw_q:
        tags = getattr(tidal_track, 'media_metadata_tags', None)
        if tags and isinstance(tags, list) and len(tags) > 0:
            raw_q = tags[0]
    
    if raw_q:
        q_upper = str(raw_q).upper()
        if "HI_RES" in q_upper or "MAX" in q_upper:
            return "HI_RES_LOSSLESS"
        elif "LOSSLESS" in q_upper:
            return "LOSSLESS"
        elif "HIGH" in q_upper:
            return "HIGH"
        elif "LOW" in q_upper:
            return "LOW"
    return "HIGH"

@router.get("/downloaded")
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
    from backend.tidal_auth import ensure_valid_session
    if not ensure_valid_session():
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
                
        playlist_name = p.name or "Playlist"
    except Exception as e:
        if "401" in str(e) and ensure_valid_session():
            try:
                p = global_session.playlist(playlist_id)
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
                playlist_name = p.name or "Playlist"
            except Exception as e2:
                raise HTTPException(status_code=500, detail=f"Failed to fetch playlist from Tidal: {str(e2)}")
        else:
            raise HTTPException(status_code=500, detail=f"Failed to fetch playlist from Tidal: {str(e)}")
        
    config = db.query(models.PlaylistConfig).filter(models.PlaylistConfig.tidal_id == playlist_id).first()
    if config:
        if config.name and config.name not in ["Unknown", "Unknown Item", "Unknown Playlist"]:
            playlist_name = config.name
        elif playlist_name and playlist_name not in ["Unknown", "Unknown Item", "Unknown Playlist"]:
            # Auto-repair DB config if it had a placeholder name
            config.name = playlist_name
            db.commit()
        
    # Detect playlist directory on disk robustly
    candidate_names = []
    if playlist_name: candidate_names.append(sanitize_filename(playlist_name))
    if getattr(p, 'name', None): candidate_names.append(sanitize_filename(p.name))
    if config and config.name: candidate_names.append(sanitize_filename(config.name))
    
    seen = set()
    candidate_names = [c for c in candidate_names if c and not (c in seen or seen.add(c))]
    
    playlist_dir = None
    safe_name = sanitize_filename(playlist_name)
    
    for cname in candidate_names:
        cand_path = os.path.join(MUSIC_DIR, cname)
        if os.path.exists(cand_path) and os.path.isdir(cand_path):
            playlist_dir = cand_path
            safe_name = cname
            break
            
    if not playlist_dir and os.path.exists(MUSIC_DIR):
        existing_dirs = {entry.name.lower(): entry.name for entry in os.scandir(MUSIC_DIR) if entry.is_dir()}
        for cname in candidate_names:
            if cname.lower() in existing_dirs:
                real_name = existing_dirs[cname.lower()]
                playlist_dir = os.path.join(MUSIC_DIR, real_name)
                safe_name = real_name
                break
                
    if not playlist_dir:
        playlist_dir = os.path.join(MUSIC_DIR, safe_name)
        
    # Collect all local files in playlist directory with relative paths for fast lookup & fuzzy matching
    local_files_map = {}
    if os.path.exists(playlist_dir):
        for root, _, files in os.walk(playlist_dir):
            for file in files:
                rel_path = os.path.relpath(os.path.join(root, file), playlist_dir)
                local_files_map[file.lower()] = rel_path
        
    result_tracks = []
    for idx, track in enumerate(tracks, start=1):
        track_num = track.track_num or 1
        artist_name = sanitize_filename(track.artist.name if track.artist else "Unknown Artist")
        album_name = sanitize_filename(track.album.name if track.album else "Unknown Album")
        safe_title = sanitize_filename(track.name)
        
        expected_prefix = os.path.join(artist_name, album_name, f"{track_num:02d} - {safe_title}")
        
        is_downloaded = False
        local_filename = None
        quality_label = resolve_track_quality(track)
        stream_url = f"/api/music/stream/{track.id}"
        
        # 1. Exact path check
        for ext in [".flac", ".m4a", ".mp3", ".opus"]:
            rel_path = expected_prefix + ext
            full_path = os.path.join(playlist_dir, rel_path)
            if os.path.exists(full_path):
                is_downloaded = True
                local_filename = rel_path
                quality_label = "LOSSLESS" if ext == ".flac" else "HIGH"
                
                try:
                    import mutagen
                    audio = mutagen.File(full_path)
                    if audio is not None:
                        comments = audio.get("COMMENT", audio.get("\xa9cmt", []))
                        for c in comments:
                            if isinstance(c, str) and c.startswith("QUALITY="):
                                quality_label = c.replace("QUALITY=", "").strip()
                                break
                except Exception:
                    pass
                break
                
        # 2. Fuzzy match fallback in case of tag discrepancies
        if not is_downloaded:
            for lf_lower, rel_path in local_files_map.items():
                if safe_title.lower() in lf_lower:
                    full_path = os.path.join(playlist_dir, rel_path)
                    is_downloaded = True
                    local_filename = rel_path
                    quality_label = "LOSSLESS" if lf_lower.endswith(".flac") else "HIGH"
                    
                    try:
                        import mutagen
                        audio = mutagen.File(full_path)
                        if audio is not None:
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
        
        if is_downloaded and local_filename:
            encoded_local_filename = "/".join([urllib.parse.quote(p) for p in local_filename.replace('\\', '/').split('/')])
            stream_url = f"/music_files/{encoded_safe_name}/{encoded_local_filename}"
                
        result_tracks.append({
            "id": track.id,
            "title": track.name,
            "artist": track.artist.name if track.artist else "Unknown Artist",
            "album": track.album.name if track.album else "Unknown Album",
            "duration": track.duration, # in seconds
            "track_num": track_num,
            "playlist_pos": idx,
            "picture_url": track.album.image(320) if track.album and hasattr(track.album, 'image') and callable(track.album.image) else None,
            "is_downloaded": is_downloaded,
            "stream_url": stream_url,
            "quality": quality_label
        })
        
    return {
        "tidal_id": playlist_id,
        "name": playlist_name,
        "picture_url": p.image(640) if hasattr(p, 'image') and callable(p.image) else None,
        "tracks": result_tracks
    }

@router.get("/stream/{track_id}")
def stream_track_from_tidal(track_id: int, quality: str = "HIGH"):
    """Directly stream a track from Tidal if it's not downloaded, with fallback logic."""
    try:
        from backend.tidal_auth import global_session, save_session
        import tidalapi
        
        quality_map = {
            "MAX": tidalapi.Quality.hi_res_lossless,
            "HI_RES_LOSSLESS": tidalapi.Quality.hi_res_lossless,
            "LOSSLESS": tidalapi.Quality.high_lossless,
            "HIGH": tidalapi.Quality.low_320k,
            "LOW": tidalapi.Quality.low_96k,
        }
        
        # Define the fallback chain
        fallback_chain = ["MAX", "LOSSLESS", "HIGH", "LOW"]
        
        # Start from the requested quality (or its closest match in the chain)
        start_idx = fallback_chain.index("HIGH") # Default fallback
        if quality in fallback_chain:
            start_idx = fallback_chain.index(quality)
        elif quality == "HI_RES_LOSSLESS":
            start_idx = fallback_chain.index("MAX")
            
        qualities_to_try = fallback_chain[start_idx:]
        
        old_quality = global_session.config.quality
        
        for idx, q_str in enumerate(qualities_to_try):
            requested_quality = quality_map[q_str]
            global_session.config.quality = requested_quality
            try:
                track = global_session.track(track_id)
                manifest = track.get_stream().get_stream_manifest()
                urls = manifest.get_urls()
                if urls:
                    global_session.config.quality = old_quality
                    return RedirectResponse(urls[0])
            except Exception as e:
                # If 401 on first try, attempt token refresh once
                if "401" in str(e) and idx == 0 and getattr(global_session, "refresh_token", None):
                    try:
                        if global_session.token_refresh(global_session.refresh_token):
                            save_session(global_session)
                            # Retry the current quality
                            track = global_session.track(track_id)
                            manifest = track.get_stream().get_stream_manifest()
                            urls = manifest.get_urls()
                            if urls:
                                global_session.config.quality = old_quality
                                return RedirectResponse(urls[0])
                    except Exception as refresh_e:
                        print(f"Token refresh failed during stream fallback: {refresh_e}")
                
                print(f"Failed to stream track {track_id} in {q_str}: {str(e)}. Falling back...")
                continue
                
        global_session.config.quality = old_quality
        raise HTTPException(404, "No stream URL found from Tidal across any quality level")
        
    except Exception as e:
        raise HTTPException(404, f"Error getting stream from Tidal (likely unavailable): {str(e)}")

@router.get("/search")
def search_tidal(query: str, category: Optional[str] = None, offset: int = 0, limit: int = 20):
    """Search Tidal for tracks, albums, and playlists with optional category filter and pagination."""
    if not global_session.check_login():
        raise HTTPException(status_code=401, detail="Not authenticated with Tidal")
    
    import tidalapi
    try:
        types_map = {
            "tracks": "TRACKS",
            "track": "TRACKS",
            "albums": "ALBUMS",
            "album": "ALBUMS",
            "playlists": "PLAYLISTS",
            "playlist": "PLAYLISTS"
        }
        
        if category and category.lower() in types_map:
            types_param = types_map[category.lower()]
        else:
            types_param = "TRACKS,ALBUMS,PLAYLISTS"
            
        params = {
            "query": query,
            "limit": limit,
            "offset": offset,
            "types": types_param
        }
        
        json_obj = global_session.request.request("GET", "search", params=params).json()
        
        tracks = []
        total_tracks = 0
        if "tracks" in json_obj and json_obj["tracks"]:
            total_tracks = json_obj["tracks"].get("totalNumberOfItems", 0)
            raw_tracks = global_session.request.map_json(json_obj["tracks"], global_session.parse_track)
            for t in raw_tracks:
                tracks.append({
                    "tidal_id": str(t.id),
                    "item_type": "track",
                    "title": t.name,
                    "artist": t.artist.name if getattr(t, 'artist', None) else "Unknown",
                    "album": t.album.name if getattr(t, 'album', None) else "Unknown",
                    "duration": t.duration,
                    "quality": getattr(t.audio_quality, 'value', t.audio_quality) if hasattr(t, 'audio_quality') else "UNKNOWN",
                    "picture_url": t.album.image(320) if getattr(t, 'album', None) and hasattr(t.album, 'image') else None
                })
                
        albums = []
        total_albums = 0
        if "albums" in json_obj and json_obj["albums"]:
            total_albums = json_obj["albums"].get("totalNumberOfItems", 0)
            raw_albums = global_session.request.map_json(json_obj["albums"], global_session.parse_album)
            for a in raw_albums:
                albums.append({
                    "tidal_id": str(a.id),
                    "item_type": "album",
                    "name": a.name,
                    "artist_name": a.artist.name if getattr(a, 'artist', None) else "Unknown",
                    "picture_url": a.image(320) if hasattr(a, 'image') and callable(a.image) else None
                })
                
        playlists = []
        total_playlists = 0
        if "playlists" in json_obj and json_obj["playlists"]:
            total_playlists = json_obj["playlists"].get("totalNumberOfItems", 0)
            raw_playlists = global_session.request.map_json(json_obj["playlists"], global_session.parse_playlist)
            for p in raw_playlists:
                playlists.append({
                    "tidal_id": str(p.id),
                    "item_type": "playlist",
                    "name": p.name,
                    "artist_name": p.creator.name if getattr(p, 'creator', None) else "Unknown",
                    "picture_url": p.image(320) if hasattr(p, 'image') and callable(p.image) else None
                })
                
        return {
            "tracks": tracks,
            "albums": albums,
            "playlists": playlists,
            "totals": {
                "tracks": total_tracks,
                "albums": total_albums,
                "playlists": total_playlists
            },
            "category": category,
            "offset": offset,
            "limit": limit
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")

@router.get("/album/{album_id}")
def get_album_details(album_id: str, db: Session = Depends(get_db)):
    """Returns the tracklist for an album, indicating which tracks are available locally."""
    if not global_session.check_login():
        raise HTTPException(status_code=401, detail="Not authenticated with Tidal.")
        
    try:
        import urllib.parse
        a = global_session.album(album_id)
        
        tracks = a.tracks()
                
        album_name = a.name
        safe_album_name = sanitize_filename(album_name)
        
        album_dir = os.path.join(MUSIC_DIR, safe_album_name)
        config = db.query(models.PlaylistConfig).filter(models.PlaylistConfig.tidal_id == album_id).first()
        if config and config.name:
            config_safe_name = sanitize_filename(config.name)
            if not os.path.exists(album_dir) and os.path.exists(os.path.join(MUSIC_DIR, config_safe_name)):
                safe_album_name = config_safe_name
                album_dir = os.path.join(MUSIC_DIR, safe_album_name)
        
        # Collect all local files with their relative paths
        local_files_map = {}
        if os.path.exists(album_dir):
            for root, _, files in os.walk(album_dir):
                for file in files:
                    rel_path = os.path.relpath(os.path.join(root, file), album_dir)
                    local_files_map[file.lower()] = rel_path
                    
        result_tracks = []
        for t in tracks:
            safe_title = sanitize_filename(t.name)
            track_num = t.track_num or 1
            artist_name = sanitize_filename(t.artist.name if getattr(t, 'artist', None) else "Unknown Artist")
            t_album_name = sanitize_filename(t.album.name if getattr(t, 'album', None) else "Unknown Album")
            
            is_downloaded = False
            local_filename = None
            quality_label = resolve_track_quality(t)
            stream_url = f"/api/music/stream/{t.id}"
            
            # Check by expected path pattern first (like playlists do)
            expected_prefix = os.path.join(artist_name, t_album_name, f"{track_num:02d} - {safe_title}")
            for ext in [".flac", ".m4a", ".mp3", ".opus"]:
                full_path = os.path.join(album_dir, expected_prefix + ext)
                if os.path.exists(full_path):
                    is_downloaded = True
                    local_filename = expected_prefix + ext
                    quality_label = "LOSSLESS" if ext == ".flac" else "HIGH"
                    
                    # Try to read actual quality from metadata
                    try:
                        import mutagen
                        audio = mutagen.File(full_path)
                        if audio is not None:
                            comments = audio.get("COMMENT", audio.get("\xa9cmt", []))
                            for c in comments:
                                if isinstance(c, str) and c.startswith("QUALITY="):
                                    quality_label = c.replace("QUALITY=", "").strip()
                                    break
                    except Exception:
                        pass
                    break
            
            # Fallback: fuzzy title match in local files
            if not is_downloaded:
                for lf_lower, rel_path in local_files_map.items():
                    if safe_title.lower() in lf_lower:
                        full_path = os.path.join(album_dir, rel_path)
                        is_downloaded = True
                        local_filename = rel_path
                        quality_label = "LOSSLESS" if lf_lower.endswith(".flac") else "HIGH"
                        
                        try:
                            import mutagen
                            audio = mutagen.File(full_path)
                            if audio is not None:
                                comments = audio.get("COMMENT", audio.get("\xa9cmt", []))
                                for c in comments:
                                    if isinstance(c, str) and c.startswith("QUALITY="):
                                        quality_label = c.replace("QUALITY=", "").strip()
                                        break
                        except Exception:
                            pass
                        break
            
            if is_downloaded and local_filename:
                encoded_safe_name = urllib.parse.quote(safe_album_name)
                encoded_local_filename = "/".join([urllib.parse.quote(p) for p in local_filename.replace("\\", "/").split("/")])
                stream_url = f"/music_files/{encoded_safe_name}/{encoded_local_filename}"
                    
            result_tracks.append({
                "id": t.id,
                "title": t.name,
                "artist": t.artist.name if getattr(t, 'artist', None) else "Unknown Artist",
                "album": t.album.name if getattr(t, 'album', None) else "Unknown Album",
                "duration": t.duration,
                "track_num": track_num,
                "playlist_pos": t.track_num or 1,
                "picture_url": t.album.image(320) if getattr(t, 'album', None) and hasattr(t.album, 'image') and callable(t.album.image) else None,
                "is_downloaded": is_downloaded,
                "stream_url": stream_url,
                "quality": quality_label
            })
            
        return {
            "tidal_id": album_id,
            "name": album_name,
            "artist_name": a.artist.name if getattr(a, 'artist', None) else "Unknown",
            "picture_url": a.image(320) if hasattr(a, 'image') and callable(a.image) else None,
            "tracks": result_tracks,
            "item_type": "album"
        }
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Album not found: {str(e)}")
