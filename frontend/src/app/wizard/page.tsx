'use client';
import { useState, useEffect, Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import Link from 'next/link';

// ─── Types ───────────────────────────────────────────────────────────────────

type StoreInfo = { name: string; zip: string; type: string };

// ─── Mock Data ────────────────────────────────────────────────────────────────

const demographics = {
  zip: '10031',
  neighborhood: 'Hamilton Heights / Harlem',
  city: 'New York, NY',
  totalPop: 47234,
  medianAge: 33.1,
  medianIncome: 38500,
  avgHouseholdSize: 2.8,
  belowPoverty: 28.3,
  renters: 89.1,
  ethnicity: [
    { label: 'Hispanic / Latino', pct: 52, color: 'bg-green-500' },
    { label: 'Black / African American', pct: 30, color: 'bg-violet-500' },
    { label: 'White', pct: 11, color: 'bg-blue-400' },
    { label: 'Asian', pct: 4, color: 'bg-amber-400' },
    { label: 'Other', pct: 3, color: 'bg-slate-300' },
  ],
  religions: [
    { label: 'Baptist / Pentecostal', count: 14, bg: 'bg-blue-50 text-blue-700' },
    { label: 'Catholic', count: 6, bg: 'bg-indigo-50 text-indigo-700' },
    { label: 'Muslim', count: 4, bg: 'bg-emerald-50 text-emerald-700' },
    { label: 'Jewish', count: 1, bg: 'bg-amber-50 text-amber-700' },
  ],
};

const categories = [
  { id: 'beverages', label: 'Beverages', sub: 'Soda, water, juices, energy drinks', score: 96, reason: 'High foot traffic + large young adult population' },
  { id: 'snacks', label: 'Snacks & Chips', sub: 'Chips, crackers, candy, nuts', score: 91, reason: 'Top CEX spend category for urban low-income households' },
  { id: 'latin', label: 'Latin / Caribbean Foods', sub: 'Goya, sofrito, sazón, plantains', score: 88, reason: '52% Hispanic population — high cultural affinity' },
  { id: 'personal', label: 'Personal Care', sub: 'Hair, skin, grooming products', score: 82, reason: 'Limited nearby drugstores; customers pay convenience premium' },
  { id: 'prepared', label: 'Prepared Foods', sub: 'Sandwiches, hot food, deli items', score: 79, reason: 'Strong morning commuter traffic; single-person households' },
  { id: 'household', label: 'Household Supplies', sub: 'Cleaning, laundry, paper goods', score: 74, reason: 'High renter density; limited storage = small-pack preference' },
  { id: 'dairy', label: 'Dairy & Eggs', sub: 'Milk, eggs, cheese, yogurt', score: 71, reason: 'Essential staple with few nearby grocery options' },
  { id: 'produce', label: 'Fresh Produce', sub: 'Fruit, vegetables, herbs', score: 63, reason: 'Food desert proximity; requires refrigeration investment' },
];

const holidays = [
  { date: '2026-04-19', name: 'Easter Sunday', type: 'Christian', prep: 'Stock: candy, chocolate, baked goods, flowers, ham' },
  { date: '2026-04-23', name: 'Passover Ends', type: 'Jewish', prep: 'Stock: kosher items, matzo, grape juice' },
  { date: '2026-04-27', name: 'Eid al-Fitr', type: 'Muslim', prep: 'Stock: dates, sweets, greeting cards, halal confections' },
  { date: '2026-05-10', name: "Mother's Day", type: 'Civic', prep: 'Stock: flowers, candy, greeting cards, gift wrap' },
  { date: '2026-05-25', name: 'Memorial Day', type: 'Civic', prep: 'Stock: BBQ supplies, beverages, snacks, ice, chips' },
  { date: '2026-06-15', name: 'Eid al-Adha', type: 'Muslim', prep: 'Stock: sweets, gifts, celebratory items' },
  { date: '2026-06-19', name: 'Juneteenth', type: 'Civic', prep: 'Stock: BBQ essentials, strawberry soda, red drinks' },
  { date: '2026-07-04', name: 'Independence Day', type: 'Civic', prep: 'Stock: beverages, BBQ snacks, ice — heaviest volume day' },
  { date: '2026-07-05', name: 'Islamic New Year', type: 'Muslim', prep: 'Stock: dates, prayer items, halal sweets' },
];

const typeColors: Record<string, string> = {
  Christian: 'bg-blue-100 text-blue-700 ring-1 ring-blue-200',
  Jewish: 'bg-amber-100 text-amber-700 ring-1 ring-amber-200',
  Muslim: 'bg-emerald-100 text-emerald-700 ring-1 ring-emerald-200',
  Civic: 'bg-violet-100 text-violet-700 ring-1 ring-violet-200',
};

const vendors = [
  { product: 'Goya Coconut Water 11.8 oz', category: 'Beverages', vendor: 'Goya Foods', distributor: 'UNFI', unitCost: '$0.89', pack: '24-pk', score: 97 },
  { product: 'Goya Black Beans 15.5 oz', category: 'Latin Foods', vendor: 'Goya Foods', distributor: 'Direct', unitCost: '$0.72', pack: '24-pk', score: 95 },
  { product: 'Saazón Goya Seasoning', category: 'Latin Foods', vendor: 'Goya Foods', distributor: 'Direct', unitCost: '$1.29', pack: '36-pk', score: 93 },
  { product: 'Monster Energy 16 oz', category: 'Beverages', vendor: 'Monster Beverage', distributor: 'DSD', unitCost: '$1.05', pack: '24-pk', score: 91 },
  { product: "Lay's Classic Chips 1.5 oz", category: 'Snacks', vendor: 'Frito-Lay', distributor: 'DSD', unitCost: '$0.48', pack: '64-pk', score: 89 },
  { product: 'Bounty Paper Towels 2-pk', category: 'Household', vendor: 'Procter & Gamble', distributor: 'McLane', unitCost: '$2.10', pack: '15-pk', score: 82 },
  { product: 'Dove Soap Bar 3.75 oz', category: 'Personal Care', vendor: 'Unilever', distributor: 'UNFI', unitCost: '$1.15', pack: '12-pk', score: 80 },
  { product: 'Pantene Shampoo 12 oz', category: 'Personal Care', vendor: 'Procter & Gamble', distributor: 'McLane', unitCost: '$3.45', pack: '6-pk', score: 77 },
];

// ─── Step 0: Demographics ─────────────────────────────────────────────────────

function DemographicsStep({ store }: { store: StoreInfo }) {
  const d = demographics;
  const stats = [
    { label: 'Total Population', value: d.totalPop.toLocaleString() },
    { label: 'Median Household Income', value: `$${d.medianIncome.toLocaleString()}` },
    { label: 'Median Age', value: `${d.medianAge} yrs` },
    { label: 'Avg Household Size', value: `${d.avgHouseholdSize}` },
    { label: 'Below Poverty Line', value: `${d.belowPoverty}%` },
    { label: 'Renters', value: `${d.renters}%` },
  ];

  return (
    <div>
      <div className="mb-1">
        <p className="text-xs font-semibold uppercase tracking-widest text-green-600">Agent 01 — Demographic Profiler</p>
        <h2 className="mt-1 text-2xl font-bold text-slate-900">Demographics</h2>
        <p className="mt-1 text-sm text-slate-500">
          {store.name || 'Your Store'} &middot; ZIP {store.zip || d.zip} &middot; {d.neighborhood}, {d.city}
        </p>
      </div>

      <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        {stats.map((s) => (
          <div key={s.label} className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
            <p className="text-xl font-bold text-green-600">{s.value}</p>
            <p className="mt-0.5 text-xs leading-tight text-slate-500">{s.label}</p>
          </div>
        ))}
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <h3 className="mb-4 text-sm font-semibold text-slate-700">Ethnicity Breakdown</h3>
          <div className="space-y-3">
            {d.ethnicity.map((e) => (
              <div key={e.label}>
                <div className="mb-1 flex justify-between text-xs">
                  <span className="text-slate-500">{e.label}</span>
                  <span className="font-semibold text-slate-700">{e.pct}%</span>
                </div>
                <div className="h-1.5 overflow-hidden rounded-full bg-slate-100">
                  <div className={`h-full rounded-full ${e.color}`} style={{ width: `${e.pct}%` }} />
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <h3 className="mb-4 text-sm font-semibold text-slate-700">Religious Communities (ARDA)</h3>
          <div className="grid grid-cols-2 gap-3">
            {d.religions.map((r) => (
              <div key={r.label} className={`rounded-lg px-3 py-3 ${r.bg}`}>
                <p className="text-2xl font-bold">{r.count}</p>
                <p className="mt-0.5 text-xs leading-tight opacity-80">{r.label}</p>
              </div>
            ))}
          </div>
          <p className="mt-3 text-xs text-slate-400">Congregations within 1-mile radius</p>
        </div>
      </div>

      <div className="mt-4 rounded-xl border border-green-200 bg-green-50 p-4">
        <p className="mb-1 text-xs font-semibold uppercase tracking-wider text-green-700">Agent Insight</p>
        <p className="text-sm leading-relaxed text-slate-700">
          High Hispanic population (52%) with low median income ($38.5k) and very high renter rate (89%)
          suggests strong demand for culturally-specific foods, single-serve packaging, and value-oriented
          household staples. Four Muslim congregations nearby signal an opportunity for halal-certified products.
        </p>
      </div>
    </div>
  );
}

// ─── Step 2: Product Mix ──────────────────────────────────────────────────────

function ProductMixStep() {
  const [selected, setSelected] = useState<Set<string>>(
    new Set(categories.filter((c) => c.score >= 75).map((c) => c.id))
  );

  const toggle = (id: string) => {
    const next = new Set(selected);
    next.has(id) ? next.delete(id) : next.add(id);
    setSelected(next);
  };

  return (
    <div>
      <p className="text-xs font-semibold uppercase tracking-widest text-green-600">Agent 02 — Buying Behavior Suggester</p>
      <h2 className="mt-1 text-2xl font-bold text-slate-900">Product Mix</h2>
      <p className="mt-1 text-sm text-slate-500">
        AI-ranked categories based on your ZIP demographics and CEX data. Click to include or exclude.
      </p>

      <div className="mt-6 grid gap-3 sm:grid-cols-2">
        {[...categories].sort((a, b) => b.score - a.score).map((cat, i) => {
          const on = selected.has(cat.id);
          return (
            <button
              key={cat.id}
              onClick={() => toggle(cat.id)}
              className={`rounded-xl border p-4 text-left transition-all ${
                on
                  ? 'border-green-300 bg-green-50 shadow-sm'
                  : 'border-slate-200 bg-white opacity-50 hover:opacity-70'
              }`}
            >
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="w-5 shrink-0 text-xs text-slate-300">#{i + 1}</span>
                    <span className={`text-sm font-semibold ${on ? 'text-slate-800' : 'text-slate-400'}`}>
                      {cat.label}
                    </span>
                  </div>
                  <p className="mt-0.5 pl-7 text-xs text-slate-400">{cat.sub}</p>
                  <p className="mt-1.5 pl-7 text-xs leading-relaxed text-slate-400">{cat.reason}</p>
                </div>
                <div className="shrink-0 text-right">
                  <span className={`text-lg font-bold ${cat.score >= 85 ? 'text-green-600' : cat.score >= 75 ? 'text-slate-700' : 'text-slate-400'}`}>
                    {cat.score}
                  </span>
                  <p className="text-xs text-slate-300">score</p>
                </div>
              </div>
            </button>
          );
        })}
      </div>

      <p className="mt-4 text-xs text-slate-400">
        {selected.size} of {categories.length} categories selected &middot; Score = demand confidence from CEX + demographics
      </p>
    </div>
  );
}

// ─── Step 3: Holiday Calendar ─────────────────────────────────────────────────

function HolidayCalendarStep() {
  const formatDate = (iso: string) => {
    const [y, m, d] = iso.split('-').map(Number);
    const date = new Date(y, m - 1, d);
    return {
      month: date.toLocaleDateString('en-US', { month: 'short' }),
      day: date.getDate(),
    };
  };

  return (
    <div>
      <p className="text-xs font-semibold uppercase tracking-widest text-green-600">Agent 03 — Religious Holiday Calendar</p>
      <h2 className="mt-1 text-2xl font-bold text-slate-900">90-Day Holiday Calendar</h2>
      <p className="mt-1 text-sm text-slate-500">
        Upcoming events with stocking recommendations. Stock up 10–14 days before each date.
      </p>

      <div className="mt-6 space-y-3">
        {holidays.map((h) => {
          const { month, day } = formatDate(h.date);
          return (
            <div key={h.date} className="flex gap-4 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
              <div className="flex w-14 shrink-0 flex-col items-center justify-center rounded-lg bg-slate-50 py-2 border border-slate-100">
                <p className="text-xs font-medium text-slate-400">{month}</p>
                <p className="text-2xl font-bold text-slate-800">{day}</p>
              </div>
              <div className="flex min-w-0 flex-1 flex-col justify-center gap-1">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="text-sm font-semibold text-slate-800">{h.name}</p>
                  <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${typeColors[h.type]}`}>
                    {h.type}
                  </span>
                </div>
                <p className="text-xs text-slate-500">{h.prep}</p>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ─── Step 4: Vendor Recommendations ──────────────────────────────────────────

function VendorStep() {
  const [filter, setFilter] = useState('All');
  const allCats = ['All', ...Array.from(new Set(vendors.map((v) => v.category)))];
  const filtered = filter === 'All' ? vendors : vendors.filter((v) => v.category === filter);

  return (
    <div>
      <p className="text-xs font-semibold uppercase tracking-widest text-green-600">Agent 04 — Vendor & Inventory Recommender</p>
      <div className="mt-1 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-2xl font-bold text-slate-900">Vendor Recommendations</h2>
          <p className="mt-1 text-sm text-slate-500">Top SKU-level picks based on your neighborhood and selected categories.</p>
        </div>
        <button className="rounded-full bg-green-600 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-green-700">
          Export Report
        </button>
      </div>

      <div className="mt-5 flex flex-wrap gap-2">
        {allCats.map((cat) => (
          <button
            key={cat}
            onClick={() => setFilter(cat)}
            className={`rounded-full px-3 py-1 text-xs font-medium transition-all ${
              filter === cat
                ? 'bg-green-100 text-green-700 ring-1 ring-green-300'
                : 'bg-slate-100 text-slate-500 hover:text-slate-700'
            }`}
          >
            {cat}
          </button>
        ))}
      </div>

      <div className="mt-4 overflow-x-auto rounded-xl border border-slate-200 shadow-sm">
        <table className="w-full text-sm">
          <thead className="border-b border-slate-200 bg-slate-50">
            <tr>
              {['Product', 'Category', 'Vendor', 'Dist.', 'Unit Cost', 'Pack', 'Score'].map((h) => (
                <th key={h} className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-400">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 bg-white">
            {filtered.map((v, i) => (
              <tr key={i} className="transition-colors hover:bg-slate-50">
                <td className="px-4 py-3 font-medium text-slate-800">{v.product}</td>
                <td className="px-4 py-3 text-slate-500">{v.category}</td>
                <td className="px-4 py-3 text-slate-500">{v.vendor}</td>
                <td className="px-4 py-3">
                  <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-500">{v.distributor}</span>
                </td>
                <td className="px-4 py-3 text-slate-700">{v.unitCost}</td>
                <td className="px-4 py-3 text-slate-500">{v.pack}</td>
                <td className="px-4 py-3 font-bold">
                  <span className={v.score >= 90 ? 'text-green-600' : 'text-slate-600'}>{v.score}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="mt-4 rounded-xl border border-green-200 bg-green-50 p-4">
        <p className="mb-1 text-xs font-semibold uppercase tracking-wider text-green-700">Report Complete</p>
        <p className="text-sm leading-relaxed text-slate-700">
          This report has been saved to your account and is available for reference in the RAG Chat.
          You can export it as a PDF or share the vendor list directly with your distributor rep.
        </p>
        <div className="mt-3 flex flex-wrap gap-3">
          <button className="rounded-full border border-green-300 px-3 py-1.5 text-xs font-medium text-green-700 transition-colors hover:bg-green-100">
            Save Report
          </button>
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

// ─── Main Wizard ──────────────────────────────────────────────────────────────

const steps = [
  { id: 0, label: 'Demographics' },
  { id: 1, label: 'Product Mix' },
  { id: 2, label: 'Holidays' },
  { id: 3, label: 'Vendors' },
];

const autoLoadingSteps = [
  'Fetching Census data...',
  'Loading ARDA religious community data...',
  'Computing CEX buying behavior scores...',
  'Building 90-day holiday calendar...',
];

function AutoRunLoader({ store, onDone }: { store: StoreInfo; onDone: () => void }) {
  const [progress, setProgress] = useState(0);

  useEffect(() => {
    let i = 0;
    const interval = setInterval(() => {
      i++;
      setProgress(i);
      if (i >= autoLoadingSteps.length) {
        clearInterval(interval);
        setTimeout(onDone, 300);
      }
    }, 400);
    return () => clearInterval(interval);
  }, [onDone]);

  return (
    <div className="mx-auto max-w-md py-16">
      <p className="text-sm font-semibold text-slate-500">Running analysis for</p>
      <h2 className="mt-1 text-2xl font-bold text-slate-900">{store.name}</h2>
      <p className="mt-0.5 text-sm text-slate-400">ZIP {store.zip} &middot; {store.type}</p>
      <div className="mt-8 space-y-3">
        {autoLoadingSteps.map((msg, i) => (
          <div
            key={i}
            className={`flex items-center gap-3 text-sm transition-all duration-300 ${
              i < progress ? 'text-green-600' : 'text-slate-300'
            }`}
          >
            <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${i < progress ? 'bg-green-500' : 'bg-slate-200'}`} />
            {msg}
          </div>
        ))}
      </div>
    </div>
  );
}

function WizardInner() {
  const params = useSearchParams();
  const [step, setStep] = useState(0);
  const [store, setStore] = useState<StoreInfo>({ name: '', zip: '', type: '' });
  const [autoRunning, setAutoRunning] = useState(false);

  useEffect(() => {
    const name = params.get('store');
    const zip  = params.get('zip');
    const type = params.get('type');
    if (name && zip) {
      setStore({ name, zip, type: type ?? '' });
      setAutoRunning(true);
    }
  }, [params]);



  return (
    <div className="min-h-screen bg-slate-50 px-6 py-10">
      <div className="mx-auto max-w-4xl">
        {/* Step indicator */}
        <div className="mb-10 flex items-center">
          {steps.map((s, i) => (
            <div key={s.id} className="flex flex-1 items-center">
              <button
                onClick={() => step > 0 && s.id > 0 && setStep(s.id)}
                disabled={s.id === 0 || step === 0}
                className="flex flex-col items-center gap-1.5 disabled:cursor-default"
              >
                <span
                  className={`flex h-8 w-8 items-center justify-center rounded-full text-xs font-bold transition-all ${
                    s.id < step
                      ? 'bg-green-600 text-white'
                      : s.id === step
                      ? 'bg-green-50 text-green-600 ring-2 ring-green-500'
                      : 'bg-white text-slate-300 ring-1 ring-slate-200'
                  }`}
                >
                  {s.id < step ? '✓' : s.id + 1}
                </span>
                <span
                  className={`hidden text-xs font-medium sm:block ${
                    s.id === step ? 'text-green-600' : s.id < step ? 'text-slate-500' : 'text-slate-300'
                  }`}
                >
                  {s.label}
                </span>
              </button>
              {i < steps.length - 1 && (
                <div className={`mx-2 h-px flex-1 ${s.id < step ? 'bg-green-300' : 'bg-slate-200'}`} />
              )}
            </div>
          ))}
        </div>

        {/* Step content */}
        <div className="min-h-96">
          {autoRunning && (
            <AutoRunLoader store={store} onDone={() => { setAutoRunning(false); setStep(0); }} />
          )}
          {!autoRunning && step === 0 && <DemographicsStep store={store} />}
          {!autoRunning && step === 1 && <ProductMixStep />}
          {!autoRunning && step === 2 && <HolidayCalendarStep />}
          {!autoRunning && step === 3 && <VendorStep />}
        </div>

        {/* Back / Next */}
        {!autoRunning && (
          <div className="mt-8 flex justify-between border-t border-slate-200 pt-6">
            {step > 0 ? (
              <button
                onClick={() => setStep((s) => s - 1)}
                className="rounded-full border border-slate-200 px-5 py-2 text-sm font-medium text-slate-600 transition-colors hover:border-slate-300 hover:text-slate-900"
              >
                &larr; Back
              </button>
            ) : (
              <div />
            )}
            {step < 3 && (
              <button
                onClick={() => setStep((s) => s + 1)}
                className="rounded-full bg-green-600 px-5 py-2 text-sm font-semibold text-white transition-colors hover:bg-green-700"
              >
                Next: {steps[step + 1].label} &rarr;
              </button>
            )}
          </div>
        )}
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
