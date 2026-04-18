'use client';
import { useState } from 'react';

const mockDelta = [
  { product: 'Goya Coconut Water', category: 'Beverages', jan: 48, feb: 62, delta: 14 },
  { product: 'Monster Energy 16 oz', category: 'Beverages', jan: 120, feb: 145, delta: 25 },
  { product: "Lay's Classic 1.5 oz", category: 'Snacks', jan: 200, feb: 180, delta: -20 },
  { product: 'Bounty Paper Towels', category: 'Household', jan: 30, feb: 38, delta: 8 },
  { product: 'Dove Soap Bar', category: 'Personal Care', jan: 45, feb: 42, delta: -3 },
  { product: 'Goya Black Beans', category: 'Latin Foods', jan: 60, feb: 78, delta: 18 },
  { product: 'Red Bull 8.4 oz', category: 'Beverages', jan: 90, feb: 85, delta: -5 },
  { product: 'Pantene Shampoo 12 oz', category: 'Personal Care', jan: 22, feb: 31, delta: 9 },
  { product: 'Saazón Goya', category: 'Latin Foods', jan: 55, feb: 70, delta: 15 },
  { product: 'Doritos Nacho 1.75 oz', category: 'Snacks', jan: 110, feb: 98, delta: -12 },
];

const growing = mockDelta.filter((r) => r.delta > 0).length;
const totalDelta = mockDelta.reduce((sum, r) => sum + r.feb - r.jan, 0);
const totalPrev = mockDelta.reduce((sum, r) => sum + r.jan, 0);
const pctChange = ((totalDelta / totalPrev) * 100).toFixed(1);

