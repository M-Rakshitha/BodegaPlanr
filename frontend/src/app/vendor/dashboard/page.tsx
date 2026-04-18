'use client';
import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { VENDORS, type Vendor } from '@/lib/vendors';

export default function VendorDashboardPage() {
  const router = useRouter();
  const [vendor, setVendor] = useState<Vendor | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    try {
      const raw = sessionStorage.getItem('bodega_vendor');
      if (!raw) {
        router.replace('/vendor');
        return;
      }
      const { id } = JSON.parse(raw) as { id: string; name: string };
      const data = VENDORS[id];
      if (!data) {
        router.replace('/vendor');
        return;
      }
      setVendor(data);
    } catch {
      router.replace('/vendor');
    } finally {
      setReady(true);
    }
  }, [router]);

  const handleLogout = () => {
    sessionStorage.removeItem('bodega_vendor');
    router.push('/vendor');
  };

  if (!ready || !vendor) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-white">
        <div className="h-5 w-5 animate-spin rounded-full border-2 border-green-500 border-t-transparent" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-50">
      {/* Header */}
      <div className="border-b border-slate-200 bg-white px-6 py-5">
        <div className="mx-auto flex max-w-5xl items-center justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-widest text-green-600">
              BodegaPlanr &rsaquo; Vendor Portal
            </p>
            <h1 className="mt-1 text-xl font-bold text-slate-900">
              Welcome back, {vendor.name.split(' ')[0]}
            </h1>
            <p className="text-sm text-slate-500">
              {vendor.stores.length === 1
                ? '1 store on your account'
                : `${vendor.stores.length} stores on your account`}
            </p>
          </div>
          <button
            onClick={handleLogout}
            className="rounded-full border border-slate-200 px-4 py-1.5 text-xs font-semibold text-slate-500 transition-colors hover:border-slate-300 hover:text-slate-700"
          >
            Log Out
          </button>
        </div>
      </div>

      {/* Stores */}
      <div className="mx-auto max-w-5xl px-6 py-10">
        <p className="mb-5 text-xs font-semibold uppercase tracking-widest text-slate-400">
          Your Stores — choose one to continue
        </p>

        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {vendor.stores.map((store) => (
            <div
              key={store.id}
              className="flex flex-col rounded-2xl border border-slate-200 bg-white p-6 shadow-sm transition-shadow hover:shadow-md"
            >
              {/* Store header */}
              <div className="flex items-start justify-between gap-2">
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-green-100 text-base font-bold text-green-700">
                  {store.name.charAt(0)}
                </div>
                <span className="rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-medium text-slate-500">
                  {store.type}
                </span>
              </div>

              <h2 className="mt-4 text-base font-semibold text-slate-900">{store.name}</h2>
              <p className="mt-0.5 text-xs text-slate-400">{store.address}</p>
              <p className="mt-0.5 text-xs text-slate-400">ZIP {store.zip}</p>

              {/* Last report status */}
              <div className="mt-4 rounded-lg bg-slate-50 px-3 py-2.5">
                {store.lastReport ? (
                  <div className="flex items-center gap-2">
                    <span className="h-1.5 w-1.5 rounded-full bg-green-500" />
                    <span className="text-xs text-slate-500">
                      Last report: <span className="font-medium text-slate-700">{store.lastReport}</span>
                    </span>
                  </div>
                ) : (
                  <div className="flex items-center gap-2">
                    <span className="h-1.5 w-1.5 rounded-full bg-slate-300" />
                    <span className="text-xs text-slate-400">No reports yet</span>
                  </div>
                )}
              </div>

              {/* Actions */}
              <div className="mt-5 flex flex-col gap-2">
                <Link
                  href={`/wizard?store=${encodeURIComponent(store.name)}&zip=${store.zip}&type=${encodeURIComponent(store.type)}`}
                  className="w-full rounded-full bg-green-600 py-2 text-center text-xs font-semibold text-white transition-colors hover:bg-green-700"
                >
                  Run New Report
                </Link>
                {store.lastReport ? (
                  <Link
                    href="/chat"
                    className="w-full rounded-full border border-slate-200 py-2 text-center text-xs font-semibold text-slate-600 transition-colors hover:border-slate-300 hover:text-slate-800"
                  >
                    Ask Questions in Chat
                  </Link>
                ) : (
                  <Link
                    href="/data"
                    className="w-full rounded-full border border-slate-200 py-2 text-center text-xs font-semibold text-slate-600 transition-colors hover:border-slate-300 hover:text-slate-800"
                  >
                    Upload Sales Data
                  </Link>
                )}
              </div>
            </div>
          ))}

          {/* Add store card */}
          <button className="flex flex-col items-center justify-center rounded-2xl border-2 border-dashed border-slate-200 p-6 transition-colors hover:border-green-300 hover:bg-green-50/30">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl border-2 border-dashed border-slate-300 text-xl text-slate-300">
              +
            </div>
            <p className="mt-3 text-sm font-medium text-slate-400">Add Another Store</p>
            <p className="mt-0.5 text-xs text-slate-300">Run a report for a new location</p>
          </button>
        </div>

        {/* Quick stats */}
        <div className="mt-10 grid grid-cols-3 gap-4">
          {[
            {
              label: 'Reports Run',
              value: vendor.stores.filter((s) => s.lastReport).length,
              note: 'across all stores',
            },
            {
              label: 'Stores Active',
              value: vendor.stores.length,
              note: 'on your account',
            },
            {
              label: 'Next Holiday',
              value: 'Apr 27',
              note: 'Eid al-Fitr — stock now',
            },
          ].map((stat) => (
            <div key={stat.label} className="rounded-xl border border-slate-200 bg-white p-5">
              <p className="text-2xl font-bold text-slate-900">{stat.value}</p>
              <p className="mt-0.5 text-xs font-semibold text-slate-600">{stat.label}</p>
              <p className="text-xs text-slate-400">{stat.note}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
