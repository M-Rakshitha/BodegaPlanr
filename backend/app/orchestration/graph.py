from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from typing import Any, TypedDict, cast

from app.agents.agent1.models import DemographicProfileRequest, DemographicProfileResponse
from app.agents.agent1.service import DemographicProfiler
from app.agents.agent2.service import BuyingBehaviorSuggester
from app.rate_limit import set_gemini_cooldown, set_outbound_cooldown, wait_for_gemini_slot, wait_for_outbound_slot
from app.orchestration.models import (
    Agent2Output,
    Agent3Output,
    Agent4Output,
    OrchestrationRequest,
    OrchestratedReportResponse,
)


class GraphState(TypedDict, total=False):
    request: OrchestrationRequest
    agent1: dict[str, Any]
    agent2: dict[str, Any]
    agent3: dict[str, Any]
    agent4: dict[str, Any]
    llm_model: str | None


async def run_orchestration(request: OrchestrationRequest) -> OrchestratedReportResponse:
    try:
        from langgraph.graph import END, START, StateGraph
    except ImportError as error:
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
    return OrchestratedReportResponse(
        generated_at=datetime.now(timezone.utc),
        location=agent1_output["location"],
        llm_model=final_state.get("llm_model"),
        agent1=agent1_output,
        agent2=Agent2Output.model_validate(final_state["agent2"]),
        agent3=Agent3Output.model_validate(final_state["agent3"]),
        agent4=Agent4Output.model_validate(final_state["agent4"]),
    )


async def _agent1_node(state: GraphState) -> GraphState:
    request = state["request"]
    profiler = DemographicProfiler()
    profile = await profiler.build_profile(
        DemographicProfileRequest(address=request.address, zip_code=request.zip_code),
    )
    profile_payload = profile.model_dump()

    if not request.include_religion:
        profile_payload["religion_demographics"] = None

    return {"agent1": profile_payload}


async def _agent2_node(state: GraphState) -> GraphState:
    agent1 = state["agent1"]
    suggestion = await BuyingBehaviorSuggester().suggest(DemographicProfileResponse.model_validate(agent1))
    return {"agent2": {"categories": [category.model_dump() for category in suggestion.categories]}, "llm_model": state.get("llm_model")}


async def _agent3_node(state: GraphState) -> GraphState:
    agent1 = state["agent1"]
    race = agent1.get("race_demographics", {})

    signals = [
        {
            "holiday": "Back-to-school window",
            "start_window_days": 30,
            "demand_multiplier": 1.15,
            "rationale": "General seasonal uplift for snacks and beverages.",
        }
    ]

    if race.get("Hispanic or Latino (any race)", {}).get("share_pct", 0) >= 15:
        signals.append(
            {
                "holiday": "Hispanic heritage events (localized)",
                "start_window_days": 21,
                "demand_multiplier": 1.1,
                "rationale": "Higher Hispanic share supports culturally tuned seasonal promotions.",
            }
        )

    return {"agent3": {"upcoming_signals": signals}}


async def _agent4_node(state: GraphState) -> GraphState:
    categories = state["agent2"]["categories"]
    recommendations = []

    for index, item in enumerate(categories, start=1):
        wholesale = round(3.25 + index * 0.6, 2)
        margin = 38.0
        retail = round(wholesale / (1 - margin / 100), 2)
        recommendations.append(
            {
                "product": item["category"],
                "suggested_vendor": "Local wholesaler shortlist",
                "wholesale_cost_estimate": wholesale,
                "suggested_retail_price": retail,
                "margin_pct": margin,
                "reorder_trigger_units": 8,
            }
        )

    return {"agent4": {"recommendations": recommendations}}


async def _maybe_gemini_refine_categories(
    agent1_payload: dict[str, Any],
    categories: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]] | None, str | None]:
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
        response = await llm.ainvoke(prompt)
        content = response.content if isinstance(response.content, str) else ""
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
