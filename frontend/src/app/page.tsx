'use client';
import Link from 'next/link';
import { useEffect } from 'react';
import { useRouter } from 'next/navigation';

const agents = [
  {
    num: '01',
    name: 'Demographic Profiler',
    description:
      'Census + ARDA data to understand who lives near your store — age, income, ethnicity, and religious community density.',
    sources: ['US Census', 'ARDA'],
  },
  {
    num: '02',
    name: 'Buying Behavior Suggester',
    description:
      'Consumer Expenditure Survey rules mapped to your neighborhood profile to rank product categories by expected demand.',
    sources: ['CEX', 'Curated Rules'],
  },
  {
    num: '03',
    name: 'Holiday Calendar',
    description:
      '90-day religious and civic holiday planning so you can time inventory purchases before demand spikes.',
    sources: ['Hebcal', 'Aladhan'],
  },
  {
    num: '04',
    name: 'Vendor Recommender',
    description:
      'SKU-level product and vendor matches with unit pricing and distributor info from major supply chains.',
    sources: ['RangeMe', 'Faire', 'UNFI'],
  },
];

const modes = [
  {
    href: '/wizard',
    label: 'Report Wizard',
    description:
      'Run all 4 agents for a store location. Enter a ZIP and get a full demographic profile, product mix, holiday calendar, and vendor list in minutes.',
    highlight: true,
  },
  {
    href: '/data',
    label: 'Customer Data Mode',
    description:
      'Upload CSV files of your sales history to track buying trends over time and surface what is growing or declining.',
    highlight: false,
  },
  {
    href: '/chat',
    label: 'RAG Chat',
    description:
      'Ask questions grounded in your saved reports. Answers cite your actual planning data — not generic AI knowledge.',
    highlight: false,
  },
];

export default function Home() {
  const router = useRouter();

  useEffect(() => {
    try {
      const raw = sessionStorage.getItem('bodega_vendor');
      if (raw) router.replace('/vendor/dashboard');
    } catch {}
  }, [router]);

  return (
    <div className="min-h-screen">

      {/* Hero */}
      <section className="relative overflow-hidden px-6 pb-36 pt-28 text-center">
        <div className="relative mx-auto max-w-4xl">
          <p className="text-xs font-semibold uppercase tracking-widest text-brand-700/60">
            BodegaPlanr
          </p>

          <h1 className="mt-5 text-6xl font-bold leading-tight tracking-tight text-brand-800/50 sm:text-7xl">
            The planning platform for
          </h1>
          <h1 className="text-6xl font-bold leading-tight tracking-tight text-slate-900 sm:text-7xl">
            Corner Store Owners.
          </h1>

          <p className="mx-auto mt-7 max-w-2xl text-lg leading-relaxed text-slate-900">
            Four AI agents that analyze your neighborhood — demographics, buying behavior,
            religious holidays, and vendor pricing — so you always stock the right products.
          </p>

          <div className="mt-10 flex justify-center">
            <Link
              href="/vendor"
              className="rounded-full bg-slate-900 px-8 py-3.5 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-slate-700"
            >
              Vendor Login
            </Link>
          </div>
        </div>
      </section>

      {/* 4-Agent Pipeline */}
      <section className="px-6 py-20">
        <div className="mx-auto max-w-6xl">
          <p className="text-xs font-semibold uppercase tracking-widest text-slate-900">
            The 4-Agent Pipeline
          </p>
          <p className="mt-2 max-w-xl text-slate-900">
            Each report runs four agents in sequence, combining public data sources with AI reasoning.
          </p>

          <div className="mt-8 grid gap-4 md:grid-cols-4">
            {agents.map((agent, i) => {
              const accent = ['bg-emerald-700', 'bg-fuchsia-500', 'bg-sky-500', 'bg-amber-400'][i];
              return (
                <div key={agent.num} className="overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-sm transition hover:shadow-md">
                  <div className="flex min-h-[220px] flex-col p-6">
                    <div className="flex items-start gap-4">
                      <div className={`h-14 w-2 rounded-full ${accent}`} />
                      <p className="text-5xl font-bold text-slate-900">{agent.num}</p>
                    </div>
                    <h3 className="mt-8 text-xl font-semibold text-slate-900">{agent.name}</h3>
                    <p className="mt-3 text-sm leading-6 text-slate-900">{agent.description}</p>
                    <div className="mt-auto flex flex-wrap gap-2">
                      {agent.sources.map((s) => (
                        <span key={s} className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-900">
                          {s}
                        </span>
                      ))}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      {/* Three Modes */}
      <section className="border-t border-white/30 px-6 py-20">
        <div className="mx-auto max-w-6xl">
          <p className="text-xs font-semibold uppercase tracking-widest text-slate-900">
            Three Ways to Use BodegaPlanr
          </p>
          <div className="mt-8 grid gap-4 md:grid-cols-3">
            {modes.map((mode) => (
              <div
                key={mode.href}
                className={`flex flex-col rounded-2xl border p-7 backdrop-blur-sm ${
                  mode.highlight ? 'border-white/60 bg-white/80' : 'border-white/40 bg-white/60'
                }`}
              >
                {mode.highlight && (
                  <span className="mb-3 self-start rounded-full bg-brand-600 px-2.5 py-0.5 text-xs font-semibold text-white">
                    Core Feature
                  </span>
                )}
                <h3 className="text-base font-semibold text-slate-900">{mode.label}</h3>
                <p className="mt-2 flex-1 text-sm leading-relaxed text-slate-900">{mode.description}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Data sources */}
      <section className="border-t border-white/30 px-6 py-14 text-center">
        <div className="mx-auto max-w-4xl">
          <p className="text-xs font-semibold uppercase tracking-widest text-slate-900">
            Powered by public data sources
          </p>
          <div className="mt-6 flex flex-wrap items-center justify-center gap-8">
            {['US Census Bureau', 'ARDA', 'Consumer Expenditure Survey', 'Hebcal', 'Aladhan', 'UNFI', 'Faire', 'RangeMe'].map((src) => (
              <span key={src} className="text-sm font-medium text-slate-900">{src}</span>
            ))}
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-white/30 px-6 py-8">
        <div className="mx-auto flex max-w-6xl items-center justify-between">
          <span className="text-sm font-semibold text-brand-700">BodegaPlanr</span>
          <span className="text-xs text-slate-900">Hackathon MVP &copy; 2026</span>
        </div>
      </footer>
    </div>
  );
}
