# Agent 3

Religious holiday demand calendar built from Agent 1 demographic output.

## Endpoint

- `POST /agents/agent-3/calendar`

Request body:

- `profile`: Agent 1 `DemographicProfileResponse` payload
- `horizon_days` (optional): defaults to `90` (range `14..180`)

Response highlights:

- 90-day event list (or custom horizon) with:
  - holiday name and tradition
  - start/end dates and days until event
  - relevant local population % (inferred from religion distribution)
  - expected demand categories
  - stock-up window recommendation
  - estimated demand multiplier
  - source label and links
- data gaps and source inventory

## Data Sources

- Hebcal API for Jewish holidays
- Aladhan API for Hijri calendar derived holidays (Ramadan/Eid)
- Nager public holiday API for Christian public markers (for US)
- Gemini AI fallback for traditions not covered by API results in the requested horizon

## Notes

- This agent is API-first and resilient: source-specific failures are captured in `data_gaps` while still returning partial events.
- No hardcoded festival-date table is used for event generation.
- Demand multipliers are population-adjusted so higher local representation increases projected uplift.
