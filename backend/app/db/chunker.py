from __future__ import annotations

from typing import Any


def _pct(val: float | int) -> str:
    return f"{round(float(val))}%"


def _chunks_from_agent1(data: dict[str, Any]) -> list[dict[str, Any]]:
    loc = data.get("location", "this area")
    chunks: list[dict[str, Any]] = []

    # Overview
    income = f"${data['median_income']:,}" if data.get("median_income") else "N/A"
    density = f"{data['population_density_per_sq_mile']:,.0f}/sq mi" if data.get("population_density_per_sq_mile") else ""
    chunks.append({
        "chunk_type": "area_overview",
        "text": (
            f"Neighborhood overview for {loc}. "
            f"Total population: {data.get('total_pop', 'N/A'):,}. "
            f"Households: {data['household_count']:,}. " if data.get("household_count") else
            f"Total population: {data.get('total_pop', 'N/A'):,}. "
            f"Income tier: {data.get('income_tier', 'N/A')}. "
            f"Median household income: {income}. "
            f"Population density: {density}. "
            f"Primary language: {data.get('primary_language', 'N/A')}."
        ),
    })

    # Race demographics
    race_parts: list[str] = []
    for race, val in (data.get("race_demographics") or {}).items():
        if isinstance(val, dict) and val.get("share_pct", 0) >= 1:
            label = race.replace(" alone", "").replace(" (any race)", "")
            race_parts.append(f"{label} {_pct(val['share_pct'])}")
    race_parts.sort(key=lambda x: -float(x.split()[-1].replace("%", "")))
    if race_parts:
        chunks.append({
            "chunk_type": "race_demographics",
            "text": f"Race and ethnicity breakdown for {loc}: {', '.join(race_parts)}.",
        })

    # Religion demographics
    rel_parts: list[str] = []
    for religion, val in (data.get("religion_demographics") or {}).items():
        if isinstance(val, dict):
            rel_parts.append(
                f"{religion} ({val.get('count', 0):,} congregations, {_pct(val.get('share_pct', 0))})"
            )
    rel_parts.sort(key=lambda x: -int(x.split("(")[1].split(" ")[0].replace(",", "")))
    if rel_parts:
        chunks.append({
            "chunk_type": "religion_demographics",
            "text": f"Religious communities near {loc}: {', '.join(rel_parts)}.",
        })

    # Age groups
    age_sorted = sorted(
        ((k, v) for k, v in (data.get("age_groups") or {}).items() if isinstance(v, dict)),
        key=lambda x: x[1].get("share_pct", 0),
        reverse=True,
    )
    age_parts = [f"{k} {_pct(v['share_pct'])}" for k, v in age_sorted[:6]]
    if age_parts:
        chunks.append({
            "chunk_type": "age_demographics",
            "text": f"Age distribution in {loc}: {', '.join(age_parts)}.",
        })

    return chunks


def _chunks_from_agent2(data: dict[str, Any]) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    for cat in data.get("categories") or []:
        drivers = ", ".join(cat.get("drivers") or [])
        evidence = ", ".join(cat.get("evidence") or [])
        chunks.append({
            "chunk_type": "product_category",
            "text": (
                f"Product category to stock: {cat.get('category', '')}. "
                f"Why: {cat.get('rationale', '')}. "
                f"Key demand drivers: {drivers}. "
                f"Suggested specific items: {evidence}. "
                f"Data source: {cat.get('source', '')}."
            ),
        })
    return chunks


def _chunks_from_agent3(data: dict[str, Any]) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    for evt in data.get("events") or []:
        cats = ", ".join(evt.get("expected_demand_categories") or [])
        chunks.append({
            "chunk_type": "holiday_event",
            "text": (
                f"Upcoming holiday: {evt.get('holiday', '')} ({evt.get('tradition', '')} tradition). "
                f"Dates: {evt.get('start_date', '')} to {evt.get('end_date', '')} "
                f"— {evt.get('days_until', '?')} days away. "
                f"Affects {_pct(evt.get('relevant_population_pct', 0))} of the local population. "
                f"Categories to stock up on: {cats}. "
                f"Recommended stock-up window: {evt.get('stock_up_window', 'N/A')}. "
                f"Expected demand multiplier: {evt.get('estimated_demand_multiplier', 1):.2f}×. "
                f"{evt.get('demographic_rationale', '')}"
            ),
        })
    return chunks


def _chunks_from_agent4(data: dict[str, Any]) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    for rec in data.get("recommendations") or []:
        vendor_url = rec.get("vendor_url") or "no URL on file"
        addr = rec.get("vendor_address") or "N/A"
        unit_price = (
            f"${rec['vendor_unit_price']:.2f}{' / ' + rec['vendor_quantity'] if rec.get('vendor_quantity') else ''}"
            if rec.get("vendor_unit_price") else "N/A"
        )
        chunks.append({
            "chunk_type": "vendor_recommendation",
            "text": (
                f"Product to stock: {rec.get('product', '')}. "
                f"Recommended vendor: {rec.get('suggested_vendor', '')} ({vendor_url}). "
                f"Vendor address: {addr}. "
                f"Vendor unit price: {unit_price}. "
                f"Wholesale cost: ${rec.get('wholesale_cost_estimate', 0):.2f}, "
                f"suggested retail: ${rec.get('suggested_retail_price', 0):.2f}, "
                f"margin: {rec.get('margin_pct', 0):.0f}%. "
                f"Reorder trigger: {rec.get('reorder_trigger_units', 'N/A')} units. "
                f"Rationale: {rec.get('rationale', '')}. "
                f"Data source: {rec.get('data_source', '')}."
            ),
        })
    return chunks


_AGENT_FNS = {
    "agent1": _chunks_from_agent1,
    "agent2": _chunks_from_agent2,
    "agent3": _chunks_from_agent3,
    "agent4": _chunks_from_agent4,
}


def build_agent_chunks(
    agent: str,
    session_id: str,
    zip_code: str,
    store_name: str,
    data: dict[str, Any],
) -> list[dict[str, Any]]:
    """Return embeddable chunks for a single agent's output."""
    fn = _AGENT_FNS.get(agent)
    if fn is None:
        raise ValueError(f"Unknown agent: {agent!r}")
    base = {"session_id": session_id, "zip": zip_code, "store_name": store_name, "agent": agent}
    return [{**base, **chunk} for chunk in fn(data)]


def build_chunks(
    session_id: str,
    zip_code: str,
    store_name: str,
    agent1: dict[str, Any],
    agent2: dict[str, Any],
    agent3: dict[str, Any],
    agent4: dict[str, Any],
) -> list[dict[str, Any]]:
    """Return all embeddable text chunks for a full report."""
    result: list[dict[str, Any]] = []
    for agent_key, data in [
        ("agent1", agent1), ("agent2", agent2),
        ("agent3", agent3), ("agent4", agent4),
    ]:
        result.extend(build_agent_chunks(agent_key, session_id, zip_code, store_name, data))
    return result
