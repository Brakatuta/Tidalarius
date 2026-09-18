import threading
import queue
import time
import os
import asyncio
import requests as http_requests
import json
import datetime
import re
import base64
from pathlib import Path
from tidal_auth import global_session
from database import SessionLocal
import models
from ws_manager import manager

MUSIC_DIR = os.environ.get("MUSIC_DIR", "/music")
TIDARR_URL = os.environ.get("TIDARR_URL")
TIDARR_API_KEY = os.environ.get("TIDARR_API_KEY", "")

sync_queue = queue.Queue()
# track job state: { playlist_id: "queued" | "running" | "paused" | "cancelled" }
active_jobs = {}
active_logs = {}
active_progress = {}

def get_log_timestamp():
    now = datetime.datetime.now()
    return f"{now.strftime('%Y:%m:%d:%H:%M:%S')}:{now.microsecond // 1000:03d}"

def emit_sync_event(event_type, playlist_id, **kwargs):
    event = {"type": event_type, "playlist_id": playlist_id}
    event.update(kwargs)
    
    if event_type == "sync_log":
        msg = kwargs.get("message", "")
        ts = get_log_timestamp()
        formatted_msg = f"[{ts}] {msg}"
        kwargs["message"] = formatted_msg
        event["message"] = formatted_msg
        if playlist_id not in active_logs:
            active_logs[playlist_id] = []
        active_logs[playlist_id].append(formatted_msg)
        print(formatted_msg, flush=True)
    elif event_type == "sync_progress":
        active_progress[playlist_id] = kwargs.get("progress", 0)
        
    manager.broadcast_sync(event)

def sanitize_filename(name):
    return re.sub(r'[\\/*?:"<>|]', "", name)

def prune_sync_reports(directory: str, max_keep: int = 3):
    """Keeps only the latest max_keep sync report log files in the directory."""
    try:
        if not os.path.exists(directory):
            return
        log_files = [f for f in os.listdir(directory) if f.startswith('sync_report_') and f.endswith('.log')]
        if len(log_files) > max_keep:
            sorted_logs = sorted(log_files, reverse=True)
            for old_log in sorted_logs[max_keep:]:
                try:
                    os.remove(os.path.join(directory, old_log))
                except Exception as ex:
                    print(f"Failed to remove old sync report {old_log}: {ex}")
    except Exception as e:
        print(f"Error pruning sync reports in {directory}: {e}")

def prune_all_sync_reports(music_dir: str = MUSIC_DIR, max_keep: int = 3):
    """Prunes sync reports across all playlist directories."""
    try:
        if not os.path.exists(music_dir):
            return
        for entry in os.scandir(music_dir):
            if entry.is_dir():
                prune_sync_reports(entry.path, max_keep=max_keep)
    except Exception as e:
        print(f"Error pruning all sync reports: {e}")

def download_cover(track):
    """Download album cover art, returns bytes or None."""
    try:
        album = track.album
        if album:
            cover_url = album.image(1280)
            if cover_url:
                resp = http_requests.get(cover_url, timeout=15)
                if resp.status_code == 200:
                    return resp.content
    except Exception as e:
        print(f"Cover download failed for '{track.name}': {e}")
    return None

