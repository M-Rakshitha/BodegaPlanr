const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8001';

// ─── Types mirroring backend Pydantic models ──────────────────────────────────

export type CountShare = { count: number; share_pct: number };

export type CategoryDemographic = {
  count: number;
  share_pct: number;
  subcategories: Record<string, CountShare>;
};

export type GeographyCoverage = {
  geography_unit: 'county' | 'census_tract' | 'zcta';
  coverage_id: string;
  estimated_radius_miles: number | null;
  explanation: string;
};

export type Agent1Output = {
  location: string;
  geography_type: 'address' | 'zip';
  total_pop: number;
  household_count: number | null;
  population_density_per_sq_mile: number | null;
  geography_coverage: GeographyCoverage;
  age_groups: Record<string, CountShare>;
  race_demographics: Record<string, CategoryDemographic>;
  religion_demographics: Record<string, CategoryDemographic> | null;
  median_income: number | null;
  income_tier: string;
  primary_language: string;
  sources: string[];
};

export type Agent2Category = {
  category: string;
  rationale: string;
  drivers: string[];
  evidence: string[];
  source: string;
  source_links: string[];
};

export type Agent2Signal = {
  dimension: string;
  label: string;
  share_pct: number;
  confidence: string;
  rationale: string;
  source: string;
};

export type Agent2Output = {
  location: string;
  top_signals: Agent2Signal[];
  categories: Agent2Category[];
  data_gaps: string[];
};

export type Agent3Signal = {
  holiday: string;
  start_window_days: number;
  demand_multiplier: number;
  rationale: string;
};
export type Agent3Output = { upcoming_signals: Agent3Signal[] };

export type Agent4Recommendation = {
  product: string;
  suggested_vendor: string;
  wholesale_cost_estimate: number;
  suggested_retail_price: number;
  margin_pct: number;
  reorder_trigger_units: number;
};
export type Agent4Output = { recommendations: Agent4Recommendation[] };

export type OrchestratedReport = {
  generated_at: string;
  location: string;
  llm_model: string | null;
  agent1: Agent1Output;
  agent2: Agent2Output;
  agent3: Agent3Output;
  agent4: Agent4Output;
};

// ─── API function ─────────────────────────────────────────────────────────────

export async function runOrchestration(zip: string): Promise<OrchestratedReport> {
  const res = await fetch(`${API_BASE}/orchestration/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ zip }),
  });

  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(`API error ${res.status}${text ? ': ' + text : ''}`);
  }

  return res.json();
}

export async function runAgent1(zip: string): Promise<Agent1Output> {
  const res = await fetch(`${API_BASE}/agents/agent-1/profile`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ zip_code: zip }),
  });

  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(`Agent1 API error ${res.status}${text ? ': ' + text : ''}`);
  }

  return res.json();
}

export async function runAgent2(profile: Agent1Output): Promise<Agent2Output> {
  const res = await fetch(`${API_BASE}/agents/agent-2/suggest`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ profile }),
  });

  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(`Agent2 API error ${res.status}${text ? ': ' + text : ''}`);
  }

  return res.json();
}
