# Backend

FastAPI service for BodegaPlanr.

This backend supports both:

1. Direct single-agent endpoints (`agent-1`, `agent-2`, `agent-3`, `agent4`).
1. A full orchestration endpoint that chains agents end-to-end.

## What The End-to-End Workflow Does

For a given location (address or ZIP):

1. Agent 1 builds a demographic profile.
1. Agent 2 uses Agent 1 output to suggest buying behavior categories and top items.
1. Agent 3 uses Agent 1 output to build a 90-day holiday demand calendar and top holiday-driven items.
1. Orchestration combines top suggestions from Agent 2 and Agent 3.
1. Agent 4 receives:
   - category context,
   - holiday signals,
   - combined top item list,
   - location ZIP context,
     and returns vendor/inventory recommendations.

## Rate Limit And Speed Guarantees

All outbound and Gemini calls use shared sliding-window limiters.

- `OUTBOUND_API_MAX_REQUESTS_PER_MINUTE` is clamped to max `13`.
- `GEMINI_MAX_REQUESTS_PER_MINUTE` is clamped to max `13`.

Even if environment values are set higher, runtime clamping enforces `<= 13/min`.

## API Endpoints

### 1) Agent 1: Demographic Profiler

- `POST /agents/agent-1/profile`

Input:

```json
{
  "address": "2121 I St NW, Washington, DC 20052"
}
```

or:

```json
{
  "zip_code": "20052"
}
```

Output highlights:

- `location`, `geography_type`, `total_pop`, `household_count`
- `age_groups`, `top_age_groups`
- `race_demographics`, `top_races`
- `religion_demographics`, `top_religions`
- `median_income`, `income_tier`, `primary_language`

### 2) Agent 2: Buying Behavior Suggester

- `POST /agents/agent-2/suggest`

Input:

- Agent 1 profile object (either wrapped in `profile` or raw profile payload).

Output highlights:

- `categories` (ranked category suggestions)
- `group_item_suggestions` (race/religion-specific item lists)
- `data_gaps`
- `coverage_statistics`

### 3) Agent 3: Religious Holiday Calendar

- `POST /agents/agent-3/calendar`

Input:

```json
{
  "profile": { "...agent1 profile...": "..." },
  "horizon_days": 90
}
```

Output highlights:

- `events` with holiday windows, multipliers, and demographic linkage
- `demographics_used`
- `data_gaps`
- `sources_used`

### 4) Agent 4: Vendor & Inventory Recommender

- `POST /agent4/recommend`

Input:

- `categories` from Agent 2
- optional `holidays` from Agent 3
- optional `requested_items` (important for combined top suggestions flow)
- optional `location_zip`

Output:

- `recommendations[]` with product/vendor/price/margin/reorder details

### 5) Full Orchestration

- `POST /orchestration/run`

Input:

```json
{
  "address": "2121 I St NW, Washington, DC 20052",
  "include_religion": true
}
```

or:

```json
{
  "zip": "20052",
  "include_religion": true
}
```

Output structure:

- `agent1`: full demographic profile
- `agent2`: categories + `top_items`
- `agent3`: holiday signals + `top_items`
- `combined_top_suggestions`: deduped union of Agent 2 + Agent 3 top items
- `agent4`: vendor recommendations produced using combined suggestions + location context

## Data Flow Details For Orchestration

1. `run_agent1`
   - resolves address/zip demographics.
1. `run_agent2`
   - builds behavior categories and extracts top item suggestions from category evidence and group item lists.
1. `run_agent3`
   - builds holiday signals and extracts top holiday demand categories.
1. `run_agent4`
   - merges Agent 2 + Agent 3 top items into `combined_top_suggestions`.
   - passes combined suggestions to Agent 4 via `requested_items`.
   - uses ZIP extracted from Agent 1 location (or request ZIP fallback).

## Run Locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Health check:

```bash
curl http://127.0.0.1:8000/health
```

## Test Workflow (Address -> Agents 1/2/3 -> Agent 4)

Integration test file:

- `tests/test_orchestration_workflow.py`

Run it:

```bash
.venv/bin/python -m pytest -q tests/test_orchestration_workflow.py
```

This test verifies:

1. Address-based orchestration request succeeds.
1. Agent 1/2/3/4 sections are present.
1. Agent 2 and Agent 3 both emit top item lists.
1. `combined_top_suggestions` is non-empty.
1. Agent 4 returns recommendation list shape.

## Full Test Suite

```bash
pytest
```
