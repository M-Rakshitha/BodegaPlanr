'use client';
import { useState, useEffect, useRef } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import dynamic from 'next/dynamic';
import { saveCustomVendor } from '@/lib/vendors';
import type { MapPin } from '@/components/MapView';

const MapView = dynamic(() => import('@/components/MapView'), { ssr: false });

function generateVendorId(fullName: string): string {
  const first = fullName.trim().split(' ')[0].toLowerCase().replace(/[^a-z]/g, '');
  const suffix = Math.floor(10 + Math.random() * 90);
  return `${first}${suffix}`;
}

async function geocode(query: string): Promise<[number, number] | null> {
  try {
    const url = `https://nominatim.openstreetmap.org/search?q=${encodeURIComponent(query)}&format=json&limit=1&countrycodes=us`;
    const res = await fetch(url, { headers: { 'Accept-Language': 'en' } });
    const data = await res.json();
    if (!data.length) return null;
    return [parseFloat(data[0].lat), parseFloat(data[0].lon)];
  } catch {
    return null;
  }
}

export default function VendorSignupPage() {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const [form, setForm] = useState({
    fullName: '',
    password: '',
    confirmPassword: '',
    storeName: '',
    address: '',
    zip: '',
  });

  // Map state
  const [pins, setPins] = useState<MapPin[]>([]);
  const [mapCenter, setMapCenter] = useState<[number, number]>([40.7128, -74.006]);
  const [mapZoom, setMapZoom] = useState(11);
  const [locating, setLocating] = useState(false);
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Geocode when address or zip changes
  useEffect(() => {
    const query = (form.address || form.zip).trim();
    if (!query) return;
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(async () => {
      const coords = await geocode(query);
      if (coords) {
        setMapCenter(coords);
        setMapZoom(15);
        setPins([{ lat: coords[0], lng: coords[1], label: form.storeName || 'New store', sub: form.address || form.zip, active: true, draggable: true }]);
      }
    }, 600);
  }, [form.address, form.zip, form.storeName]);

  useEffect(() => {
    if (typeof window !== 'undefined') {
      setIsLoggedIn(!!sessionStorage.getItem('bodega_vendor'));
    }
  }, []);

  const handlePinDrag = async (lat: number, lng: number) => {
    try {
      const res = await fetch(`https://nominatim.openstreetmap.org/reverse?lat=${lat}&lon=${lng}&format=json`, { headers: { 'Accept-Language': 'en' } });
      const data = await res.json();
      const a = data.address ?? {};
      const road = a.road ?? '';
      const houseNumber = a.house_number ?? '';
      const city = a.city ?? a.town ?? a.village ?? '';
      const state = a.state ?? '';
      const zip = a.postcode ?? '';
      const street = houseNumber ? `${houseNumber} ${road}` : road;
      const address = [street, city, state].filter(Boolean).join(', ');
      setForm((f) => ({ ...f, address, zip }));
      setPins([{ lat, lng, label: form.storeName || 'New store', sub: address, active: true, draggable: true }]);
    } catch {}
  };

  const set = (key: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm((f) => ({ ...f, [key]: e.target.value }));

  const useCurrentLocation = () => {
    if (!navigator.geolocation) return;
    setLocating(true);
    navigator.geolocation.getCurrentPosition(
      async (pos) => {
        const { latitude: lat, longitude: lng } = pos.coords;
        // Reverse geocode
        try {
          const res = await fetch(`https://nominatim.openstreetmap.org/reverse?lat=${lat}&lon=${lng}&format=json`, { headers: { 'Accept-Language': 'en' } });
          const data = await res.json();
          const a = data.address ?? {};
          const road = a.road ?? '';
          const houseNumber = a.house_number ?? '';
          const city = a.city ?? a.town ?? a.village ?? '';
          const state = a.state ?? '';
          const zip = a.postcode ?? '';
          const street = houseNumber ? `${houseNumber} ${road}` : road;
          const address = [street, city, state].filter(Boolean).join(', ');
          setForm((f) => ({ ...f, address, zip }));
        } catch {}
        setMapCenter([lat, lng]);
        setMapZoom(16);
        setPins([{ lat, lng, label: form.storeName || 'New store', sub: 'Current location', active: true }]);
        setLocating(false);
      },
      () => setLocating(false),
      { timeout: 10000 }
    );
  };

  const handleSubmit = (e: React.SyntheticEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError('');
    if (!form.fullName.trim()) { setError('Full name is required.'); return; }
    if (form.password.length < 6) { setError('Password must be at least 6 characters.'); return; }
    if (form.password !== form.confirmPassword) { setError('Passwords do not match.'); return; }
    if (!form.storeName.trim()) { setError('Store name is required.'); return; }
    if (!form.address.trim()) { setError('Address is required.'); return; }
    if (!/^\d{5}$/.test(form.zip.trim())) { setError('Enter a valid 5-digit ZIP code.'); return; }

    setLoading(true);
    setTimeout(() => {
      const vendorId = generateVendorId(form.fullName);
      const vendor = {
        id: vendorId,
        password: form.password,
        name: form.fullName.trim(),
        stores: [{
          id: `custom-${Date.now()}`,
          name: form.storeName.trim(),
          address: form.address.trim(),
          zip: form.zip.trim(),
          type: 'Bodega',
          lastReport: null,
        }],
      };
      saveCustomVendor(vendor);
      sessionStorage.setItem('bodega_vendor', JSON.stringify({ id: vendorId, name: vendor.name }));
      router.push('/vendor/dashboard');
    }, 600);
  };

  return (
    <div className="flex min-h-screen flex-col bg-white">
      <div className="h-1 bg-brand-500" />

      <div className="flex flex-1 items-center justify-center px-6 py-12">
        <div className="w-full max-w-4xl">
          <Link href="/" className="mb-8 block text-center text-lg font-bold text-brand-700">
            BodegaPlanr
          </Link>

          <div className="grid gap-6 lg:grid-cols-[1fr_1.1fr]">
            {/* Form */}
            <div className="rounded-2xl border border-slate-200 bg-white p-8 shadow-sm">
              <h1 className="text-xl font-bold text-slate-900">Create Account</h1>
              <p className="mt-1 text-sm text-slate-500">Sign up to start planning your store.</p>

              <form onSubmit={handleSubmit} className="mt-6 space-y-5">
                <div>
                  <p className="mb-3 text-xs font-semibold uppercase tracking-widest text-slate-400">Your Account</p>
                  <div className="space-y-3">
                    <div>
                      <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-slate-500">Full Name</label>
                      <input type="text" value={form.fullName} onChange={set('fullName')} placeholder="e.g. Maria Santos" required disabled={loading}
                        className="w-full rounded-lg border border-slate-200 bg-slate-50 px-4 py-2.5 text-sm text-slate-900 placeholder-slate-400 focus:border-brand-400 focus:bg-white focus:outline-none focus:ring-1 focus:ring-brand-400 disabled:opacity-60" />
                    </div>
                    <div>
                      <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-slate-500">Password</label>
                      <input type="password" value={form.password} onChange={set('password')} placeholder="Min. 6 characters" required disabled={loading}
                        className="w-full rounded-lg border border-slate-200 bg-slate-50 px-4 py-2.5 text-sm text-slate-900 placeholder-slate-400 focus:border-brand-400 focus:bg-white focus:outline-none focus:ring-1 focus:ring-brand-400 disabled:opacity-60" />
                    </div>
                    <div>
                      <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-slate-500">Confirm Password</label>
                      <input type="password" value={form.confirmPassword} onChange={set('confirmPassword')} placeholder="••••••••" required disabled={loading}
                        className="w-full rounded-lg border border-slate-200 bg-slate-50 px-4 py-2.5 text-sm text-slate-900 placeholder-slate-400 focus:border-brand-400 focus:bg-white focus:outline-none focus:ring-1 focus:ring-brand-400 disabled:opacity-60" />
                    </div>
                  </div>
                </div>

                <div>
                  <p className="mb-3 text-xs font-semibold uppercase tracking-widest text-slate-400">Your First Store</p>
                  <div className="space-y-3">
                    <div>
                      <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-slate-500">Store Name</label>
                      <input type="text" value={form.storeName} onChange={set('storeName')} placeholder="e.g. Santos Deli" required disabled={loading}
                        className="w-full rounded-lg border border-slate-200 bg-slate-50 px-4 py-2.5 text-sm text-slate-900 placeholder-slate-400 focus:border-brand-400 focus:bg-white focus:outline-none focus:ring-1 focus:ring-brand-400 disabled:opacity-60" />
                    </div>
                    <div>
                      <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-slate-500">Address</label>
                      <input type="text" value={form.address} onChange={set('address')} placeholder="e.g. 123 Main St, New York, NY" required disabled={loading}
                        className="w-full rounded-lg border border-slate-200 bg-slate-50 px-4 py-2.5 text-sm text-slate-900 placeholder-slate-400 focus:border-brand-400 focus:bg-white focus:outline-none focus:ring-1 focus:ring-brand-400 disabled:opacity-60" />
                    </div>
                    <div>
                      <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-slate-500">ZIP Code</label>
                      <input type="text" value={form.zip} onChange={set('zip')} placeholder="e.g. 10031" maxLength={5} required disabled={loading}
                        className="w-full rounded-lg border border-slate-200 bg-slate-50 px-4 py-2.5 text-sm text-slate-900 placeholder-slate-400 focus:border-brand-400 focus:bg-white focus:outline-none focus:ring-1 focus:ring-brand-400 disabled:opacity-60" />
                    </div>
                  </div>
                </div>

                {error && (
                  <p className="rounded-lg bg-red-50 px-4 py-2.5 text-xs text-red-600">{error}</p>
                )}

                <button type="submit" disabled={loading}
                  className="w-full rounded-full bg-brand-600 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-brand-700 disabled:opacity-50">
                  {loading ? 'Creating account...' : 'Create Account & Continue'}
                </button>
              </form>
            </div>

            {/* Map */}
            <div className="flex flex-col gap-3">
              <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                <p className="text-xs font-semibold uppercase tracking-widest text-slate-500">Store Location Preview</p>
                <p className="mt-1 text-sm text-slate-400">
                  {pins.length ? 'Pin updates as you type your address.' : 'Enter your address to see it on the map.'}
                </p>
              </div>
              <div className="relative overflow-hidden rounded-3xl border border-slate-200 shadow-sm" style={{ height: 460 }}>
                <MapView pins={pins} center={mapCenter} zoom={mapZoom} onPinDrag={handlePinDrag} />
                <button
                  type="button"
                  onClick={useCurrentLocation}
                  disabled={locating}
                  className="absolute bottom-4 right-4 z-[1000] flex items-center gap-2 rounded-full bg-white px-4 py-2.5 text-xs font-semibold text-slate-700 shadow-md ring-1 ring-slate-200 transition-all hover:bg-brand-50 hover:text-brand-700 hover:ring-brand-300 disabled:opacity-60"
                >
                  {locating ? (
                    <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-brand-500 border-t-transparent" />
                  ) : (
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                      <circle cx="12" cy="12" r="3" /><path d="M12 2v3M12 19v3M2 12h3M19 12h3" /><circle cx="12" cy="12" r="8" strokeOpacity="0.3" />
                    </svg>
                  )}
                  {locating ? 'Locating…' : 'Use my location'}
                </button>
              </div>
              <p className="text-center text-xs text-slate-300">
                &copy; OpenStreetMap contributors &middot; CARTO Voyager tiles
              </p>
            </div>
          </div>

          <p className="mt-5 text-center text-xs text-slate-500">
            Already have an account?{' '}
            <Link href="/vendor" className="font-semibold text-brand-600 hover:underline">Sign in</Link>
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