def write_metadata(file_path, track, cover_data=None, quality=None):
    """Write ID3/Vorbis metadata to the downloaded file using mutagen."""
    try:
        ext = file_path.suffix.lower()
        
        artist_name = track.artist.name if track.artist else "Unknown Artist"
        album_name = track.album.name if track.album else "Unknown Album"
        track_num = track.track_num or 1
        disc_num = getattr(track, 'volume_num', 1) or 1
        
        if ext == ".flac":
            from mutagen.flac import FLAC, Picture
            audio = FLAC(str(file_path))
            
            audio["TITLE"] = track.name
            audio["ARTIST"] = artist_name
            audio["ALBUM"] = album_name
            audio["ALBUMARTIST"] = artist_name
            audio["TRACKNUMBER"] = str(track_num)
            audio["DISCNUMBER"] = str(disc_num)
            
            if hasattr(track, 'isrc') and track.isrc:
                audio["ISRC"] = track.isrc
                
            if quality:
                audio["COMMENT"] = f"QUALITY={quality}"
                
            if cover_data:
                pic = Picture()
                pic.data = cover_data
                pic.mime = "image/jpeg"
                pic.type = 3  # front cover
                pic.width = 1280
                pic.height = 1280
                audio.add_picture(pic)
            
            audio.save()
            
        elif ext == ".m4a":
            from mutagen.mp4 import MP4, MP4Cover
            from mutagen.easymp4 import EasyMP4
            
            # First: cover art (needs raw MP4)
            if cover_data:
                mp4 = MP4(str(file_path))
                mp4["covr"] = [MP4Cover(cover_data, imageformat=MP4Cover.FORMAT_JPEG)]
                if quality:
                    mp4["\xa9cmt"] = f"QUALITY={quality}"
                mp4.save()
            elif quality:
                mp4 = MP4(str(file_path))
                mp4["\xa9cmt"] = f"QUALITY={quality}"
                mp4.save()
            
            # Then: text tags via EasyMP4
            audio = EasyMP4(str(file_path))
            audio["title"] = track.name
            audio["artist"] = artist_name
            audio["album"] = album_name
            audio["albumartist"] = artist_name
            audio["tracknumber"] = str(track_num)
            audio["discnumber"] = str(disc_num)
            audio.save()
            
    except Exception as e:
        print(f"Metadata write failed for '{track.name}': {e}")

