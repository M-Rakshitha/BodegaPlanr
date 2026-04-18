# BodegaPlanr

Starter monorepo for **Corner Store Planning**, with separate frontend and backend projects.

## Repository Layout

- `/frontend` — Next.js + Tailwind UI starter for the report wizard, customer data mode, and RAG chat.
- `/backend` — FastAPI service starter for agent orchestration endpoints and data integrations.

## Product Scope (Build Spec)

BodegaPlanr is a multi-agent platform for small store owners to make better inventory and vendor decisions using:

1. **Demographic Profiler** (Census + ARDA)
2. **Buying Behavior Suggester** (CEX + curated rules)
3. **Religious Holiday Calendar** (Hebcal + Aladhan)
4. **Vendor & Inventory Recommender** (RangeMe/Faire/distributor catalogs)

### UI Sections

1. **Report Generator Wizard** (sequential agent flow)
2. **Customer Data Mode** (CSV upload and delta analysis)
3. **RAG Chat** (saved report chunks + vector search)

## Quick Start

### Frontend

```bash
cd /home/runner/work/BodegaPlanr/BodegaPlanr/frontend
npm install
npm run dev
```

### Backend

```bash
cd /home/runner/work/BodegaPlanr/BodegaPlanr/backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Backend health check:

```bash
curl http://127.0.0.1:8000/health
```

## Next Implementation Steps

- Add API routes for each agent workflow stage.
- Wire Agent 1 and Agent 4 first for hackathon MVP.
- Add Pinecone-backed report save + retrieval.
- Build persistent RAG chat grounded on saved reports.
