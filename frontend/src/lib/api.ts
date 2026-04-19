const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

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

export type Agent2Category = { category: string; score: number; rationale: string };
export type Agent2Output = { categories: Agent2Category[] };

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