def download_track_via_tidalapi(track, quality_str, base_path):
    """
    Download a track using tidalapi's own authenticated session.
    This avoids the OAuth client mismatch with tiddl.
    
    quality_str: one of HI_RES_LOSSLESS, LOSSLESS, HIGH, LOW
    """
    try:
        # Build the file path prefix to check if it already exists BEFORE hitting the API
        artist_name = sanitize_filename(track.artist.name if track.artist else "Unknown Artist")
        album_name = sanitize_filename(track.album.name if track.album else "Unknown Album")
        track_title = sanitize_filename(track.name)
        track_num = track.track_num or 1
        
        track_dir = Path(base_path) / artist_name / album_name
        track_dir.mkdir(parents=True, exist_ok=True)
        file_prefix = f"{track_num:02d} - {track_title}"
        
        for ext in [".flac", ".m4a"]:
            check_path = track_dir / f"{file_prefix}{ext}"
            if check_path.exists() and check_path.stat().st_size > 100_000:
                return True, f"Already exists ({check_path.stat().st_size} bytes)", str(check_path)

        # Map our quality strings to tidalapi Quality enum
        import tidalapi
        quality_map = {
            "HI_RES_LOSSLESS": tidalapi.Quality.hi_res_lossless,
            "LOSSLESS": tidalapi.Quality.high_lossless,
            "HIGH": tidalapi.Quality.low_320k,
            "LOW": tidalapi.Quality.low_96k,
        }
        quality = quality_map.get(quality_str)
        if not quality:
            quality = tidalapi.Quality.high_lossless
        
        # Add a small delay to avoid rate limiting
        import time
        time.sleep(0.5)
        
        # Temporarily set quality on the session so get_stream() uses it
        old_quality = global_session.config.quality
        global_session.config.quality = quality
        
        try:
            # Get the stream URL from Tidal
            try:
                stream = track.get_stream()
            except Exception as e:
                # Catch 401 Unauthorized, refresh token, and retry once
                if "401" in str(e) and getattr(global_session, "refresh_token", None):
                    print("[WORKER] Token expired (401). Refreshing token and retrying...", flush=True)
                    from backend import tidal_auth
                    if global_session.token_refresh(global_session.refresh_token):
                        tidal_auth.save_session(global_session)
                        stream = track.get_stream()
                    else:
                        raise e
                else:
                    raise e
                    
            manifest = stream.get_stream_manifest()
        finally:
            # Restore original quality setting
            global_session.config.quality = old_quality
        
        # Get download URLs from the manifest
        urls = manifest.get_urls()
        if not urls:
            return False, "No stream URLs returned by Tidal", ""
        
        # Use file_extension from manifest directly (e.g. ".flac", ".m4a")
        ext = manifest.file_extension
        if not ext.startswith("."):
            ext = "." + ext
            
        actual_q_str = str(stream.audio_quality).upper()
        if "HI_RES" in actual_q_str:
            actual_quality_label = "HI_RES_LOSSLESS"
        elif "LOSSLESS" in actual_q_str:
            actual_quality_label = "LOSSLESS"
        elif "HIGH" in actual_q_str:
            actual_quality_label = "HIGH"
        elif "LOW" in actual_q_str:
            actual_quality_label = "LOW"
        else:
            actual_quality_label = quality_str
            
        codecs = manifest.get_codecs()
        
        # Build the file path: base_path/Artist/Album/TrackNum - Title.ext
        artist_name = sanitize_filename(track.artist.name if track.artist else "Unknown Artist")
        album_name = sanitize_filename(track.album.name if track.album else "Unknown Album")
        track_title = sanitize_filename(track.name)
        track_num = track.track_num or 1
        
        track_dir = Path(base_path) / artist_name / album_name
        track_dir.mkdir(parents=True, exist_ok=True)
        
        file_name = f"{track_num:02d} - {track_title}{ext}"
        file_path = track_dir / file_name
        
        # Skip if file already exists and is reasonably sized
        if file_path.exists() and file_path.stat().st_size > 100_000:
            return True, f"Already exists ({file_path.stat().st_size} bytes)", str(file_path)
        
        # Download all segments
        audio_data = b""
        for url in urls:
            resp = http_requests.get(url, timeout=60)
            resp.raise_for_status()
            audio_data += resp.content
        
        if len(audio_data) < 1000:
            return False, f"Downloaded data too small ({len(audio_data)} bytes)", ""
        
        # Write audio file
        file_path.write_bytes(audio_data)
        
        # Download cover art and write metadata
        cover_data = download_cover(track)
        write_metadata(file_path, track, cover_data, quality=actual_quality_label)
        
        # Also save cover as folder.jpg if it doesn't exist
        cover_path = track_dir / "folder.jpg"
        if cover_data and not cover_path.exists():
            cover_path.write_bytes(cover_data)
        
        size_mb = len(audio_data) / (1024 * 1024)
        return True, f"Downloaded {size_mb:.1f}MB ({codecs})", str(file_path)
        
    except Exception as e:
        return False, str(e), ""


def download_track_via_ytdlp(track, base_path):
    """Fallback mechanism using yt-dlp to download from YouTube"""
    try:
        import yt_dlp
        artist_name = sanitize_filename(track.artist.name if track.artist else "Unknown Artist")
        album_name = sanitize_filename(track.album.name if track.album else "Unknown Album")
        track_title = sanitize_filename(track.name)
        track_num = track.track_num or 1
        
        track_dir = Path(base_path) / artist_name / album_name
        track_dir.mkdir(parents=True, exist_ok=True)
        
        search_query = f"ytsearch1:{track.artist.name if track.artist else ''} {track.name} audio"
        
        file_name = f"{track_num:02d} - {track_title}"
        final_file_path = track_dir / f"{file_name}.m4a"
        
        if final_file_path.exists() and final_file_path.stat().st_size > 100_000:
            return True, f"Already exists ({final_file_path.stat().st_size} bytes)", str(final_file_path)
            
        file_path_template = track_dir / f"{file_name}.%(ext)s"
        
        ydl_opts = {
            'format': 'bestaudio/best',
            'extractor_args': {'youtube': ['client=ANDROID']},
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'm4a',
                'preferredquality': '192',
            }],
            'outtmpl': str(file_path_template),
            'quiet': True,
            'no_warnings': True,
            'extract_audio': True
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            print(f"Fallback downloading '{track.name}' via YouTube...", flush=True)
            ydl.download([search_query])
            
        final_file_path = track_dir / f"{file_name}.m4a"
        if not final_file_path.exists():
            return False, "yt-dlp failed to produce output file", ""
            
        cover_data = download_cover(track)
        write_metadata(final_file_path, track, cover_data, quality="YOUTUBE")
        
        file_size_mb = final_file_path.stat().st_size / (1024 * 1024)
        return True, f"Downloaded {file_size_mb:.1f}MB (M4A) via YouTube", str(final_file_path)
    except Exception as e:
        return False, f"Fallback yt-dlp failed: {str(e)}", ""

