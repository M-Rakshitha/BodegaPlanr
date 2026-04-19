'use client';
import { useState, useEffect, useRef, Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { runAgentViaWS, saveAgentChunks, type Agent1Output, type Agent2Output, type Agent3Output, type Agent4Output } from '@/lib/api';

type StoreInfo = { name: string; zip: string; type: string };

const RACE_COLORS: Record<string, string> = {
  'White': 'bg-blue-400',
  'Black or African American': 'bg-violet-500',
  'Hispanic or Latino (any race)': 'bg-brand-500',
  'Asian': 'bg-amber-400',
  'Two or more races': 'bg-rose-400',
  'American Indian or Alaska Native': 'bg-orange-400',
  'Some other race': 'bg-slate-400',
  'Native Hawaiian or Other Pacific Islander': 'bg-teal-400',
};


// ─── Demographics sub-components ─────────────────────────────────────────────

function DemoStatCard({
  label,
  value,
  dark,
}: {
  label: string;
  value: string;
  dark?: boolean;
}) {
  return (
    <div
      className={`flex flex-col justify-between rounded-2xl p-5 ${
        dark ? 'bg-brand-900 text-white' : 'bg-white border border-slate-100 shadow-sm'
      }`}
    >
      <p className={`text-xs font-semibold uppercase tracking-wider ${dark ? 'text-brand-300' : 'text-slate-400'}`}>
        {label}
      </p>
      <p className={`mt-3 text-3xl font-bold tracking-tight leading-none ${dark ? 'text-white' : 'text-slate-900'}`}>
        {value}
      </p>
    </div>
  );
}

function EthnicityBar({ label, pct, color }: { label: string; pct: number; color: string }) {
  return (
    <div className="flex items-center gap-3">
      <div className="w-36 shrink-0 text-right text-xs text-slate-500 truncate">{label}</div>
      <div className="relative flex-1 h-7 overflow-hidden rounded-lg bg-slate-100">
        <div
          className={`h-full rounded-lg ${color} transition-all duration-500`}
          style={{ width: `${pct}%` }}
        />
        <span className="absolute right-2 top-1/2 -translate-y-1/2 text-xs font-bold text-slate-700">
          {pct}%
        </span>
      </div>
    </div>
  );
}


// ─── Step 0: Demographics ─────────────────────────────────────────────────────

function DemographicsStep({ data }: { data: Agent1Output }) {
  const ethnicity = Object.entries(data.race_demographics)
    .map(([key, val]) => ({
      rawKey: key,
      label: key.replace(' alone', '').replace(' (any race)', ''),
      pct: Math.round(val.share_pct),
      color: RACE_COLORS[key] ?? 'bg-slate-300',
    }))
    .filter((e) => e.pct >= 1)
    .sort((a, b) => b.pct - a.pct)
    .slice(0, 5);

  const religions = data.religion_demographics
    ? Object.entries(data.religion_demographics)
        .sort((a, b) => b[1].count - a[1].count)
        .slice(0, 6)
        .map(([label, val]) => ({
          label,
          count: val.count,
          share_pct: Math.round(val.share_pct),
        }))
    : [];

  const topGroup = ethnicity[0];
  const incomeTier = data.income_tier.charAt(0).toUpperCase() + data.income_tier.slice(1);
  const insight = topGroup
    ? `${topGroup.label} (${topGroup.pct}%) is the largest demographic group in this area. Income tier: ${incomeTier}. Primary language: ${data.primary_language}.`
    : `Income tier: ${incomeTier}. Primary language: ${data.primary_language}.`;

  const coverageLabel =
    data.geography_coverage.geography_unit === 'zcta'
      ? `ZIP ${data.geography_coverage.coverage_id}`
      : data.geography_coverage.geography_unit === 'county'
      ? `County ${data.geography_coverage.coverage_id}`
      : `Tract ${data.geography_coverage.coverage_id}`;

  return (
    <div>
      <div className="mb-1">
        <p className="text-xs font-semibold uppercase tracking-widest text-brand-600">Demographic Profiler</p>
        <h2 className="mt-1 text-2xl font-bold text-slate-900">Demographics</h2>
        <p className="mt-1 text-sm text-slate-500">
          {data.location} &middot; {coverageLabel}
          {data.geography_coverage.estimated_radius_miles != null &&
            ` &middot; ~${data.geography_coverage.estimated_radius_miles} mi radius`}
        </p>
      </div>

      {/* ── Stat Cards ── */}
      <div className="mt-6 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <DemoStatCard label="Total Population" value={data.total_pop.toLocaleString()} dark />
        <DemoStatCard
          label="Median Income"
          value={data.median_income ? `$${data.median_income.toLocaleString()}` : 'N/A'}
        />
        <DemoStatCard label="Income Tier" value={incomeTier} />
        <DemoStatCard label="Primary Language" value={data.primary_language} />
      </div>

      {/* ── Religion (middle — expanded & highlighted) ── */}
      <div className="mt-4 rounded-2xl border border-brand-200 bg-brand-50 p-6 shadow-sm">
        <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-widest text-brand-600">Religious Communities</p>
            <h3 className="mt-1 text-lg font-bold text-slate-900">Faith Landscape</h3>
          </div>
          <span className="rounded-full bg-brand-100 px-3 py-1 text-xs font-medium text-brand-700 ring-1 ring-brand-200">
            {religions.length} groups · {data.geography_coverage.coverage_id}
          </span>
        </div>

        {religions.length > 0 ? (
          <div className="space-y-2.5">
            {religions.map((r) => {
              const maxCount = religions[0].count;
              const barPct = Math.round((r.count / maxCount) * 100);
              return (
                <div key={r.label} className="flex items-center gap-4">
                  <div className="w-40 shrink-0 text-right text-xs font-semibold text-slate-700 truncate">{r.label}</div>
                  <div className="relative flex-1 h-7 rounded-full bg-brand-100 overflow-hidden">
                    <div
                      className="h-full rounded-full bg-brand-500 transition-all duration-700"
                      style={{ width: `${barPct}%` }}
                    />
                  </div>
                  <div className="w-28 shrink-0 text-xs text-slate-500">
                    <span className="font-semibold text-slate-700">{r.count.toLocaleString()}</span> congregations
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <p className="text-sm text-slate-400">No religion data available for this area.</p>
        )}

        <p className="mt-4 text-xs text-slate-400">Congregations in coverage area · ARDA dataset</p>
      </div>

      {/* ── Bottom row: Area Stats | Race & Ethnicity | Insight ── */}
      <div className="mt-4 grid gap-4 lg:grid-cols-[200px_1fr_220px]">
        {/* Area Stats */}
        <div className="rounded-2xl border border-slate-100 bg-white p-5 shadow-sm">
          <p className="text-sm font-semibold text-slate-700">Area Stats</p>
          <div className="mt-4 space-y-4">
            <div>
              <p className="text-2xl font-bold text-slate-900">{data.household_count?.toLocaleString() ?? 'N/A'}</p>
              <p className="text-xs text-slate-400">Households</p>
            </div>
            <div>
              <p className="text-2xl font-bold text-slate-900">
                {(() => {
                  const top = Object.entries(data.age_groups).sort((a, b) => b[1].share_pct - a[1].share_pct)[0];
                  return top ? `${top[0]} yrs` : 'N/A';
                })()}
              </p>
              <p className="text-xs text-slate-400">
                {(() => {
                  const top = Object.entries(data.age_groups).sort((a, b) => b[1].share_pct - a[1].share_pct)[0];
                  return top ? `Dominant age group · ${Math.round(top[1].share_pct)}%` : 'Dominant age group';
                })()}
              </p>
            </div>
          </div>
        </div>

        {/* Race & Ethnicity (moved to bottom middle) */}
        <div className="rounded-2xl border border-slate-100 bg-white p-5 shadow-sm">
          <div className="mb-4 flex items-center justify-between">
            <p className="text-sm font-semibold text-slate-700">Race & Ethnicity</p>
            <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-medium text-slate-500">
              {data.geography_coverage.coverage_id}
            </span>
          </div>
          <div className="space-y-3">
            {ethnicity.map((e) => (
              <EthnicityBar key={e.rawKey} label={e.label} pct={e.pct} color={e.color} />
            ))}
          </div>
        </div>

        {/* Insight */}
        <div className="flex flex-col justify-between rounded-2xl bg-brand-900 p-5 text-white shadow-sm">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wider text-brand-300">Agent Insight</p>
            <p className="mt-3 text-sm leading-relaxed text-brand-100">{insight}</p>
          </div>
          <div className="mt-4 h-px bg-brand-700" />
          <p className="mt-3 text-xs text-brand-400">
            Powered by Census ACS 2023
          </p>
        </div>
      </div>
    </div>
  );
}

// ─── Step 1: Product Mix ──────────────────────────────────────────────────────

function ProductMixStep({ data, profile }: { data: Agent2Output; profile: Agent1Output }) {
  // Build top-3 products per race
  const raceProducts: { race: string; pct: number; products: string[] }[] = Object.entries(profile.race_demographics)
    .map(([race, val]) => ({ race, pct: Math.round(val.share_pct) }))
    .filter((r) => r.pct >= 1)
    .sort((a, b) => b.pct - a.pct)
    .slice(0, 5)
    .map(({ race, pct }) => {
      const shortRace = race.replace(' alone', '').replace(' (any race)', '').toLowerCase();
      const products: string[] = [];
      const seen = new Set<string>();
      for (const cat of data.categories) {
        const driverMatch = cat.drivers.some((d) => d.toLowerCase().includes(shortRace) || shortRace.includes(d.toLowerCase().split(' ')[0]));
        const rationaleMatch = cat.rationale.toLowerCase().includes(shortRace);
        if (driverMatch || rationaleMatch) {
          for (const item of cat.evidence) {
            if (!seen.has(item) && products.length < 3) { seen.add(item); products.push(item); }
          }
        }
        if (products.length >= 3) break;
      }
      // fallback: fill from any category if no specific match
      if (products.length < 3) {
        for (const cat of data.categories) {
          for (const item of cat.evidence) {
            if (!seen.has(item) && products.length < 3) { seen.add(item); products.push(item); }
          }
          if (products.length >= 3) break;
        }
      }
      return { race: race.replace(' alone', '').replace(' (any race)', ''), pct, products };
    });

  return (
    <div>
      <p className="text-xs font-semibold uppercase tracking-widest text-brand-600">Buying Behavior Suggester</p>
      <h2 className="mt-1 text-2xl font-bold text-slate-900">Product Mix</h2>
      <p className="mt-1 text-sm text-slate-500">
        Categories based on your ZIP's demographic and religious community data.
      </p>

      {/* ── Top 3 products per race ── */}
      {raceProducts.length > 0 && (
        <div className="mt-6 rounded-2xl border border-brand-200 bg-brand-50 p-5">
          <p className="mb-4 text-xs font-semibold uppercase tracking-widest text-brand-600">
            Top Products by Race &amp; Ethnicity
          </p>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {raceProducts.map((r) => (
              <div key={r.race} className="rounded-xl bg-white p-4 shadow-sm ring-1 ring-brand-100">
                <div className="mb-3 flex items-center justify-between gap-2">
                  <p className="text-xs font-bold text-slate-800 leading-snug">{r.race}</p>
                  <span className="shrink-0 rounded-full bg-brand-100 px-2 py-0.5 text-xs font-semibold text-brand-700">
                    {r.pct}%
                  </span>
                </div>
                <div className="space-y-1.5">
                  {r.products.map((p, i) => (
                    <div key={i} className="flex items-center gap-2">
                      <span className="text-xs font-bold text-brand-300">{i + 1}</span>
                      <span className="text-xs text-slate-700">{p}</span>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        {data.categories.map((cat, i) => (
          <div key={i} className="flex flex-col rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="flex items-start gap-3">
              <span className="mt-0.5 shrink-0 text-xs font-bold text-slate-300">#{i + 1}</span>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-bold text-slate-800">{cat.category}</p>
                <p className="mt-1 text-xs leading-relaxed text-slate-500">{cat.rationale}</p>
              </div>
            </div>

            {cat.drivers.length > 0 && (
              <div className="mt-4">
                <p className="mb-1.5 text-xs font-semibold uppercase tracking-wider text-slate-400">Drivers</p>
                <div className="flex flex-wrap gap-1.5">
                  {cat.drivers.map((d, j) => (
                    <span key={j} className="rounded-full bg-brand-50 px-2.5 py-0.5 text-xs font-medium text-brand-700 ring-1 ring-brand-200">
                      {d}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {cat.evidence.length > 0 && (
              <div className="mt-3">
                <p className="mb-1.5 text-xs font-semibold uppercase tracking-wider text-slate-400">Suggested Items</p>
                <div className="flex flex-wrap gap-1.5">
                  {cat.evidence.map((item, j) => (
                    <span key={j} className="rounded-lg bg-slate-100 px-2.5 py-1 text-xs text-slate-700">
                      {item}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {cat.source && (
              <p className="mt-auto pt-4 text-xs text-slate-300">Source: {cat.source}</p>
            )}
          </div>
        ))}
      </div>

      <p className="mt-4 text-xs text-slate-400">{data.categories.length} categories</p>
    </div>
  );
}

const TRADITION_BADGE: Record<string, string> = {
  jewish: 'bg-blue-100 text-blue-700',
  islamic: 'bg-green-100 text-green-700',
  christian: 'bg-violet-100 text-violet-700',
  hindu: 'bg-orange-100 text-orange-700',
  sikh: 'bg-amber-100 text-amber-700',
  community: 'bg-slate-100 text-slate-600',
};

// ─── Step 2: Holiday Calendar ─────────────────────────────────────────────────

function HolidayCalendarStep({ data }: { data: Agent3Output }) {
  return (
    <div>
      <p className="text-xs font-semibold uppercase tracking-widest text-brand-600">Holiday Demand Calendar</p>
      <h2 className="mt-1 text-2xl font-bold text-slate-900">Demand Signals</h2>
      <p className="mt-1 text-sm text-slate-500">
        {data.events.length} upcoming events in a {data.horizon_days}-day window · {data.location}
      </p>

      <div className="mt-6 space-y-3">
        {data.events.map((e, i) => (
          <div key={i} className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
            <div className="flex flex-wrap items-start gap-3">
              {/* Days-until badge */}
              <div className="flex w-14 shrink-0 flex-col items-center justify-center rounded-lg border border-slate-100 bg-slate-50 py-2">
                <p className="text-xs font-medium text-slate-400">In</p>
                <p className="text-xl font-bold text-slate-800">{e.days_until}d</p>
              </div>

              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="text-sm font-bold text-slate-800">{e.holiday}</p>
                  <span className={`rounded-full px-2 py-0.5 text-xs font-medium capitalize ${TRADITION_BADGE[e.tradition] ?? TRADITION_BADGE.community}`}>
                    {e.tradition}
                  </span>
                  <span className="rounded-full bg-brand-100 px-2 py-0.5 text-xs font-medium text-brand-700 ring-1 ring-brand-200">
                    {e.estimated_demand_multiplier.toFixed(2)}× demand
                  </span>
                  <span className="text-xs text-slate-400">{Math.round(e.relevant_population_pct)}% of area</span>
                </div>

                <p className="mt-1 text-xs text-slate-500">{e.demographic_rationale || e.stock_up_window}</p>

                {e.expected_demand_categories.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {e.expected_demand_categories.map((c, j) => (
                      <span key={j} className="rounded-lg bg-slate-100 px-2 py-0.5 text-xs text-slate-600">{c}</span>
                    ))}
                  </div>
                )}

                <p className="mt-2 text-xs text-slate-300">
                  {e.start_date} → {e.end_date} · Stock up: {e.stock_up_window}
                </p>
              </div>
            </div>
          </div>
        ))}
      </div>

      {data.data_gaps.length > 0 && (
        <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-3">
          <p className="mb-1 text-xs font-semibold text-amber-700">Data gaps</p>
          <ul className="space-y-0.5">
            {data.data_gaps.map((g, i) => <li key={i} className="text-xs text-amber-600">{g}</li>)}
          </ul>
        </div>
      )}
    </div>
  );
}

// ─── Step 3: Vendor Recommendations ──────────────────────────────────────────

function VendorStep({ data }: { data: Agent4Output }) {
  return (
    <div>
      <p className="text-xs font-semibold uppercase tracking-widest text-brand-600">
        Vendor &amp; Inventory Recommender
      </p>
      <h2 className="mt-1 text-2xl font-bold text-slate-900">Vendor Recommendations</h2>
      <p className="mt-1 text-sm text-slate-500">
        Top picks based on your neighborhood profile and product mix.
      </p>

      <div className="mt-6 grid gap-4 sm:grid-cols-2">
        {data.recommendations.map((v, i) => (
          <div key={i} className="flex flex-col rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="flex items-start justify-between gap-2">
              <p className="text-sm font-bold text-slate-800">{v.product}</p>
              <span className="shrink-0 rounded-full bg-brand-50 px-2 py-0.5 text-xs font-semibold text-brand-700">
                {v.margin_pct.toFixed(0)}% margin
              </span>
            </div>

            <p className="mt-1 text-xs leading-relaxed text-slate-500">{v.rationale}</p>

            <div className="mt-4 space-y-1.5 text-xs text-slate-600">
              <div className="flex justify-between">
                <span className="text-slate-400">Vendor</span>
                {v.vendor_url ? (
                  <a href={v.vendor_url} target="_blank" rel="noopener noreferrer" className="font-medium text-brand-600 underline underline-offset-2">
                    {v.suggested_vendor}
                  </a>
                ) : (
                  <span className="font-medium">{v.suggested_vendor}</span>
                )}
              </div>
              {v.vendor_address && (
                <div className="flex justify-between gap-4">
                  <span className="text-slate-400 shrink-0">Address</span>
                  <span className="text-right">{v.vendor_address}</span>
                </div>
              )}
              <div className="flex justify-between">
                <span className="text-slate-400">Unit cost</span>
                <span className="font-medium">${v.wholesale_cost_estimate.toFixed(2)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Retail price</span>
                <span className="font-medium">${v.suggested_retail_price.toFixed(2)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Reorder at</span>
                <span className="font-medium">{v.reorder_trigger_units} units</span>
              </div>
              {v.vendor_unit_price && (
                <div className="flex justify-between">
                  <span className="text-slate-400">Vendor unit price</span>
                  <span className="font-medium">${v.vendor_unit_price.toFixed(2)}{v.vendor_quantity ? ` / ${v.vendor_quantity}` : ''}</span>
                </div>
              )}
            </div>

            <p className="mt-auto pt-3 text-xs text-slate-300">Source: {v.data_source}</p>
          </div>
        ))}
      </div>

      <div className="mt-6 rounded-xl border border-brand-200 bg-brand-50 p-5">
        <div className="flex items-start gap-3">
          <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-brand-600 text-white">
            <svg className="h-4 w-4" viewBox="0 0 16 16" fill="none">
              <path d="M3 8l4 4 6-6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          </span>
          <div className="flex-1">
            <p className="text-sm font-bold text-slate-900">Report saved — ready to chat</p>
            <p className="mt-0.5 text-sm text-slate-500">
              Your report has been saved. Ask follow-up questions, explore vendor options, or dig into holiday demand.
            </p>
            <div className="mt-4 flex flex-wrap gap-3">
              <Link
                href="/chat"
                className="rounded-full bg-brand-600 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-brand-700"
              >
                Chat with your report &rarr;
              </Link>
              <Link
                href="/vendor/dashboard"
                className="rounded-full border border-slate-200 px-4 py-2 text-sm font-medium text-slate-600 transition-colors hover:text-slate-900"
              >
                &larr; Back to Dashboard
              </Link>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── Loading Animation ────────────────────────────────────────────────────────

// ─── Main Wizard ──────────────────────────────────────────────────────────────

const steps = [
  { id: 0, label: 'Demographics' },
  { id: 1, label: 'Product Mix' },
  { id: 2, label: 'Holiday Calendar' },
  { id: 3, label: 'Vendor Picks' },
];

function WizardInner() {
  const params = useSearchParams();
  const [step, setStep] = useState(0);
  const [store, setStore] = useState<StoreInfo>({ name: '', zip: '', type: '' });
  const [agent1Data, setAgent1Data] = useState<Agent1Output | null>(null);
  const [agent2Data, setAgent2Data] = useState<Agent2Output | null>(null);
  const [agent3Data, setAgent3Data] = useState<Agent3Output | null>(null);
  const [agent4Data, setAgent4Data] = useState<Agent4Output | null>(null);
  const [runningAgent1, setRunningAgent1] = useState(false);
  const [runningAgent2, setRunningAgent2] = useState(false);
  const [runningAgent3, setRunningAgent3] = useState(false);
  const [runningAgent4, setRunningAgent4] = useState(false);
  const [progressHistory, setProgressHistory] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);

  const maxUnlocked = agent4Data ? 3 : agent3Data ? 2 : agent2Data ? 1 : agent1Data ? 0 : -1;
  const agent1Triggered = useRef(false);
  const sessionId = useRef<string>(
    typeof crypto !== 'undefined' ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`
  );

  useEffect(() => {
    const name = params.get('store');
    const zip = params.get('zip');
    const type = params.get('type');
    if (name && zip) {
      setStore({ name, zip, type: type ?? '' });
    }
  }, [params]);

  const startProgress = () => { setProgressHistory([]); };
  const updateProgress = (msg: string) => { setProgressHistory((prev) => [...prev, msg]); };
  const clearProgress = () => { setProgressHistory([]); };

  const saveChunks = (agent: 'agent1' | 'agent2' | 'agent3' | 'agent4', data: Agent1Output | Agent2Output | Agent3Output | Agent4Output) => {
    saveAgentChunks({ session_id: sessionId.current, zip: store.zip, store_name: store.name, agent, data }).catch(console.error);
  };

  useEffect(() => {
    if (!store.zip || agent1Data || error || agent1Triggered.current) return;
    agent1Triggered.current = true;
    setRunningAgent1(true);
    startProgress();
    runAgentViaWS<Agent1Output>('/ws/agents/1', { zip_code: store.zip }, updateProgress)
      .then((data) => {
        setAgent1Data(data);
        saveChunks('agent1', data);
        localStorage.setItem('bodega_last_session', sessionId.current);
        localStorage.setItem('bodega_last_store', JSON.stringify({ name: store.name, zip: store.zip }));
      })
      .catch((err: Error) => {
        setError(err.message);
        agent1Triggered.current = false;
      })
      .finally(() => { setRunningAgent1(false); clearProgress(); });
  }, [store.zip, agent1Data, error]);

  const runAgent2Handler = () => {
    if (agent1Data && !runningAgent2) {
      setRunningAgent2(true);
      startProgress();
      runAgentViaWS<Agent2Output>('/ws/agents/2', { profile: agent1Data }, updateProgress)
        .then((data) => { setAgent2Data(data); setStep(1); saveChunks('agent2', data); })
        .catch((err: Error) => setError(err.message))
        .finally(() => { setRunningAgent2(false); clearProgress(); });
    }
  };

  const runAgent3Handler = () => {
    if (agent1Data && !runningAgent3) {
      setRunningAgent3(true);
      startProgress();
      runAgentViaWS<Agent3Output>('/ws/agents/3', { profile: agent1Data }, updateProgress)
        .then((data) => { setAgent3Data(data); setStep(2); saveChunks('agent3', data); })
        .catch((err: Error) => setError(err.message))
        .finally(() => { setRunningAgent3(false); clearProgress(); });
    }
  };

  const runAgent4Handler = () => {
    if (agent2Data && agent3Data && !runningAgent4) {
      setRunningAgent4(true);
      startProgress();
      runAgentViaWS<Agent4Output>(
        '/ws/agents/4',
        {
          categories: agent2Data.categories.map((c) => ({ ...c, score: 1.0 })),
          holidays: agent3Data.events.map((e) => ({ holiday: e.holiday, demand_multiplier: e.estimated_demand_multiplier })),
          location_zip: store.zip,
        },
        updateProgress,
      )
        .then((data) => { setAgent4Data(data); setStep(3); saveChunks('agent4', data); })
        .catch((err: Error) => setError(err.message))
        .finally(() => { setRunningAgent4(false); clearProgress(); });
    }
  };

  const hasStore = store.name && store.zip;

  const anyRunning = runningAgent1 || runningAgent2 || runningAgent3 || runningAgent4;

  function AgentLoader({ label, agentNum, totalSteps }: { label: string; agentNum: number; totalSteps: number }) {
    const completedSteps = progressHistory.slice(0, -1);
    const currentStep = progressHistory[progressHistory.length - 1] ?? null;
    const pct = progressHistory.length === 0
      ? 4
      : Math.min(94, Math.round((progressHistory.length / totalSteps) * 100));

    return (
      <div className="mx-auto max-w-lg py-14">
        {/* Header */}
        <div className="flex items-center gap-3 mb-6">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-brand-600 text-xs font-bold text-white">
            {String(agentNum).padStart(2, '0')}
          </div>
          <div>
            <p className="text-xs font-semibold uppercase tracking-widest text-brand-600">{label}</p>
            <p className="text-base font-bold text-slate-900 leading-tight">{store.name}</p>
            <p className="text-xs text-slate-400">ZIP {store.zip} &middot; {store.type}</p>
          </div>
        </div>

        {/* Progress bar */}
        <div className="mb-6">
          <div className="mb-1.5 flex items-center justify-between text-xs text-slate-400">
            <span>{pct}% complete</span>
            <span>{progressHistory.length} / {totalSteps} steps</span>
          </div>
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-100">
            <div
              className="h-full rounded-full bg-brand-500 transition-all duration-700 ease-out"
              style={{ width: `${pct}%` }}
            />
          </div>
        </div>

        {/* Step list */}
        <div className="space-y-2.5">
          {completedSteps.map((msg, i) => (
            <div key={i} className="flex items-center gap-3">
              <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-brand-100 text-brand-600">
                <svg className="h-3 w-3" viewBox="0 0 12 12" fill="none">
                  <path d="M2 6l3 3 5-5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
              </span>
              <span className="text-sm text-slate-400">{msg}</span>
            </div>
          ))}
          {currentStep ? (
            <div className="flex items-center gap-3">
              <span className="flex h-5 w-5 shrink-0 items-center justify-center">
                <span className="h-2 w-2 animate-pulse rounded-full bg-brand-500" />
              </span>
              <span className="text-sm font-semibold text-brand-700">{currentStep}</span>
            </div>
          ) : (
            <div className="flex items-center gap-3">
              <span className="flex h-5 w-5 shrink-0 items-center justify-center">
                <span className="h-2 w-2 animate-pulse rounded-full bg-brand-400" />
              </span>
              <span className="text-sm text-slate-400">Connecting…</span>
            </div>
          )}
        </div>
      </div>
    );
  }

  function NextButton({ label, onClick, running, disabled }: { label: string; onClick: () => void; running: boolean; disabled?: boolean }) {
    return (
      <div className="mt-6 flex justify-center">
        <button
          onClick={onClick}
          disabled={running || disabled}
          className="rounded-full bg-brand-600 px-6 py-3 text-sm font-semibold text-white hover:bg-brand-700 disabled:opacity-50"
        >
          {running ? `Running ${label}…` : `Run ${label}`}
        </button>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-50 px-6 py-10">
      <div className="mx-auto max-w-4xl">
        {/* Step indicator */}
        <div className="mb-10 flex items-center">
          {steps.map((s, i) => (
            <div key={s.id} className="flex flex-1 items-center">
              <button
                onClick={() => s.id <= maxUnlocked && setStep(s.id)}
                disabled={s.id > maxUnlocked || s.id === step}
                className="flex flex-col items-center gap-1.5 disabled:cursor-default"
              >
                <span
                  className={`flex h-8 w-8 items-center justify-center rounded-full text-xs font-bold transition-all ${
                    s.id < step ? 'bg-brand-600 text-white'
                    : s.id === step ? 'bg-brand-50 text-brand-600 ring-2 ring-brand-500'
                    : 'bg-white text-slate-300 ring-1 ring-slate-200'
                  }`}
                >
                  {s.id < step ? '✓' : s.id + 1}
                </span>
                <span className={`hidden text-xs font-medium sm:block ${s.id === step ? 'text-brand-600' : s.id < step ? 'text-slate-500' : 'text-slate-300'}`}>
                  {s.label}
                </span>
              </button>
              {i < steps.length - 1 && (
                <div className={`mx-2 h-px flex-1 ${s.id < step ? 'bg-brand-300' : 'bg-slate-200'}`} />
              )}
            </div>
          ))}
        </div>

        {/* No store selected */}
        {!hasStore && (
          <div className="flex flex-col items-center py-16 text-center">
            <p className="text-slate-500">No store selected.</p>
            <Link href="/vendor/dashboard" className="mt-4 rounded-full bg-brand-600 px-5 py-2 text-sm font-semibold text-white hover:bg-brand-700">
              Go to Dashboard
            </Link>
          </div>
        )}

        {/* Error state */}
        {error && (
          <div className="rounded-xl border border-red-200 bg-red-50 p-6 text-center">
            <p className="font-semibold text-red-700">Could not load data</p>
            <p className="mt-1 text-sm text-slate-500">{error}</p>
            <div className="mt-4 flex justify-center gap-3">
              <button
                onClick={() => { setError(null); setAgent1Data(null); setAgent2Data(null); setAgent3Data(null); setAgent4Data(null); }}
                className="rounded-full bg-brand-600 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-700"
              >
                Retry
              </button>
              <Link href="/vendor/dashboard" className="rounded-full border border-slate-200 px-4 py-2 text-sm font-medium text-slate-600 hover:text-slate-900">
                Back to Dashboard
              </Link>
            </div>
          </div>
        )}

        {/* Step content */}
        <div className="min-h-96">
          {runningAgent1 && <AgentLoader label="Profiling demographics" agentNum={1} totalSteps={4} />}

          {!anyRunning && !error && agent1Data && step === 0 && (
            <div>
              <DemographicsStep data={agent1Data} />
              <NextButton label="Buying Behavior Suggester" onClick={runAgent2Handler} running={runningAgent2} />
            </div>
          )}

          {runningAgent2 && <AgentLoader label="Analyzing product mix" agentNum={2} totalSteps={4} />}

          {!anyRunning && !error && agent2Data && agent1Data && step === 1 && (
            <div>
              <ProductMixStep data={agent2Data} profile={agent1Data} />
              <NextButton label="Holiday Demand Calendar" onClick={runAgent3Handler} running={runningAgent3} />
            </div>
          )}

          {runningAgent3 && <AgentLoader label="Building holiday calendar" agentNum={3} totalSteps={5} />}

          {!anyRunning && !error && agent3Data && step === 2 && (
            <div>
              <HolidayCalendarStep data={agent3Data} />
              <NextButton label="Vendor & Inventory Recommender" onClick={runAgent4Handler} running={runningAgent4} />
            </div>
          )}

          {runningAgent4 && <AgentLoader label="Sourcing vendor picks" agentNum={4} totalSteps={3} />}

          {!anyRunning && !error && agent4Data && step === 3 && (
            <VendorStep data={agent4Data} />
          )}
        </div>
      </div>
    </div>
  );
}

export default function WizardPage() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-slate-50" />}>
      <WizardInner />
    </Suspense>
  );
}
