from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.agents.agent1.models import DemographicProfileRequest, DemographicProfileResponse
from app.agents.agent1.service import DemographicProfiler
from app.agents.agent2.service import BuyingBehaviorSuggester
from app.agents.agent3.service import ReligiousHolidayCalendarBuilder
from app.agents.agent4.models import Agent4Request
from app.agents.agent4.service import VendorInventoryRecommender

router = APIRouter(prefix="/ws", tags=["WebSocket"])

_agent1 = DemographicProfiler()
_agent2 = BuyingBehaviorSuggester()
_agent3 = ReligiousHolidayCalendarBuilder()
_agent4 = VendorInventoryRecommender()


async def _send_progress(ws: WebSocket, message: str) -> None:
    await ws.send_json({"type": "progress", "message": message})


@router.websocket("/agents/1")
async def ws_agent1(ws: WebSocket) -> None:
    await ws.accept()
    try:
        data = await ws.receive_json()
        request = DemographicProfileRequest(**data)

        async def progress(msg: str) -> None:
            await _send_progress(ws, msg)

        result = await _agent1.build_profile(request, progress=progress)
        await ws.send_json({"type": "result", "data": result.model_dump(mode="json")})
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        try:
            await ws.send_json({"type": "error", "message": str(exc)})
        except Exception:
            pass


@router.websocket("/agents/2")
async def ws_agent2(ws: WebSocket) -> None:
    await ws.accept()
    try:
        data = await ws.receive_json()
        profile = DemographicProfileResponse(**data.get("profile", data))

        async def progress(msg: str) -> None:
            await _send_progress(ws, msg)

        result = await _agent2.suggest(profile, progress=progress)
        await ws.send_json({"type": "result", "data": result.model_dump(mode="json")})
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        try:
            await ws.send_json({"type": "error", "message": str(exc)})
        except Exception:
            pass


@router.websocket("/agents/3")
async def ws_agent3(ws: WebSocket) -> None:
    await ws.accept()
    try:
        data = await ws.receive_json()
        profile = DemographicProfileResponse(**data.get("profile", data))
        horizon_days = int(data.get("horizon_days", 90))

        async def progress(msg: str) -> None:
            await _send_progress(ws, msg)

        result = await _agent3.build_calendar(profile, horizon_days=horizon_days, progress=progress)
        await ws.send_json({"type": "result", "data": result.model_dump(mode="json")})
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        try:
            await ws.send_json({"type": "error", "message": str(exc)})
        except Exception:
            pass


@router.websocket("/agents/4")
async def ws_agent4(ws: WebSocket) -> None:
    await ws.accept()
    try:
        data = await ws.receive_json()
        request = Agent4Request(**data)

        async def progress(msg: str) -> None:
            await _send_progress(ws, msg)

        result = await _agent4.generate_recommendations_async(request, progress=progress)
        await ws.send_json({"type": "result", "data": result.model_dump(mode="json")})
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        try:
            await ws.send_json({"type": "error", "message": str(exc)})
        except Exception:
            pass
