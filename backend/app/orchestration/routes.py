from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from app.orchestration.graph import run_orchestration
from app.orchestration.models import OrchestrationRequest, OrchestratedReportResponse
from app.orchestration.progress import progress_hub

router = APIRouter(prefix="/orchestration", tags=["orchestration"])


@router.post("/run", response_model=OrchestratedReportResponse)
async def run_report_orchestration(request: OrchestrationRequest) -> OrchestratedReportResponse:
    run_id = request.run_id or str(uuid4())
    request = request.model_copy(update={"run_id": run_id})

    await progress_hub.publish(
        run_id,
        {
            "event": "orchestration_queued",
            "run_id": run_id,
            "stage": "orchestration",
            "status": "queued",
            "message": "Orchestration request accepted.",
        },
    )

    try:
        result = await run_orchestration(request)
        await progress_hub.publish(
            run_id,
            {
                "event": "orchestration_response_ready",
                "run_id": run_id,
                "stage": "orchestration",
                "status": "completed",
                "message": "HTTP response payload is ready.",
            },
        )
        return result
    except ValueError as error:
        await progress_hub.publish(
            run_id,
            {
                "event": "orchestration_failed",
                "run_id": run_id,
                "stage": "orchestration",
                "status": "failed",
                "message": str(error),
            },
        )
        raise HTTPException(status_code=400, detail=str(error)) from error
    except RuntimeError as error:
        await progress_hub.publish(
            run_id,
            {
                "event": "orchestration_failed",
                "run_id": run_id,
                "stage": "orchestration",
                "status": "failed",
                "message": str(error),
            },
        )
        raise HTTPException(status_code=500, detail=str(error)) from error
    except Exception as error:
        await progress_hub.publish(
            run_id,
            {
                "event": "orchestration_failed",
                "run_id": run_id,
                "stage": "orchestration",
                "status": "failed",
                "message": str(error),
            },
        )
        raise HTTPException(status_code=500, detail="Unexpected orchestration failure.") from error


@router.websocket("/ws/{run_id}")
async def orchestration_progress_ws(websocket: WebSocket, run_id: str) -> None:
    await progress_hub.connect(run_id, websocket)
    await progress_hub.publish(
        run_id,
        {
            "event": "ws_connected",
            "run_id": run_id,
            "stage": "orchestration",
            "status": "listening",
            "message": "Progress stream connected.",
        },
    )
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await progress_hub.disconnect(run_id, websocket)
