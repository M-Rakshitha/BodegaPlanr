# Agent 4 Build Checklist

## Goal

Build Agent 4 as the final execution layer that turns the earlier agent outputs into store action items: vendor choices, inventory recommendations, pricing, and reorder thresholds.

## Inputs To Use

- Agent 1: demographic profile, race, religion, geography coverage, total population
- Agent 2: demand categories or product priority signals
- Agent 3: seasonal or holiday demand signals
- Optional: location context and store constraints if already available in orchestration

## Output Shape

- Product or category name
- Suggested vendor or vendor type
- Expected wholesale cost
- Suggested retail price
- Margin percentage
- Reorder trigger quantity
- Short rationale for the recommendation

## Build Steps

1. Define the Agent 4 request and response models.
2. Keep the logic deterministic first, using rules instead of LLM output.
3. Map category signals to product suggestions.
4. Add pricing and margin heuristics.
5. Add reorder threshold logic based on demand strength and seasonality.
6. Filter or deprioritize weak signals so outputs stay focused.
7. Add tests for empty input, strong signal input, and stable output formatting.
8. Connect Agent 4 to orchestration only after the standalone module works.

## Implementation Notes

- Keep Agent 4 inside `backend/app/agents/agent4`.
- Do not modify Agent 1 behavior unless Agent 4 needs a new field from its output.
- Prefer simple deterministic rules before introducing any LLM refinement.
- Make sure the output is easy to read and stable enough for tests.

## Test Checklist

- Returns a valid response for normal inputs
- Handles missing or empty category signals
- Produces non-negative margin and reorder values
- Returns the same output structure across runs
- Does not depend on Agent 1 internals beyond its public response shape
