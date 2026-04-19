from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/reports", tags=["reports"])


class SaveAgentRequest(BaseModel):
    session_id: str
    zip: str
    store_name: str
    agent: Literal["agent1", "agent2", "agent3", "agent4"]
    data: dict[str, Any]


class SaveReportRequest(BaseModel):
    session_id: str
    zip: str
    store_name: str
    store_type: str
    agent1: dict[str, Any]
    agent2: dict[str, Any]
    agent3: dict[str, Any]
    agent4: dict[str, Any]


class ReportSummary(BaseModel):
    session_id: str
    zip: str
    store_name: str
    generated_at: str


@router.post("/save", status_code=201)
async def save_report(req: SaveReportRequest) -> dict[str, str]:
    """
    Persist the full 4-agent report and embed all text chunks into MongoDB Atlas.
    Embedding happens in a thread-pool executor so it doesn't block the event loop.
    """
    try:
        from app.db.mongodb import get_reports_col, get_chunks_col
        from app.db.embeddings import embed
        from app.db.chunker import build_chunks

        now = datetime.now(timezone.utc).isoformat()

        # Upsert the full report document (idempotent on session_id)
        get_reports_col().replace_one(
            {"session_id": req.session_id},
            {
                "session_id": req.session_id,
                "zip": req.zip,
                "store_name": req.store_name,
                "store_type": req.store_type,
                "generated_at": now,
                "agent1": req.agent1,
                "agent2": req.agent2,
                "agent3": req.agent3,
                "agent4": req.agent4,
            },
            upsert=True,
        )

        # Build chunks then embed + upsert — all sync, run in executor
        chunks = build_chunks(
            req.session_id, req.zip, req.store_name,
            req.agent1, req.agent2, req.agent3, req.agent4,
        )

        def _embed_and_store() -> None:
            col = get_chunks_col()
            # Clear old chunks for this session before inserting fresh ones
            col.delete_many({"session_id": req.session_id})
            embedded: list[dict[str, Any]] = []
            for chunk in chunks:
                try:
                    vec = embed(chunk["text"])
                    embedded.append({**chunk, "embedding": vec})
                except Exception:
                    # Store chunk without embedding rather than failing the whole save
                    embedded.append(chunk)
            if embedded:
                col.insert_many(embedded)

        await asyncio.get_event_loop().run_in_executor(None, _embed_and_store)

        return {"session_id": req.session_id, "status": "saved"}

    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/save-agent", status_code=201)
async def save_agent(req: SaveAgentRequest) -> dict[str, str]:
    """
    Embed and store chunks for a single agent's output.
    Replaces any existing chunks for this session+agent pair.
    """
    try:
        from app.db.mongodb import get_chunks_col
        from app.db.embeddings import embed
        from app.db.chunker import build_agent_chunks

        chunks = build_agent_chunks(req.agent, req.session_id, req.zip, req.store_name, req.data)

        def _embed_and_store() -> None:
            col = get_chunks_col()
            col.delete_many({"session_id": req.session_id, "agent": req.agent})
            embedded: list[dict[str, Any]] = []
            for chunk in chunks:
                try:
                    vec = embed(chunk["text"])
                    embedded.append({**chunk, "embedding": vec})
                except Exception:
                    embedded.append(chunk)
            if embedded:
                col.insert_many(embedded)

        await asyncio.get_event_loop().run_in_executor(None, _embed_and_store)
        return {"session_id": req.session_id, "agent": req.agent, "status": "saved"}

    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("", response_model=list[ReportSummary])
async def list_reports(zip: str | None = None) -> list[ReportSummary]:
    """
    List distinct sessions derived from the chunks collection.
    The timestamp is extracted from the ObjectId of the most recently inserted chunk.
    """
    try:
        from app.db.mongodb import get_chunks_col

        match: dict[str, Any] = {}
        if zip:
            match["zip"] = zip

        pipeline: list[dict[str, Any]] = []
        if match:
            pipeline.append({"$match": match})

        pipeline += [
            # Sort descending so $first picks the latest chunk per session
            {"$sort": {"_id": -1}},
            {"$group": {
                "_id": "$session_id",
                "session_id": {"$first": "$session_id"},
                "zip": {"$first": "$zip"},
                "store_name": {"$first": "$store_name"},
                "latest_id": {"$first": "$_id"},
            }},
            # Derive ISO timestamp from ObjectId
            {"$addFields": {
                "generated_at": {
                    "$dateToString": {
                        "format": "%Y-%m-%dT%H:%M:%SZ",
                        "date": {"$toDate": "$latest_id"},
                    }
                }
            }},
            {"$sort": {"generated_at": -1}},
            {"$project": {"_id": 0, "latest_id": 0}},
            {"$limit": 30},
        ]

        docs = list(get_chunks_col().aggregate(pipeline))
        return [ReportSummary(**d) for d in docs]

    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
