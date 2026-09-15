from fastapi import WebSocket
from typing import List
import json
import asyncio

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.loop = None

    async def connect(self, websocket: WebSocket):
        if self.loop is None:
            self.loop = asyncio.get_running_loop()
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        text = json.dumps(message)
        for connection in list(self.active_connections):
            try:
                await connection.send_text(text)
            except Exception:
                self.disconnect(connection)

    def broadcast_sync(self, message: dict):
        # Fire and forget from a synchronous thread
        if self.active_connections and self.loop:
            asyncio.run_coroutine_threadsafe(self.broadcast(message), self.loop)

manager = ConnectionManager()