def download_track(track, quality, base_path):
    """Main download dispatcher."""
    if TIDARR_URL:
        try:
            headers = {"X-Api-Key": TIDARR_API_KEY, "Content-Type": "application/json"}
            payload = {
                "item": {
                    "id": str(track.id),
                    "url": f"https://listen.tidal.com/track/{track.id}",
                    "type": "track",
                    "status": "queue_download"
                }
            }
            res = http_requests.post(f"{TIDARR_URL}/api/save", headers=headers, json=payload, timeout=10)
            if res.status_code in [200, 201, 202]:
                return True, "Queued in Tidarr", ""
            else:
                return False, f"Tidarr API error: {res.status_code} {res.text}", ""
        except Exception as e:
            return False, f"Tidarr connection failed: {str(e)}", ""
    
    # Use tidalapi directly for downloading
    return download_track_via_tidalapi(track, quality, base_path)


def process_playlist_sync(playlist_id, qualities, track_id=None):
    print(f"[WORKER] Starting job for playlist {playlist_id}", flush=True)
    db = SessionLocal()
    try:
        print("[WORKER] Fetching db_config", flush=True)
        db_config = db.query(models.PlaylistConfig).filter(models.PlaylistConfig.tidal_id == playlist_id).first()
        if not db_config: 
            print("[WORKER] Config not found in DB", flush=True)
            return
        
        db_config.sync_status = "syncing"
        db.commit()
        active_jobs[playlist_id] = "running"
        print("[WORKER] DB status updated to syncing", flush=True)
        
        emit_sync_event("sync_started", playlist_id)
        
        print("[WORKER] Fetching item from global_session", flush=True)
        item_type = getattr(db_config, 'item_type', 'playlist')
        
        tracks = []
        seen_ids = set()
        
        if item_type == "album":
            album = global_session.album(playlist_id)
            playlist = album
            print(f"[WORKER] Fetched album: {album.name}", flush=True)
            for t in album.tracks():
                if t.id not in seen_ids:
                    tracks.append(t)
                    seen_ids.add(t.id)
            item_name = album.name
        elif item_type == "track":
            track = global_session.track(playlist_id)
            playlist = track
            print(f"[WORKER] Fetched track: {track.name}", flush=True)
            tracks.append(track)
            item_name = track.name
        else:
            playlist = global_session.playlist(playlist_id)
            print(f"[WORKER] Fetched playlist: {playlist.name}", flush=True)
            offset = 0
            limit = 1000
            while True:
                batch = playlist.tracks(limit=limit, offset=offset)
                if not batch: break
                for t in batch:
                    if t.id not in seen_ids:
                        tracks.append(t)
                        seen_ids.add(t.id)
                offset += len(batch)
                if len(batch) < limit: break
            item_name = playlist.name
            
        print(f"[WORKER] Found {len(tracks)} tracks total", flush=True)
        # Filter for single track sync if specified
        if track_id is not None:
            tracks = [t for t in tracks if t.id == track_id]
            
        total_tracks = len(tracks)
        print(f"[WORKER] Found {total_tracks} tracks", flush=True)
        
        emit_sync_event("sync_log", playlist_id, message=f"Starting sync for playlist '{playlist.name}' ({total_tracks} tracks)...")
        
        playlist_dir = os.path.join(MUSIC_DIR, sanitize_filename(playlist.name))
        os.makedirs(playlist_dir, exist_ok=True)
        
        report = {"success": [], "fallback": [], "failed": []}
        m3u8_entries = []
        
        for idx, track in enumerate(tracks):

            print(f"[WORKER] Loop index {idx}, track {track.name}", flush=True)
            # Handle Pause/Cancel
            while active_jobs.get(playlist_id) == "paused":
                time.sleep(1)
            if active_jobs.get(playlist_id) == "cancelled":
                emit_sync_event("sync_log", playlist_id, message="Job cancelled by user.")
                break
            
            success = False
            used_quality = None
            error_msg = ""
            
            # Sort qualities by highest priority first
            priority_order = {"HI_RES_LOSSLESS": 4, "LOSSLESS": 3, "HIGH": 2, "LOW": 1}
            sorted_qualities = sorted(qualities, key=lambda q: priority_order.get(q, 0), reverse=True)
            
            for quality in sorted_qualities:
                emit_sync_event("sync_progress", playlist_id, progress=int((idx / total_tracks) * 100), current_track=track.name, attempting_quality=quality)
                
                emit_sync_event("sync_log", playlist_id, message=f"[{idx+1}/{total_tracks}] Attempting '{track.name}' in {quality}...")
                
                ok, msg, out = download_track(track, quality, playlist_dir)
                if ok:
                    success = True
                    used_quality = quality
                    emit_sync_event("sync_log", playlist_id, message=f"SUCCESS: Downloaded '{track.name}' ({quality}) - {msg}")
                    break
                else:
                    error_msg = msg
                    emit_sync_event("sync_log", playlist_id, message=f"FAILED: '{track.name}' in {quality} - Reason: {msg}")
            
            # Fallback if ALL requested qualities on Tidal failed
            if not success and "Already exists" not in error_msg:
                emit_sync_event("sync_log", playlist_id, message=f"[{idx+1}/{total_tracks}] All Tidal qualities failed for '{track.name}'. Trying fallback via yt-dlp...")
                fallback_success, fallback_msg, fallback_path = download_track_via_ytdlp(track, playlist_dir)
                if fallback_success:
                    success = True
                    used_quality = "YOUTUBE"
                    emit_sync_event("sync_log", playlist_id, message=f"SUCCESS: Downloaded '{track.name}' (YOUTUBE) - {fallback_msg}")
                else:
                    error_msg = fallback_msg
                    emit_sync_event("sync_log", playlist_id, message=f"FAILED: yt-dlp fallback for '{track.name}' - Reason: {fallback_msg}")
            
            if success:
                # Add to M3U8
                artist_name = sanitize_filename(track.artist.name if track.artist else "Unknown Artist")
                album_name = sanitize_filename(track.album.name if track.album else "Unknown Album")
                track_title = sanitize_filename(track.name)
                track_num = track.track_num or 1
                ext = "flac" if "LOSSLESS" in used_quality else "m4a"
                rel_path = f"{artist_name}/{album_name}/{track_num:02d} - {track_title}.{ext}"
                m3u8_entries.append(f"#EXTINF:{track.duration},{track.artist.name} - {track.name}\n{rel_path}")
                
                if used_quality == sorted_qualities[0]:
                    report["success"].append(track.name)
                else:
                    report["fallback"].append({"track": track.name, "wanted": sorted_qualities[0], "got": used_quality})
                    
                emit_sync_event("track_downloaded", playlist_id, track_id=track.id, track_name=track.name, quality=used_quality)
            else:
                report["failed"].append({"track": track.name, "reason": error_msg})
                
        # Generate M3U8 file
        os.makedirs(playlist_dir, exist_ok=True)
        m3u8_path = os.path.join(playlist_dir, f"{sanitize_filename(playlist.name)}.m3u8")
        with open(m3u8_path, "w", encoding="utf-8") as f:
            f.write("#EXTM3U\n")
            f.write("\n".join(m3u8_entries))
                
        # Generate Report
        db_config.sync_status = "idle"
        db_config.last_synced = datetime.datetime.utcnow()
        db.commit()
        
        report_path = os.path.join(playlist_dir, f"sync_report_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(f"Sync Report for {playlist.name} [{get_log_timestamp()}]\n")
            f.write("="*30 + "\n\n")
            f.write(f"Success ({len(report['success'])}):\n")
            for t in report["success"]: f.write(f" - {t}\n")
            f.write(f"\nFallback ({len(report['fallback'])}):\n")
            for t in report["fallback"]: f.write(f" - {t['track']} (Got {t['got']} instead of {t['wanted']})\n")
            f.write(f"\nFailed ({len(report['failed'])}):\n")
            for t in report["failed"]: f.write(f" - {t['track']} (Reason: {t['reason']})\n")
            
        prune_sync_reports(playlist_dir, max_keep=3)
        emit_sync_event("sync_finished", playlist_id, report_url=f"/api/sync/report?path={report_path}")
        manager.broadcast_sync({"type": "library_updated", "playlist_id": playlist_id, "action": "sync_finished"})
    except Exception as e:
        print(f"[{get_log_timestamp()}] Sync failed for {playlist_id}: {e}", flush=True)
        import traceback
        traceback.print_exc()
        db_config.sync_status = "error"
        db.commit()
        emit_sync_event("sync_error", playlist_id, error=str(e))
    finally:
        active_jobs.pop(playlist_id, None)
        db.close()

def sync_worker():
    print(f"[{get_log_timestamp()}] [WORKER] Thread started, waiting for jobs", flush=True)
    prune_all_sync_reports(MUSIC_DIR, max_keep=3)
    while True:
        job = sync_queue.get()
        if job is None: break
        print(f"[{get_log_timestamp()}] [WORKER] Picked up job from queue: {job}", flush=True)
        try:
            process_playlist_sync(job["playlist_id"], job["qualities"], job.get("track_id"))
        except Exception as e:
            print(f"[{get_log_timestamp()}] [WORKER] Exception in process_playlist_sync: {e}", flush=True)
        finally:
            print(f"[{get_log_timestamp()}] [WORKER] Job finished, calling task_done", flush=True)
            sync_queue.task_done()

def scheduler_worker():
    import croniter
    print(f"[{get_log_timestamp()}] [SCHEDULER] Thread started", flush=True)
    last_checked_minute = None
    while True:
        try:
            time.sleep(5)
            now = datetime.datetime.now()
            current_minute = (now.year, now.month, now.day, now.hour, now.minute)
            if current_minute == last_checked_minute:
                continue
            last_checked_minute = current_minute
            
            check_time = now.replace(second=0, microsecond=0)
            db = SessionLocal()
            try:
                configs = db.query(models.PlaylistConfig).filter(models.PlaylistConfig.sync_enabled == True).all()
                for config in configs:
                    if config.schedule and config.schedule != "custom":
                        try:
                            if croniter.croniter.match(config.schedule, check_time):
                                if active_jobs.get(config.tidal_id) not in ["running", "paused"]:
                                    print(f"[{get_log_timestamp()}] [SCHEDULER] Triggering scheduled sync for {config.name}", flush=True)
                                    sync_queue.put({
                                        "playlist_id": config.tidal_id,
                                        "qualities": config.qualities if config.qualities else ["HIGH"]
                                    })
                        except Exception as e:
                            print(f"[{get_log_timestamp()}] [SCHEDULER] Invalid cron expression '{config.schedule}' for {config.tidal_id}: {e}", flush=True)
            finally:
                db.close()
        except Exception as e:
            print(f"[{get_log_timestamp()}] [SCHEDULER] Error: {e}", flush=True)

worker_thread = threading.Thread(target=sync_worker, daemon=True)
worker_thread.start()

scheduler_thread = threading.Thread(target=scheduler_worker, daemon=True)
scheduler_thread.start()
