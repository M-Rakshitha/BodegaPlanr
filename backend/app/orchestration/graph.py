from __future__ import annotations

import asyncio
import json
import os
import re
from datetime import datetime, timezone
from typing import Any, TypedDict, cast

from app.agents.agent1.models import DemographicProfileRequest, DemographicProfileResponse
from app.agents.agent1.service import DemographicProfiler
from app.agents.agent2.service import BuyingBehaviorSuggester
from app.agents.agent3.service import ReligiousHolidayCalendarBuilder
from app.agents.agent4.models import Agent4Request, Agent4RequestCategory, Agent4RequestHoliday
from app.agents.agent4.service import VendorInventoryRecommender
from app.orchestration.models import (
    Agent2Output,
    Agent3Output,
    Agent4Output,
    OrchestrationRequest,
    OrchestratedReportResponse,
)
from app.orchestration.progress import progress_hub
from app.rate_limit import set_gemini_cooldown, set_outbound_cooldown, wait_for_gemini_slot, wait_for_outbound_slot


class GraphState(TypedDict, total=False):
    request: OrchestrationRequest
    agent1: dict[str, Any]
    agent2: dict[str, Any]
    agent3: dict[str, Any]
    agent4: dict[str, Any]
    combined_top_suggestions: list[str]
    llm_model: str | None


async def run_orchestration(request: OrchestrationRequest) -> OrchestratedReportResponse:
    run_id = request.run_id
    await _emit_progress(
        run_id,
        stage="orchestration",
        event="orchestration_started",
        status="started",
        message="Starting orchestration graph.",
    )

    try:
        from langgraph.graph import END, START, StateGraph
    except ImportError as error:
        await _emit_progress(
            run_id,
            stage="orchestration",
            event="orchestration_failed",
            status="failed",
            message="LangGraph is not installed.",
            data={"error": str(error)},
        )
        raise RuntimeError("LangGraph is not installed. Add it to requirements and install dependencies.") from error

    graph = StateGraph(GraphState)
    graph.add_node("run_agent1", _agent1_node)
    graph.add_node("run_agent2", _agent2_node)
    graph.add_node("run_agent3", _agent3_node)
    graph.add_node("run_agent4", _agent4_node)

    graph.add_edge(START, "run_agent1")
    graph.add_edge("run_agent1", "run_agent2")
    graph.add_edge("run_agent2", "run_agent3")
    graph.add_edge("run_agent3", "run_agent4")
    graph.add_edge("run_agent4", END)

    compiled = graph.compile()
    final_state = await compiled.ainvoke({"request": request})

    agent1_output = final_state["agent1"]
    await _emit_progress(
        run_id,
        stage="orchestration",
        event="orchestration_completed",
        status="completed",
        message="All agent steps completed.",
        data={
            "combined_top_suggestions_count": len(final_state.get("combined_top_suggestions", [])),
            "agent4_recommendations_count": len(final_state["agent4"].get("recommendations", [])),
        },
    )
    return OrchestratedReportResponse(
        run_id=run_id,
        generated_at=datetime.now(timezone.utc),
        location=agent1_output["location"],
        llm_model=final_state.get("llm_model"),
        agent1=agent1_output,
        agent2=Agent2Output.model_validate(final_state["agent2"]),
        agent3=Agent3Output.model_validate(final_state["agent3"]),
        agent4=Agent4Output.model_validate(final_state["agent4"]),
        combined_top_suggestions=final_state.get("combined_top_suggestions", []),
    )


async def _agent1_node(state: GraphState) -> GraphState:
    request = state["request"]
    await _emit_progress(
        request.run_id,
        stage="agent1",
        event="agent1_started",
        status="started",
        message="Agent 1 is building demographic profile.",
    )
    try:
        profiler = DemographicProfiler()
        profile = await profiler.build_profile(
            DemographicProfileRequest(address=request.address, zip_code=request.zip_code),
        )
        profile_payload = profile.model_dump()

        if not request.include_religion:
            profile_payload["religion_demographics"] = None

        await _emit_progress(
            request.run_id,
            stage="agent1",
            event="agent1_completed",
            status="completed",
            message="Agent 1 profile ready.",
            data={
                "location": profile_payload.get("location"),
                "has_religion_data": profile_payload.get("religion_demographics") is not None,
            },
        )

        return {"agent1": profile_payload}
    except Exception as error:
        await _emit_progress(
            request.run_id,
            stage="agent1",
            event="agent1_failed",
            status="failed",
            message=str(error),
        )
        raise