export default function DataPage() {
  const [uploaded, setUploaded] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [filter, setFilter] = useState('All');

  const cats = ['All', ...Array.from(new Set(mockDelta.map((r) => r.category)))];
  const rows = filter === 'All' ? mockDelta : mockDelta.filter((r) => r.category === filter);

  return (
    <div className="min-h-screen bg-slate-50 px-6 py-10">
      <div className="mx-auto max-w-4xl">
        <p className="text-xs font-semibold uppercase tracking-widest text-green-600">Customer Data Mode</p>
        <h1 className="mt-1 text-3xl font-bold text-slate-900">Sales Delta Analysis</h1>
        <p className="mt-2 text-sm text-slate-500">
          Upload your sales CSV to track buying trends and compare periods side-by-side.
        </p>

        {!uploaded ? (
          <>
            <div
              onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
              onDragLeave={() => setDragging(false)}
              onDrop={(e) => { e.preventDefault(); setDragging(false); setUploaded(true); }}
              onClick={() => setUploaded(true)}
              className={`mt-10 flex cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed py-24 text-center transition-all ${
                dragging
                  ? 'border-green-400 bg-green-50'
                  : 'border-slate-300 bg-white hover:border-green-300 hover:bg-green-50/40'
              }`}
            >
              <div className="flex h-14 w-14 items-center justify-center rounded-full border border-slate-200 bg-slate-50 text-2xl text-slate-400 mb-4">
                &#8593;
              </div>
              <p className="text-base font-medium text-slate-700">Drop your CSV file here</p>
              <p className="mt-1 text-sm text-slate-400">or click to select &nbsp;&middot;&nbsp; CSV files only</p>
              <div className="mt-6 rounded-lg border border-slate-200 bg-slate-50 px-5 py-3 text-left">
                <p className="text-xs font-medium text-slate-400 mb-1">Expected columns</p>
                <code className="text-xs text-green-700">product, category, units_sold, period</code>
              </div>
            </div>

            <div className="mt-8 grid grid-cols-3 gap-4">
              {[
                { label: 'Upload a CSV', desc: 'Current period sales data' },
                { label: 'Auto-compare', desc: 'Against your last uploaded period' },
                { label: 'See the delta', desc: 'Which products are growing or shrinking' },
              ].map((s, i) => (
                <div key={i} className="rounded-xl border border-slate-200 bg-white p-4 text-center shadow-sm">
                  <p className="text-2xl font-bold text-slate-200">{i + 1}</p>
                  <p className="mt-2 text-sm font-medium text-slate-700">{s.label}</p>
                  <p className="mt-0.5 text-xs text-slate-400">{s.desc}</p>
                </div>
              ))}
            </div>
          </>
        ) : (
          <div className="mt-8">
            {/* Header */}
            <div className="mb-6 flex flex-wrap items-start justify-between gap-3">
              <div>
                <p className="text-sm text-slate-500">
                  Comparing{' '}
                  <span className="font-semibold text-slate-800">January 2026</span>
                  {' '}vs{' '}
                  <span className="font-semibold text-slate-800">February 2026</span>
                </p>
                <p className="mt-0.5 text-xs text-slate-400">
                  sales_feb2026.csv &middot; {mockDelta.length} products &middot; uploaded just now
                </p>
              </div>
              <button
                onClick={() => setUploaded(false)}
                className="rounded-full border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-500 transition-colors hover:border-slate-300 hover:text-slate-700"
              >
                Upload another &rarr;
              </button>
            </div>

            {/* Summary cards */}
            <div className="mb-6 grid grid-cols-2 gap-4 sm:grid-cols-4">
              <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
                <p className={`text-2xl font-bold ${Number(pctChange) >= 0 ? 'text-green-600' : 'text-rose-500'}`}>
                  {Number(pctChange) >= 0 ? '+' : ''}{pctChange}%
                </p>
                <p className="mt-0.5 text-xs text-slate-400">Total Units Change</p>
              </div>
              <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
                <p className="text-2xl font-bold text-slate-800">{growing} / {mockDelta.length}</p>
                <p className="mt-0.5 text-xs text-slate-400">Products Growing</p>
              </div>
              <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
                <p className="text-2xl font-bold text-green-600">+25</p>
                <p className="mt-0.5 text-xs text-slate-400">Biggest Gain (Monster)</p>
              </div>
              <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
                <p className="text-2xl font-bold text-rose-500">&minus;20</p>
                <p className="mt-0.5 text-xs text-slate-400">Biggest Drop (Lay&apos;s)</p>
              </div>
            </div>

            {/* Category filter */}
            <div className="mb-4 flex flex-wrap gap-2">
              {cats.map((cat) => (
                <button
                  key={cat}
                  onClick={() => setFilter(cat)}
                  className={`rounded-full px-3 py-1 text-xs font-medium transition-all ${
                    filter === cat
                      ? 'bg-green-100 text-green-700 ring-1 ring-green-300'
                      : 'bg-white text-slate-500 ring-1 ring-slate-200 hover:text-slate-700'
                  }`}
                >
                  {cat}
                </button>
              ))}
            </div>

            {/* Delta table */}
            <div className="overflow-hidden rounded-xl border border-slate-200 shadow-sm">
              <table className="w-full text-sm">
                <thead className="border-b border-slate-200 bg-slate-50">
                  <tr>
                    {['Product', 'Category', 'Jan Units', 'Feb Units', 'Delta'].map((h) => (
                      <th
                        key={h}
                        className={`px-4 py-3 text-xs font-semibold uppercase tracking-wider text-slate-400 ${
                          h === 'Jan Units' || h === 'Feb Units' || h === 'Delta' ? 'text-right' : 'text-left'
                        }`}
                      >
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 bg-white">
                  {rows.map((row) => (
                    <tr key={row.product} className="transition-colors hover:bg-slate-50">
                      <td className="px-4 py-3 font-medium text-slate-800">{row.product}</td>
                      <td className="px-4 py-3 text-slate-400">{row.category}</td>
                      <td className="px-4 py-3 text-right text-slate-400">{row.jan}</td>
                      <td className="px-4 py-3 text-right text-slate-600">{row.feb}</td>
                      <td className={`px-4 py-3 text-right font-semibold ${row.delta > 0 ? 'text-green-600' : 'text-rose-500'}`}>
                        {row.delta > 0 ? '+' : ''}{row.delta}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="mt-4 rounded-xl border border-green-200 bg-green-50 p-4 text-sm text-slate-700">
              Beverages are your fastest-growing category (+9.3% on average). Consider increasing order
              quantities on Monster Energy and Goya Coconut Water before the next period.
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
