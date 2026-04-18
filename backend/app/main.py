from datetime import datetime, timezone

from fastapi import FastAPI
from pydantic import BaseModel


class HealthResponse(BaseModel):
    service: str
    status: str
    timestamp: str


app = FastAPI(
    title="BodegaPlanr API",
    version="0.1.0",
    description="Backend API for Corner Store Planning agents and report workflows.",
)


@app.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    return HealthResponse(
        service="bodegaplanr-backend",
        status="ok",
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