async def _agent2_node(state: GraphState) -> GraphState:
    run_id = state["request"].run_id
    await _emit_progress(
        run_id,
        stage="agent2",
        event="agent2_started",
        status="started",
        message="Agent 2 is generating buying behavior suggestions.",
    )
    try:
        agent1 = state["agent1"]
        suggestion = await BuyingBehaviorSuggester().suggest(DemographicProfileResponse.model_validate(agent1))

        categories_payload: list[dict[str, Any]] = []
        for index, category in enumerate(suggestion.categories):
            inferred_score = max(0.05, 1.0 - (index * 0.08))
            categories_payload.append(
                {
                    "category": category.category,
                    "score": round(inferred_score, 2),
                    "rationale": category.rationale,
                    "evidence": category.evidence,
                    "source": category.source,
                }
            )

        top_items: list[str] = []
        for category in suggestion.categories:
            top_items.extend([item for item in category.evidence if item])
        for group_suggestion in suggestion.group_item_suggestions:
            top_items.extend([item for item in group_suggestion.all_year_items if item])

        deduped_items = _dedupe_non_empty(top_items)[:30]
        await _emit_progress(
            run_id,
            stage="agent2",
            event="agent2_completed",
            status="completed",
            message="Agent 2 suggestions ready.",
            data={
                "categories_count": len(categories_payload),
                "top_items_count": len(deduped_items),
            },
        )

        return {
            "agent2": {
                "categories": categories_payload,
                "top_items": deduped_items,
            },
            "llm_model": state.get("llm_model"),
        }
    except Exception as error:
        await _emit_progress(
            run_id,
            stage="agent2",
            event="agent2_failed",
            status="failed",
            message=str(error),
        )
        raise


async def _agent3_node(state: GraphState) -> GraphState:
    run_id = state["request"].run_id
    await _emit_progress(
        run_id,
        stage="agent3",
        event="agent3_started",
        status="started",
        message="Agent 3 is building holiday demand signals.",
    )
    try:
        agent1 = DemographicProfileResponse.model_validate(state["agent1"])
        calendar = await ReligiousHolidayCalendarBuilder().build_calendar(agent1, horizon_days=90)

        signals: list[dict[str, Any]] = []
        top_items: list[str] = []
        for event in calendar.events[:8]:
            if event.expected_demand_categories:
                top_items.extend(event.expected_demand_categories)
            signals.append(
                {
                    "holiday": event.holiday,
                    "start_window_days": max(0, event.days_until),
                    "demand_multiplier": event.estimated_demand_multiplier,
                    "rationale": event.demographic_rationale or (
                        f"{event.tradition.title()} demand window from Agent 3 holiday calendar."
                    ),
                    "demand_categories": event.expected_demand_categories,
                }
            )

        deduped_items = _dedupe_non_empty(top_items)[:30]
        await _emit_progress(
            run_id,
            stage="agent3",
            event="agent3_completed",
            status="completed",
            message="Agent 3 holiday signals ready.",
            data={
                "signals_count": len(signals),
                "top_items_count": len(deduped_items),
            },
        )

        return {
            "agent3": {
                "upcoming_signals": signals,
                "top_items": deduped_items,
            }
        }
    except Exception as error:
        await _emit_progress(
            run_id,
            stage="agent3",
            event="agent3_failed",
            status="failed",
            message=str(error),
        )
        raise


