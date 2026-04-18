from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, TypedDict

from app.agents.agent1.models import DemographicProfileRequest
from app.agents.agent1.service import DemographicProfiler
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
    race = agent1.get("race_demographics", {})
    age = agent1.get("age_groups", {})

    categories = [
        {
            "category": "Rice & grains",
            "score": 0.78,
            "rationale": "Baseline staple category for dense urban ZIP demand.",
        },
        {
            "category": "Ready-to-drink beverages",
            "score": 0.74,
            "rationale": "High convenience-store velocity across broad age distribution.",
        },
    ]

    top_asian = race.get("Asian alone", {}).get("share_pct", 0)
    youth_share = age.get("10-19", {}).get("share_pct", 0)

    if top_asian >= 10:
        categories.append(
            {
                "category": "Asian pantry staples",
                "score": 0.82,
                "rationale": "Elevated Asian population share suggests demand for culturally specific staples.",
            }
        )

    if youth_share >= 10:
        categories.append(
            {
                "category": "Snacks & impulse sweets",
                "score": 0.71,
                "rationale": "Teen share supports impulse-snack assortment depth.",
            }
        )

    llm_output, model_name = await _maybe_gemini_refine_categories(agent1, categories)
    if llm_output:
        return {"agent2": {"categories": llm_output}, "llm_model": model_name}

    return {"agent2": {"categories": categories}, "llm_model": model_name}


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
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return None, None

    model_name = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")

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
        llm = ChatGoogleGenerativeAI(model=model_name, temperature=0.2, api_key=api_key)
        response = await llm.ainvoke(prompt)
        parsed = json.loads(response.content)
        if isinstance(parsed, list) and parsed:
            return parsed, model_name
    except Exception:
        return None, model_name

    return None, model_name
