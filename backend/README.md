# Backend

FastAPI service for BodegaPlanr.

## Agent layout

- `app/agents/agent1` — demographic profiling with free Census APIs and an optional ARDA CSV hook.
- `app/agents/agent2` — buying behavior suggester driven by Agent 1 demographics.
- `app/agents/agent3` — holiday calendar placeholder.
- `app/agents/agent4` — vendor and inventory placeholder.

Each agent lives in its own folder so two people can work in parallel with minimal merge conflict risk.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Test

```bash
pytest
```
