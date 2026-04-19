from __future__ import annotations

import asyncio
import os
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/chat", tags=["chat"])

_SYSTEM = (
    "You are BodegaPlanr, an AI assistant helping corner store owners make smart "
    "stocking and purchasing decisions. Answer using ONLY the report context provided. "
    "Be concise, practical, and specific — mention product names, vendor names, and "
    "dollar figures when available. If the context doesn't cover the question, say so "
    "honestly rather than guessing."
)


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None
    zip: str | None = None


class SourceRef(BaseModel):
    agent: str
    chunk_type: str
    store_name: str


class ChatResponse(BaseModel):
    answer: str
    sources: list[SourceRef]


@router.post("/query", response_model=ChatResponse)
async def chat_query(req: ChatRequest) -> ChatResponse:
    """
    RAG chat endpoint.
    1. Embed the user's question with text-embedding-004.
    2. Run Atlas Vector Search on the chunks collection to fetch the top-6 relevant passages.
    3. Pass those passages as grounding context to Gemini and return the answer.
    """
    try:
        from app.db.embeddings import embed
        from app.db.mongodb import get_chunks_col
        from google import genai

        def _run() -> ChatResponse:
            # ── 1. Embed query ────────────────────────────────────────────────
            q_vec = embed(req.message)

            # ── 2. Build optional filter ──────────────────────────────────────
            match_filter: dict[str, Any] = {}
            if req.session_id:
                match_filter["session_id"] = req.session_id
            elif req.zip:
                match_filter["zip"] = req.zip

            # ── 3. Atlas Vector Search pipeline ──────────────────────────────
            vector_stage: dict[str, Any] = {
                "index": "bodega_vector_index",
                "path": "embedding",
                "queryVector": q_vec,
                "numCandidates": 80,
                "limit": 6,
            }
            if match_filter:
                vector_stage["filter"] = match_filter

            pipeline: list[dict[str, Any]] = [
                {"$vectorSearch": vector_stage},
                {
                    "$project": {
                        "_id": 0,
                        "text": 1,
                        "agent": 1,
                        "chunk_type": 1,
                        "store_name": 1,
                        "zip": 1,
                        "score": {"$meta": "vectorSearchScore"},
                    }
                },
            ]

            chunks = list(get_chunks_col().aggregate(pipeline))

            if not chunks:
                return ChatResponse(
                    answer=(
                        "I don't have any report data to draw from yet. "
                        "Please run the wizard to generate a report first — "
                        "then I can answer questions grounded in your store's data."
                    ),
                    sources=[],
                )

            # ── 4. Build grounding context ────────────────────────────────────
            context_blocks = "\n\n".join(
                f"[{c['agent'].upper()} — {c['chunk_type'].replace('_', ' ')}]\n{c['text']}"
                for c in chunks
            )

            prompt = (
                f"{_SYSTEM}\n\n"
                f"Report context:\n{context_blocks}\n\n"
                f"Question: {req.message}\n\n"
                f"Answer:"
            )

            # ── 5. Generate answer with Gemini ────────────────────────────────
            client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])
            model = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash-lite")
            response = client.models.generate_content(model=model, contents=prompt)

            sources = [
                SourceRef(
                    agent=c["agent"],
                    chunk_type=c["chunk_type"],
                    store_name=c.get("store_name", ""),
                )
                for c in chunks
            ]

            return ChatResponse(answer=response.text.strip(), sources=sources)

        return await asyncio.get_event_loop().run_in_executor(None, _run)

    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
