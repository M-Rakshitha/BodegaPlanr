'use client';
import { useState, useEffect, useCallback, Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { runOrchestration, type OrchestratedReport, runAgent1, runAgent2, type Agent1Output, type Agent2Output } from '@/lib/api';

type StoreInfo = { name: string; zip: string; type: string };

const RACE_COLORS: Record<string, string> = {
  'Hispanic or Latino (any race)': 'bg-brand-500',
  'Black or African American alone': 'bg-violet-500',
  'White alone': 'bg-blue-400',
  'Asian alone': 'bg-amber-400',
  'Two or more races': 'bg-rose-400',
  'American Indian and Alaska Native alone': 'bg-orange-400',
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
        <p className="text-xs font-semibold uppercase tracking-widest text-brand-600">Agent 01 — Demographic Profiler</p>
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
            Powered by Census ACS 2023 · Agent 01
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
      <p className="text-xs font-semibold uppercase tracking-widest text-brand-600">Agent 02 — Buying Behavior Suggester</p>
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

// ─── Step 2: Holiday Calendar ─────────────────────────────────────────────────

function HolidayCalendarStep({ data }: { data: OrchestratedReport['agent3'] }) {
  return (
    <div>
      <p className="text-xs font-semibold uppercase tracking-widest text-brand-600">Agent 03 — Holiday Calendar</p>
      <h2 className="mt-1 text-2xl font-bold text-slate-900">Demand Signals</h2>
      <p className="mt-1 text-sm text-slate-500">
        Upcoming events with stocking recommendations. Stock up before each prep window closes.
      </p>

      <div className="mt-6 space-y-3">
        {data.upcoming_signals.map((s, i) => (
          <div key={i} className="flex gap-4 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
            <div className="flex w-14 shrink-0 flex-col items-center justify-center rounded-lg border border-slate-100 bg-slate-50 py-2">
              <p className="text-xs font-medium text-slate-400">Prep</p>
              <p className="text-xl font-bold text-slate-800">{s.start_window_days}d</p>
            </div>
            <div className="flex min-w-0 flex-1 flex-col justify-center gap-1">
              <div className="flex flex-wrap items-center gap-2">
                <p className="text-sm font-semibold text-slate-800">{s.holiday}</p>
                <span className="rounded-full bg-brand-100 px-2 py-0.5 text-xs font-medium text-brand-700 ring-1 ring-brand-200">
                  {s.demand_multiplier.toFixed(2)}× demand
                </span>
              </div>
              <p className="text-xs text-slate-500">{s.rationale}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── Step 3: Vendor Recommendations ──────────────────────────────────────────

function VendorStep({ data }: { data: OrchestratedReport['agent4'] }) {
  return (
    <div>
      <p className="text-xs font-semibold uppercase tracking-widest text-brand-600">
        Agent 04 — Vendor & Inventory Recommender
      </p>
      <div className="mt-1 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-2xl font-bold text-slate-900">Vendor Recommendations</h2>
          <p className="mt-1 text-sm text-slate-500">
            Top picks based on your neighborhood profile and product mix.
          </p>
        </div>
      </div>

      <div className="mt-5 overflow-x-auto rounded-xl border border-slate-200 shadow-sm">
        <table className="w-full text-sm">
          <thead className="border-b border-slate-200 bg-slate-50">
            <tr>
              {['Product Category', 'Suggested Vendor', 'Unit Cost', 'Retail Price', 'Margin', 'Reorder At'].map((h) => (
                <th key={h} className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-400">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 bg-white">
            {data.recommendations.map((v, i) => (
              <tr key={i} className="transition-colors hover:bg-slate-50">
                <td className="px-4 py-3 font-medium text-slate-800">{v.product}</td>
                <td className="px-4 py-3 text-slate-500">{v.suggested_vendor}</td>
                <td className="px-4 py-3 text-slate-700">${v.wholesale_cost_estimate.toFixed(2)}</td>
                <td className="px-4 py-3 text-slate-700">${v.suggested_retail_price.toFixed(2)}</td>
                <td className="px-4 py-3">
                  <span className="rounded-full bg-brand-50 px-2 py-0.5 text-xs font-semibold text-brand-700">
                    {v.margin_pct.toFixed(0)}%
                  </span>
                </td>
                <td className="px-4 py-3 text-slate-500">{v.reorder_trigger_units} units</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="mt-4 rounded-xl border border-brand-200 bg-brand-50 p-4">
        <p className="mb-1 text-xs font-semibold uppercase tracking-wider text-brand-700">Report Complete</p>
        <p className="text-sm leading-relaxed text-slate-700">
          Report generated from live Census data and AI-driven demand analysis. Contact your local
          wholesaler with these recommendations.
        </p>
        <div className="mt-3 flex flex-wrap gap-3">
          <Link
            href="/vendor/dashboard"
            className="rounded-full border border-brand-300 px-3 py-1.5 text-xs font-medium text-brand-700 transition-colors hover:bg-brand-100"
          >
            &larr; Back to Dashboard
          </Link>
          <Link
            href="/chat"
            className="rounded-full border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-600 transition-colors hover:text-slate-900"
          >
            Ask Questions in Chat &rarr;
          </Link>
        </div>
      </div>
    </div>
  );
}

// ─── Loading Animation ────────────────────────────────────────────────────────

const autoLoadingSteps = [
  'Fetching Census demographic data...',
  'Loading ARDA religious community data...',
  'Computing CEX buying behavior scores...',
  'Building demand signals and vendor list...',
];

function AutoRunLoader({
  store,
  onDone,
  onError,
}: {
  store: StoreInfo;
  onDone: (report: OrchestratedReport) => void;
  onError: (err: string) => void;
}) {
  const [progress, setProgress] = useState(0);

  useEffect(() => {
    let cancelled = false;

    const apiPromise = runOrchestration(store.zip);

    let i = 0;
    const interval = setInterval(() => {
      i++;
      if (i < autoLoadingSteps.length) setProgress(i);
    }, 900);

    apiPromise
      .then((report) => {
        if (!cancelled) {
          clearInterval(interval);
          setProgress(autoLoadingSteps.length);
          setTimeout(() => onDone(report), 400);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          clearInterval(interval);
          onError(err instanceof Error ? err.message : 'Failed to fetch report');
        }
      });

    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [store.zip, onDone, onError]);

  return (
    <div className="mx-auto max-w-md py-16">
      <p className="text-sm font-semibold text-slate-500">Running analysis for</p>
      <h2 className="mt-1 text-2xl font-bold text-slate-900">{store.name}</h2>
      <p className="mt-0.5 text-sm text-slate-400">
        ZIP {store.zip} &middot; {store.type}
      </p>
      <div className="mt-8 space-y-3">
        {autoLoadingSteps.map((msg, i) => (
          <div
            key={i}
            className={`flex items-center gap-3 text-sm transition-all duration-300 ${
              i < progress ? 'text-brand-600' : 'text-slate-300'
            }`}
          >
            <span
              className={`h-1.5 w-1.5 shrink-0 rounded-full ${i < progress ? 'bg-brand-500' : 'bg-slate-200'}`}
            />
            {msg}
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── Main Wizard ──────────────────────────────────────────────────────────────

const steps = [
  { id: 0, label: 'Demographics' },
  { id: 1, label: 'Product Mix' },
];

function WizardInner() {
  const params = useSearchParams();
  const [step, setStep] = useState(0);
  const [store, setStore] = useState<StoreInfo>({ name: '', zip: '', type: '' });
  const [agent1Data, setAgent1Data] = useState<Agent1Output | null>(null);
  const [agent2Data, setAgent2Data] = useState<Agent2Output | null>(null);
  const [runningAgent1, setRunningAgent1] = useState(false);
  const [runningAgent2, setRunningAgent2] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const name = params.get('store');
    const zip = params.get('zip');
    const type = params.get('type');
    if (name && zip) {
      setStore({ name, zip, type: type ?? '' });
    }
  }, [params]);

  useEffect(() => {
    if (store.zip && !agent1Data && !runningAgent1 && !error) {
      setRunningAgent1(true);
      runAgent1(store.zip)
        .then(setAgent1Data)
        .catch(err => setError(err.message))
        .finally(() => setRunningAgent1(false));
    }
  }, [store.zip, agent1Data, runningAgent1, error]);

  const runAgent2Handler = () => {
    if (agent1Data && !runningAgent2) {
      setRunningAgent2(true);
      runAgent2(agent1Data)
        .then((data) => { setAgent2Data(data); setStep(1); })
        .catch(err => setError(err.message))
        .finally(() => setRunningAgent2(false));
    }
  };

  const hasStore = store.name && store.zip;

  return (
    <div className="min-h-screen bg-slate-50 px-6 py-10">
      <div className="mx-auto max-w-4xl">
        {/* Step indicator */}
        <div className="mb-10 flex items-center">
          {steps.map((s, i) => (
            <div key={s.id} className="flex flex-1 items-center">
              <button
                onClick={() => (agent1Data && s.id <= (agent2Data ? 1 : 0)) && setStep(s.id)}
                disabled={!(agent1Data && s.id <= (agent2Data ? 1 : 0)) || s.id === step}
                className="flex flex-col items-center gap-1.5 disabled:cursor-default"
              >
                <span
                  className={`flex h-8 w-8 items-center justify-center rounded-full text-xs font-bold transition-all ${
                    s.id < step
                      ? 'bg-brand-600 text-white'
                      : s.id === step
                      ? 'bg-brand-50 text-brand-600 ring-2 ring-brand-500'
                      : 'bg-white text-slate-300 ring-1 ring-slate-200'
                  }`}
                >
                  {s.id < step ? '✓' : s.id + 1}
                </span>
                <span
                  className={`hidden text-xs font-medium sm:block ${
                    s.id === step ? 'text-brand-600' : s.id < step ? 'text-slate-500' : 'text-slate-300'
                  }`}
                >
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
            <Link
              href="/vendor/dashboard"
              className="mt-4 rounded-full bg-brand-600 px-5 py-2 text-sm font-semibold text-white hover:bg-brand-700"
            >
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
                onClick={() => {
                  setError(null);
                  setAgent1Data(null);
                  setAgent2Data(null);
                }}
                className="rounded-full bg-brand-600 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-700"
              >
                Retry
              </button>
              <Link
                href="/vendor/dashboard"
                className="rounded-full border border-slate-200 px-4 py-2 text-sm font-medium text-slate-600 hover:text-slate-900"
              >
                Back to Dashboard
              </Link>
            </div>
          </div>
        )}

        {/* Step content */}
        <div className="min-h-96">
          {runningAgent1 && (
            <div className="mx-auto max-w-md py-16">
              <p className="text-sm font-semibold text-slate-500">Running Agent 1 for</p>
              <h2 className="mt-1 text-2xl font-bold text-slate-900">{store.name}</h2>
              <p className="mt-0.5 text-sm text-slate-400">
                ZIP {store.zip} &middot; {store.type}
              </p>
              <div className="mt-8 space-y-3">
                <div className="flex items-center gap-3 text-sm text-brand-600">
                  <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-brand-500" />
                  Fetching Census demographic data...
                </div>
              </div>
            </div>
          )}
          {!runningAgent1 && !error && agent1Data && step === 0 && (
            <div>
              <DemographicsStep data={agent1Data} />
              <div className="mt-6 flex justify-center">
                <button
                  onClick={runAgent2Handler}
                  disabled={runningAgent2}
                  className="rounded-full bg-brand-600 px-6 py-3 text-sm font-semibold text-white hover:bg-brand-700 disabled:opacity-50"
                >
                  {runningAgent2 ? 'Running Agent 2...' : 'Run Agent 2'}
                </button>
              </div>
            </div>
          )}
          {runningAgent2 && (
            <div className="mx-auto max-w-md py-16">
              <p className="text-sm font-semibold text-slate-500">Running Agent 2 for</p>
              <h2 className="mt-1 text-2xl font-bold text-slate-900">{store.name}</h2>
              <p className="mt-0.5 text-sm text-slate-400">
                ZIP {store.zip} &middot; {store.type}
              </p>
              <div className="mt-8 space-y-3">
                <div className="flex items-center gap-3 text-sm text-brand-600">
                  <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-brand-500" />
                  Loading CEX buying behavior scores...
                </div>
              </div>
            </div>
          )}
          {!runningAgent2 && !error && agent2Data && agent1Data && step === 1 && <ProductMixStep data={agent2Data} profile={agent1Data} />}
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
