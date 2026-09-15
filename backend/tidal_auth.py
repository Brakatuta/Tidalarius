from fastapi import APIRouter, HTTPException, BackgroundTasks
import tidalapi
import os
import json

router = APIRouter()

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
        "logged_in": global_session.check_login(),
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