async def _agent4_node(state: GraphState) -> GraphState:
    run_id = state["request"].run_id
    await _emit_progress(
        run_id,
        stage="agent4",
        event="agent4_started",
        status="started",
        message="Agent 4 is generating vendor recommendations.",
    )
    try:
        categories = [
            Agent4RequestCategory(
                category=item["category"],
                score=float(item.get("score", 0.0)),
                rationale=str(item.get("rationale", "")),
            )
            for item in state["agent2"]["categories"]
        ]
        holidays = [
            Agent4RequestHoliday(
                holiday=item["holiday"],
                demand_multiplier=float(item.get("demand_multiplier", 1.0)),
            )
            for item in state["agent3"]["upcoming_signals"]
        ]

        combined_top_suggestions = _dedupe_non_empty(
            list(state["agent2"].get("top_items", [])) + list(state["agent3"].get("top_items", []))
        )[:50]

        agent1 = state["agent1"]
        location_zip = _extract_zip_from_agent1(agent1) or state["request"].zip_code

        request = Agent4Request(
            categories=categories,
            holidays=holidays,
            location_zip=location_zip,
            requested_items=combined_top_suggestions,
        )
        output = await VendorInventoryRecommender().generate_recommendations_async(request)
        await _emit_progress(
            run_id,
            stage="agent4",
            event="agent4_completed",
            status="completed",
            message="Agent 4 recommendations ready.",
            data={
                "recommendations_count": len(output.recommendations),
                "requested_items_count": len(combined_top_suggestions),
            },
        )
        return {
            "agent4": output.model_dump(),
            "combined_top_suggestions": combined_top_suggestions,
        }
    except Exception as error:
        await _emit_progress(
            run_id,
            stage="agent4",
            event="agent4_failed",
            status="failed",
            message=str(error),
        )
        raise


async def _emit_progress(
    run_id: str | None,
    *,
    stage: str,
    event: str,
    status: str,
    message: str,
    data: dict[str, Any] | None = None,
) -> None:
    if not run_id:
        return

    payload: dict[str, Any] = {
        "event": event,
        "run_id": run_id,
        "stage": stage,
        "status": status,
        "message": message,
    }
    if data:
        payload["data"] = data

    await progress_hub.publish(run_id, payload)


def _dedupe_non_empty(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = str(value).strip()
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(cleaned)
    return out


def _extract_zip_from_agent1(agent1_payload: dict[str, Any]) -> str | None:
    location = str(agent1_payload.get("location", "")).strip()
    match = re.search(r"\b(\d{5})(?:-\d{4})?\b", location)
    if match:
        return match.group(1)
    return None


async def _maybe_gemini_refine_categories(
    agent1_payload: dict[str, Any],
    categories: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]] | None, str | None]:
    gemini_timeout_seconds = 20.0

    def _extract_retry_after_seconds(message: str) -> float | None:
        retry_in_match = re.search(r"retry in\s+([0-9]+(?:\.[0-9]+)?)s", message, flags=re.IGNORECASE)
        if retry_in_match:
            return float(retry_in_match.group(1))

        retry_delay_match = re.search(r"retry_delay\s*\{\s*seconds:\s*([0-9]+)", message, flags=re.IGNORECASE)
        if retry_delay_match:
            return float(retry_delay_match.group(1))

        return None

    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return None, None

    model_name = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite-preview")

    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
    except ImportError:
        return None, model_name

    prompt = (
        "You are refining product category suggestions for a corner store planner. "
        "Return strict JSON array with fields: category, score, rationale. "
        "Use concise rationale and score range 0-1.\n\n"
        f"Agent1 demographic payload:\n{json.dumps(agent1_payload, indent=2)}\n\n"
        f"Current category draft:\n{json.dumps(categories, indent=2)}"
    )

    try:
        llm = ChatGoogleGenerativeAI(model=model_name, temperature=0.2, api_key=cast(Any, api_key), max_retries=0)
        await wait_for_gemini_slot()
        await wait_for_outbound_slot()
        response = await asyncio.wait_for(llm.ainvoke(prompt), timeout=gemini_timeout_seconds)
        content_obj = getattr(response, "content", "")
        if isinstance(content_obj, str):
            content = content_obj
        elif isinstance(content_obj, list):
            parts: list[str] = []
            for part in content_obj:
                if isinstance(part, dict):
                    txt = part.get("text") or part.get("content")
                    if isinstance(txt, str) and txt.strip():
                        parts.append(txt.strip())
                elif isinstance(part, str) and part.strip():
                    parts.append(part.strip())
            content = "\n".join(parts)
        else:
            content = str(content_obj or "")

        parsed = json.loads(content)
        if isinstance(parsed, list) and parsed:
            return parsed, model_name
    except Exception as error:
        msg = str(error)
        lowered = msg.lower()
        if "resourceexhausted" in lowered or "quota exceeded" in lowered or "429" in lowered:
            retry_after = _extract_retry_after_seconds(msg)
            wait_seconds = max(1.0, retry_after if retry_after is not None else 60.0) + 1.0
            await set_outbound_cooldown(wait_seconds)
            await set_gemini_cooldown(wait_seconds)
        return None, model_name

    return None, model_name
