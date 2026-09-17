from sqlalchemy import Column, String, Boolean, JSON, DateTime, Integer
from database import Base
import datetime

class PlaylistConfig(Base):
    __tablename__ = "playlist_configs"

    tidal_id = Column(String, primary_key=True, index=True)
    item_type = Column(String, default="playlist") # playlist, album, track
    name = Column(String, index=True)
    artist_name = Column(String, nullable=True)
    picture_url = Column(String, nullable=True)
    sync_enabled = Column(Boolean, default=False)
    # Qualities stored as a JSON array of strings e.g. ["LOW", "HIGH", "LOSSLESS", "HI_RES", "HI_RES_LOSSLESS"]
    qualities = Column(JSON, default=list)
    schedule = Column(String, nullable=True) # e.g. cron string "0 0 * * *"
    last_synced = Column(DateTime, nullable=True)
    sync_status = Column(String, nullable=True) # e.g. "idle", "syncing", "error"

    def to_dict(self):
        return {
            "tidal_id": self.tidal_id,
            "item_type": self.item_type or "playlist",
            "name": self.name,
            "artist_name": self.artist_name,
            "picture_url": self.picture_url,
            "sync_enabled": self.sync_enabled,
            "qualities": self.qualities or [],
            "schedule": self.schedule,
            "last_synced": self.last_synced.isoformat() if self.last_synced else None,
            "sync_status": self.sync_status
        }

