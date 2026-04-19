from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

from app.agents.agent1.routes import router as agent1_router
from app.agents.agent2.routes import router as agent2_router
from app.agents.agent4.routes import router as agent4_router
from app.orchestration.routes import router as orchestration_router


load_dotenv(Path(__file__).resolve().parents[1] / ".env")


class HealthResponse(BaseModel):
    service: str
    status: str
    timestamp: str


app = FastAPI(
    title="BodegaPlanr API",
    version="0.1.0",
    description="Backend API for Corner Store Planning agents and report workflows.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(agent1_router)
app.include_router(agent2_router)
app.include_router(agent4_router)
app.include_router(orchestration_router)


@app.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    return HealthResponse(
        service="bodegaplanr-backend",
        status="ok",
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
