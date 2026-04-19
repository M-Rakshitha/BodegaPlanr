'use client';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useState } from 'react';

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

  const [vendorName, setVendorName] = useState<string | null>(() => {
    if (typeof window === 'undefined') return null;
    try {
      const raw = sessionStorage.getItem('bodega_vendor');
      return raw ? JSON.parse(raw).name : null;
    } catch {
      return null;
    }
  });

  if (pathname !== '/') return null;

  const handleLogout = () => {
    sessionStorage.removeItem('bodega_vendor');
    setVendorName(null);
    window.location.href = '/';
  };

  return (
    <div className="fixed inset-x-4 top-4 z-50 sm:inset-x-6 lg:inset-x-10">
      <nav className="flex h-14 items-center justify-between rounded-2xl bg-white/30 px-5 shadow-sm backdrop-blur-md ring-1 ring-white/50">
        <Link href="/" className="flex shrink-0 items-center">
          <span className="font-bold tracking-tight text-brand-700">BodegaPlanr</span>
        </Link>

        {!isVendor && (
          <div className="flex items-center gap-0.5">
            {[...publicLinks, ...(vendorName ? vendorLinks : [])].map(({ href, label }) => (
              <Link
                key={href}
                href={href}
                className={`rounded-lg px-3 py-1.5 text-sm font-medium transition-all ${
                  pathname === href
                    ? 'bg-brand-50 text-brand-700'
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
                className="flex items-center gap-2 rounded-full bg-brand-600 pl-4 pr-1.5 py-1.5 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-brand-700"
              >
                Log Out
                <span className="flex h-7 w-7 items-center justify-center rounded-full bg-white text-brand-700">
                  <ArrowIcon />
                </span>
              </button>
            </>
          ) : (
            <Link
              href="/vendor"
              className="flex items-center gap-2 rounded-full bg-brand-50 pl-4 pr-1.5 py-1.5 text-sm font-semibold text-brand-800 transition-colors hover:bg-brand-100"
            >
              Login/SignUp
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
