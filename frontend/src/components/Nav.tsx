'use client';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useEffect, useState } from 'react';

const publicLinks = [
  { href: '/', label: 'Home' },
  { href: '/data', label: 'Customer Data' },
];

const vendorLinks = [
  { href: '/wizard', label: 'Report Wizard' },
  { href: '/chat', label: 'Chat' },
];

function ArrowIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
      <path d="M2.5 6h7M6.5 3l3 3-3 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export default function Nav() {
  const pathname = usePathname();
  const isVendor = pathname.startsWith('/vendor');

  const [vendorName, setVendorName] = useState<string | null>(null);
  useEffect(() => {
    try {
      const raw = sessionStorage.getItem('bodega_vendor');
      if (raw) setVendorName(JSON.parse(raw).name);
    } catch {}
  }, [pathname]);

  const handleLogout = () => {
    sessionStorage.removeItem('bodega_vendor');
    setVendorName(null);
    window.location.href = '/';
  };

  return (
    <div className="fixed inset-x-4 top-4 z-50 sm:inset-x-6 lg:inset-x-10">
      <nav className="flex h-14 items-center justify-between rounded-2xl bg-white/30 px-5 shadow-sm backdrop-blur-md ring-1 ring-white/50">
        <Link href="/" className="flex shrink-0 items-center">
          <span className="font-bold tracking-tight text-green-700">BodegaPlanr</span>
        </Link>

        {!isVendor && (
          <div className="flex items-center gap-0.5">
            {[...publicLinks, ...(vendorName ? vendorLinks : [])].map(({ href, label }) => (
              <Link
                key={href}
                href={href}
                className={`rounded-lg px-3 py-1.5 text-sm font-medium transition-all ${
                  pathname === href
                    ? 'bg-green-50 text-green-700'
                    : 'text-slate-500 hover:bg-slate-50 hover:text-slate-800'
                }`}
              >
                {label}
              </Link>
            ))}
          </div>
        )}

        <div className="flex shrink-0 items-center gap-3">
          {vendorName ? (
            <>
              <Link
                href="/vendor/dashboard"
                className="hidden text-sm font-medium text-slate-600 hover:text-slate-900 sm:block"
              >
                {vendorName}
              </Link>
              <button
                onClick={handleLogout}
                className="flex items-center gap-2 rounded-full bg-slate-100 pl-4 pr-1.5 py-1.5 text-sm font-semibold text-slate-700 transition-colors hover:bg-slate-200"
              >
                Log Out
                <span className="flex h-7 w-7 items-center justify-center rounded-full bg-slate-800 text-white">
                  <ArrowIcon />
                </span>
              </button>
            </>
          ) : (
            <Link
              href="/vendor"
              className="flex items-center gap-2 rounded-full bg-green-50 pl-4 pr-1.5 py-1.5 text-sm font-semibold text-green-800 transition-colors hover:bg-green-100"
            >
              Vendor log in
              <span className="flex h-7 w-7 items-center justify-center rounded-full bg-slate-900 text-white">
                <ArrowIcon />
              </span>
            </Link>
          )}
        </div>
      </nav>
    </div>
  );
}
