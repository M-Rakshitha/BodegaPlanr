from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from fastapi import WebSocket


class OrchestrationProgressHub:
    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def connect(self, run_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections[run_id].add(websocket)

    async def disconnect(self, run_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            sockets = self._connections.get(run_id)
            if not sockets:
                return
            sockets.discard(websocket)
            if not sockets:
                self._connections.pop(run_id, None)

    async def publish(self, run_id: str, payload: dict[str, Any]) -> None:
        if not run_id:
            return

        message = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **payload,
        }

        async with self._lock:
            sockets = list(self._connections.get(run_id, set()))

        stale: list[WebSocket] = []
        for websocket in sockets:
            try:
                await websocket.send_json(message)
            except Exception:
                stale.append(websocket)

        if stale:
            async with self._lock:
                live = self._connections.get(run_id)
                if not live:
                    return
                for websocket in stale:
                    live.discard(websocket)
                if not live:
                    self._connections.pop(run_id, None)


progress_hub = OrchestrationProgressHub()
