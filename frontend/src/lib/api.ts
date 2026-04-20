const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'https://bodegaplanr-13.onrender.com';
const WS_BASE = API_BASE.replace(/^http/, 'ws');

export function runAgentViaWS<T>(
  path: string,
  payload: unknown,
  onProgress: (msg: string) => void,
): Promise<T> {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(`${WS_BASE}${path}`);

    ws.onopen = () => ws.send(JSON.stringify(payload));

    ws.onmessage = (event) => {
      let msg: { type: string; message?: string; data?: unknown };
      try { msg = JSON.parse(event.data as string); } catch { return; }
      if (msg.type === 'progress' && msg.message) {
        onProgress(msg.message);
      } else if (msg.type === 'result') {
        resolve(msg.data as T);
        ws.close();
      } else if (msg.type === 'error') {
        reject(new Error(msg.message ?? 'Unknown error'));
        ws.close();
      }
    };

    ws.onerror = () => reject(new Error('WebSocket connection failed'));
  });
}

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

export type HolidayDemandEvent = {
  holiday: string;
  tradition: 'jewish' | 'islamic' | 'christian' | 'hindu' | 'sikh' | 'community';
  start_date: string;
  end_date: string;
  days_until: number;
  relevant_population_pct: number;
  expected_demand_categories: string[];
  stock_up_window: string;
  estimated_demand_multiplier: number;
  matched_religion_demographics: string[];
  matched_race_demographics: string[];
  geography_context: string;
  demographic_rationale: string;
  source: string;
  source_links: string[];
};

export type Agent3Output = {
  location: string;
  generated_at: string;
  horizon_days: number;
  window_start: string;
  window_end: string;
  demographics_used: {
    top_religions_used: string[];
    top_races_used: string[];
    country_context: string;
  };
  events: HolidayDemandEvent[];
  data_gaps: string[];
  sources_used: string[];
};

export type Agent4Recommendation = {
  product: string;
  suggested_vendor: string;
  vendor_url: string | null;
  vendor_address: string | null;
  vendor_unit_price: number | null;
  vendor_quantity: string | null;
  wholesale_cost_estimate: number;
  suggested_retail_price: number;
  margin_pct: number;
  reorder_trigger_units: number;
  rationale: string;
  data_source: string;
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

// ─── Vector store / chat types ───────────────────────────────────────────────

export type ReportSummary = {
  session_id: string;
  zip: string;
  store_name: string;
  generated_at: string;
};

export type SourceRef = {
  agent: string;
  chunk_type: string;
  store_name: string;
};

export type ChatResponse = {
  answer: string;
  sources: SourceRef[];
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

export async function runAgent3(profile: Agent1Output): Promise<Agent3Output> {
  const res = await fetch(`${API_BASE}/agents/agent-3/calendar`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ profile }),
  });

  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(`Agent3 API error ${res.status}${text ? ': ' + text : ''}`);
  }

  return res.json();
}

export async function runAgent4(
  categories: Agent2Category[],
  events: HolidayDemandEvent[],
  zip: string,
): Promise<Agent4Output> {
  const res = await fetch(`${API_BASE}/agent4/recommend`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      categories: categories.map((c) => ({ ...c, score: 1.0 })),
      holidays: events.map((e) => ({ holiday: e.holiday, demand_multiplier: e.estimated_demand_multiplier })),
      location_zip: zip,
    }),
  });

  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(`Agent4 API error ${res.status}${text ? ': ' + text : ''}`);
  }

  return res.json();
}

// ─── Report persistence ───────────────────────────────────────────────────────

export async function saveAgentChunks(payload: {
  session_id: string;
  zip: string;
  store_name: string;
  agent: 'agent1' | 'agent2' | 'agent3' | 'agent4';
  data: Agent1Output | Agent2Output | Agent3Output | Agent4Output;
}): Promise<{ session_id: string; agent: string; status: string }> {
  const res = await fetch(`${API_BASE}/reports/save-agent`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(`Save agent error ${res.status}${text ? ': ' + text : ''}`);
  }
  return res.json();
}

export async function saveReport(payload: {
  session_id: string;
  zip: string;
  store_name: string;
  store_type: string;
  agent1: Agent1Output;
  agent2: Agent2Output;
  agent3: Agent3Output;
  agent4: Agent4Output;
}): Promise<{ session_id: string; status: string }> {
  const res = await fetch(`${API_BASE}/reports/save`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(`Save error ${res.status}${text ? ': ' + text : ''}`);
  }
  return res.json();
}

export async function getReports(zip?: string): Promise<ReportSummary[]> {
  const url = zip
    ? `${API_BASE}/reports?zip=${encodeURIComponent(zip)}`
    : `${API_BASE}/reports`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Reports error ${res.status}`);
  return res.json();
}

// ─── RAG chat ─────────────────────────────────────────────────────────────────

export async function chatQuery(
  message: string,
  session_id?: string,
  zip?: string,
): Promise<ChatResponse> {
  const res = await fetch(`${API_BASE}/chat/query`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, session_id, zip }),
  });
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(`Chat error ${res.status}${text ? ': ' + text : ''}`);
  }
  return res.json();
}
