from fastapi import APIRouter, HTTPException, BackgroundTasks
import tidalapi
import os
import json

router = APIRouter()

# Patch tidalapi.album.Album.__init__ to gracefully handle CloudFront 429 rate-limiting
# on api.tidal.com/v1/albums/{id} by falling back to api.tidal.com/v1/albums/{id}/tracks
_original_album_init = tidalapi.album.Album.__init__

def _resilient_album_init(self, session, album_id):
    self.session = session
    self.request = session.request
    self.artist = session.artist()
    self.id = str(album_id) if album_id is not None else None

    if self.id:
        try:
            request = self.request.request("GET", "albums/%s" % self.id)
            self.request.map_json(request.json(), parse=self.parse)
        except Exception as e:
            try:
                req_tracks = self.request.request("GET", f"albums/{self.id}/tracks")
                tracks_data = req_tracks.json()
                items = tracks_data.get("items", [])
                if items:
                    alb_json = items[0].get("album", {})
                    art_json = items[0].get("artist", {})
                    arts_json = items[0].get("artists", [art_json] if art_json else [])
                    fallback_json = {
                        "id": self.id,
                        "title": alb_json.get("title", "Unknown Album"),
                        "cover": alb_json.get("cover"),
                        "videoCover": alb_json.get("videoCover"),
                        "artist": art_json,
                        "artists": arts_json,
                        "numberOfTracks": tracks_data.get("totalNumberOfItems", len(items))
                    }
                    self.parse(fallback_json)
                else:
                    raise e
            except Exception:
                raise e

tidalapi.album.Album.__init__ = _resilient_album_init

CONFIG_DIR = os.environ.get("CONFIG_DIR", "./config")
SESSION_FILE = os.path.join(CONFIG_DIR, "tidal_session.json")

# In-memory dictionary to hold the login state
login_state = {
    "is_logging_in": False,
    "url": None,
    "code": None,
    "error": None
}

global_session = tidalapi.Session()
# Override with Tiddl's client credentials which have streaming access
global_session.config.client_id = "4N3n6Q1x95LL5K7p"
global_session.config.client_secret = "oKOXfJW371cX6xaZ0PyhgGNBdNLlBZd4AKKYougMjik="

def load_session():
    if os.path.exists(SESSION_FILE):
        try:
            with open(SESSION_FILE, "r") as f:
                data = json.load(f)
            global_session.load_oauth_session(
                token_type=data.get("token_type", "Bearer"), 
                access_token=data["access_token"], 
                refresh_token=data.get("refresh_token")
            )
        except Exception as e:
            print(f"Error loading session: {e}")

load_session()

def save_session(session):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    if session.check_login():
        data = {
            "session_id": session.session_id,
            "token_type": session.token_type,
            "access_token": session.access_token,
            "refresh_token": session.refresh_token
        }
        with open(SESSION_FILE, "w") as f:
            json.dump(data, f)
        return True
    return False

def ensure_valid_session():
    """Checks if the session is valid, and refreshes the token if expired."""
    try:
        if global_session.check_login():
            return True
        if getattr(global_session, "refresh_token", None):
            print("[TIDAL_AUTH] Access token expired. Refreshing token...", flush=True)
            if global_session.token_refresh(global_session.refresh_token):
                save_session(global_session)
                print("[TIDAL_AUTH] Token refreshed successfully.", flush=True)
                return True
    except Exception as e:
        print(f"[TIDAL_AUTH] Token refresh failed: {e}", flush=True)
    return False

def wait_for_login(future):
    try:
        future.result() # This blocks until the user logs in or it times out
        save_session(global_session)
    except Exception as e:
        print(f"Login failed: {e}")
        login_state["error"] = str(e)
    finally:
        login_state["is_logging_in"] = False
        login_state["url"] = None
        login_state["code"] = None

@router.get("/device_login")
def get_device_login(background_tasks: BackgroundTasks):
    if global_session.check_login():
        return {"status": "already_logged_in"}
    
    if login_state["is_logging_in"]:
        return {
            "status": "waiting_for_user",
            "url": login_state["url"],
            "code": login_state["code"]
        }

    # Start new OAuth device flow
    try:
        login, future = global_session.login_oauth()
        
        url = login.verification_uri_complete
        if not url.startswith("http"):
            url = f"https://{url}"
            
        code = getattr(login, "user_code", url.split("/")[-1])
        
        login_state["is_logging_in"] = True
        login_state["url"] = url
        login_state["code"] = code
        login_state["error"] = None
        
        # Run the blocking future.result() in a background thread
        background_tasks.add_task(wait_for_login, future)
        
        return {
            "status": "waiting_for_user",
            "url": url,
            "code": code,
            "expires_in": login.expires_in
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/status")
def check_status():
    return {
        "logged_in": ensure_valid_session(),
        "is_logging_in": login_state["is_logging_in"],
        "error": login_state["error"]
    }

@router.post("/logout")
def logout():
    global global_session
    global_session = tidalapi.Session()
    global_session.config.client_id = "4N3n6Q1x95LL5K7p"
    global_session.config.client_secret = "oKOXfJW371cX6xaZ0PyhgGNBdNLlBZd4AKKYougMjik="
    if os.path.exists(SESSION_FILE):
        os.remove(SESSION_FILE)
    return {"status": "logged_out"}
