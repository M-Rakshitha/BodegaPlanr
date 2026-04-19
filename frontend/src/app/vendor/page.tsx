'use client';
import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { authenticate } from '@/lib/vendors';

export default function VendorLoginPage() {
  const router = useRouter();
  const [id, setId] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [isLoggedIn, setIsLoggedIn] = useState(false);

  useEffect(() => {
    if (typeof window !== 'undefined') {
      setIsLoggedIn(!!sessionStorage.getItem('bodega_vendor'));
    }
  }, []);

  const handleSubmit = (e: React.SyntheticEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    setTimeout(() => {
      const vendor = authenticate(id, password);
      if (!vendor) {
        setError('Incorrect vendor ID or password. Try the demo credentials below.');
        setLoading(false);
        return;
      }
      sessionStorage.setItem(
        'bodega_vendor',
        JSON.stringify({ id: vendor.id, name: vendor.name })
      );
      router.push('/vendor/dashboard');
    }, 600);
  };

  const fillDemo = (vendorId: string, pw: string) => {
    setId(vendorId);
    setPassword(pw);
    setError('');
  };

  return (
    <div className="flex min-h-screen flex-col bg-white">
      {/* Top green accent bar */}
      <div className="h-1 bg-brand-500" />

      <div className="flex flex-1 items-center justify-center px-6 py-16">
        <div className="w-full max-w-sm">
          {/* Logo */}
          <Link href="/" className="mb-8 block text-center text-lg font-bold text-brand-700">
            BodegaPlanr
          </Link>

          <div className="rounded-2xl border border-slate-200 bg-white p-8 shadow-sm">
            <h1 className="text-xl font-bold text-slate-900">Vendor Login</h1>
            <p className="mt-1 text-sm text-slate-500">
              Sign in to manage your stores and run planning reports.
            </p>

            <form onSubmit={handleSubmit} className="mt-6 space-y-4">
              <div>
                <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Vendor ID
                </label>
                <input
                  type="text"
                  value={id}
                  onChange={(e) => setId(e.target.value)}
                  placeholder="e.g. carlos01"
                  required
                  disabled={loading}
                  className="w-full rounded-lg border border-slate-200 bg-slate-50 px-4 py-2.5 text-sm text-slate-900 placeholder-slate-400 focus:border-brand-400 focus:bg-white focus:outline-none focus:ring-1 focus:ring-brand-400 disabled:opacity-60"
                />
              </div>

              <div>
                <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Password
                </label>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  required
                  disabled={loading}
                  className="w-full rounded-lg border border-slate-200 bg-slate-50 px-4 py-2.5 text-sm text-slate-900 placeholder-slate-400 focus:border-brand-400 focus:bg-white focus:outline-none focus:ring-1 focus:ring-brand-400 disabled:opacity-60"
                />
              </div>

              {error && (
                <p className="rounded-lg bg-red-50 px-4 py-2.5 text-xs text-red-600">
                  {error}
                </p>
              )}

              <button
                type="submit"
                disabled={loading || !id.trim() || !password.trim()}
                className="mt-1 w-full rounded-full bg-brand-600 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-brand-700 disabled:opacity-50"
              >
                {loading ? 'Signing in...' : 'Sign In'}
              </button>
            </form>
          </div>

          {/* Demo credentials */}
          <div className="mt-5 rounded-xl border border-slate-200 bg-slate-50 p-5">
            <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-slate-400">
              Demo Credentials
            </p>
            <div className="space-y-2">
              {[
                { id: 'carlos01', pw: 'store123', name: 'Carlos Morales', stores: '2 stores' },
                { id: 'maria02', pw: 'store456', name: 'Maria Santos', stores: '1 store' },
                { id: 'joe03', pw: 'store789', name: 'Joe Kim', stores: '3 stores' },
              ].map((d) => (
                <button
                  key={d.id}
                  type="button"
                  onClick={() => fillDemo(d.id, d.pw)}
                  className="flex w-full items-center justify-between rounded-lg border border-slate-200 bg-white px-3 py-2 text-left transition-colors hover:border-brand-300 hover:bg-brand-50"
                >
                  <div>
                    <span className="text-xs font-semibold text-slate-700">{d.name}</span>
                    <span className="mx-1.5 text-slate-300">&middot;</span>
                    <code className="text-xs text-slate-500">{d.id}</code>
                  </div>
                  <span className="text-xs text-slate-400">{d.stores}</span>
                </button>
              ))}
            </div>
            <p className="mt-3 text-xs text-slate-400">Click a row to fill the form.</p>
          </div>

          <p className="mt-5 text-center text-xs text-slate-500">
            New to BodegaPlanr?{' '}
            <Link href="/vendor/signup" className="font-semibold text-brand-600 hover:underline">
              Create an account
            </Link>
          </p>

          {!isLoggedIn && (
            <p className="mt-3 text-center text-xs text-slate-400">
              <Link href="/" className="hover:underline">&larr; Back to home</Link>
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
