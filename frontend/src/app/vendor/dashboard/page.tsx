'use client';
import { useEffect, useState, useCallback, useRef } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import dynamic from 'next/dynamic';
import { lookupVendor, type Vendor } from '@/lib/vendors';
import type { MapPin } from '@/components/MapView';

const MapView = dynamic(() => import('@/components/MapView'), { ssr: false });

type NewStoreForm = { name: string; address: string; zip: string; type: string };

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

type ReverseResult = { address: string; zip: string };

async function reverseGeocode(lat: number, lng: number): Promise<ReverseResult> {
  try {
    const url = `https://nominatim.openstreetmap.org/reverse?lat=${lat}&lon=${lng}&format=json`;
    const res = await fetch(url, { headers: { 'Accept-Language': 'en' } });
    const data = await res.json();
    const a = data.address ?? {};
    const road = a.road ?? '';
    const houseNumber = a.house_number ?? '';
    const city = a.city ?? a.town ?? a.village ?? '';
    const state = a.state ?? '';
    const zip = a.postcode ?? '';
    const street = houseNumber ? `${houseNumber} ${road}` : road;
    const address = [street, city, state].filter(Boolean).join(', ');
    return { address, zip };
  } catch {
    return { address: '', zip: '' };
  }
}

export default function VendorDashboardPage() {
  const router = useRouter();
  const [vendor, setVendor] = useState<Vendor | null>(null);
  const [ready, setReady] = useState(false);
  const [search, setSearch] = useState('');
  const [showAddForm, setShowAddForm] = useState(false);
  const [newStore, setNewStore] = useState<NewStoreForm>({ name: '', address: '', zip: '', type: 'Bodega' });
  const [formError, setFormError] = useState('');

  // Map state
  const [pins, setPins] = useState<MapPin[]>([]);
  const [mapCenter, setMapCenter] = useState<[number, number] | undefined>(undefined);
  const [mapZoom, setMapZoom] = useState(13);
  const geocodeDebounce = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [locating, setLocating] = useState(false);
  const [locError, setLocError] = useState('');

  useEffect(() => {
    try {
      const raw = sessionStorage.getItem('bodega_vendor');
      if (!raw) { router.replace('/vendor'); return; }
      const { id } = JSON.parse(raw) as { id: string; name: string };
      const data = lookupVendor(id);
      if (!data) { router.replace('/vendor'); return; }
      setVendor(data);
    } catch {
      router.replace('/vendor');
    } finally {
      setReady(true);
    }
  }, [router]);

  // Geocode all store addresses on load
  useEffect(() => {
    if (!vendor) return;
    (async () => {
      const results = await Promise.all(
        vendor.stores.map(async (s) => {
          const coords = await geocode(s.address || s.zip);
          if (!coords) return null;
          return { lat: coords[0], lng: coords[1], label: s.name, sub: s.address || `ZIP ${s.zip}`, active: true } as MapPin;
        })
      );
      const valid = results.filter(Boolean) as MapPin[];
      setPins(valid);
      if (valid.length === 1) { setMapCenter([valid[0].lat, valid[0].lng]); setMapZoom(15); }
    })();
  }, [vendor]);

  // Geocode search query with debounce, fly map to result
  const handleSearchChange = useCallback((value: string) => {
    setSearch(value);
    if (geocodeDebounce.current) clearTimeout(geocodeDebounce.current);
    if (!value.trim()) {
      // Reset to store pins
      setMapCenter(undefined);
      setMapZoom(13);
      return;
    }
    geocodeDebounce.current = setTimeout(async () => {
      const coords = await geocode(value.trim());
      if (coords) {
        setMapCenter(coords);
        setMapZoom(14);
        // Add a temporary search pin (not active = grey)
        setPins((prev) => {
          const storePins = prev.filter((p) => p.active);
          return [...storePins, { lat: coords[0], lng: coords[1], label: value.trim(), active: false }];
        });
      }
    }, 600);
  }, []);

  const handleLogout = () => {
    sessionStorage.removeItem('bodega_vendor');
    router.push('/vendor');
  };

  const useCurrentLocation = () => {
    if (!navigator.geolocation) { setLocError('Geolocation not supported by your browser.'); return; }
    setLocating(true);
    setLocError('');
    navigator.geolocation.getCurrentPosition(
      async (pos) => {
        const { latitude: lat, longitude: lng } = pos.coords;
        const { address, zip } = await reverseGeocode(lat, lng);
        setMapCenter([lat, lng]);
        setMapZoom(16);
        setPins((prev) => [...prev.filter((p) => p.active), { lat, lng, label: 'Your location', sub: address || undefined, active: false }]);
        setNewStore({ name: '', address, zip, type: 'Bodega' });
        setFormError('');
        setShowAddForm(true);
        setLocating(false);
      },
      () => {
        setLocError('Could not get your location. Please allow location access.');
        setLocating(false);
      },
      { timeout: 10000 }
    );
  };

  const openAddForm = (prefill?: string) => {
    const looksLikeZip = /^\d{5}$/.test(prefill?.trim() ?? '');
    setNewStore({ name: '', address: looksLikeZip ? '' : (prefill ?? ''), zip: looksLikeZip ? (prefill ?? '') : '', type: 'Bodega' });
    setFormError('');
    setShowAddForm(true);
  };

  const handleAddStoreSubmit = (e: React.SyntheticEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!newStore.name.trim()) { setFormError('Store name is required.'); return; }
    if (!/^\d{5}$/.test(newStore.zip.trim())) { setFormError('Enter a valid 5-digit ZIP code.'); return; }
    router.push(`/wizard?store=${encodeURIComponent(newStore.name.trim())}&zip=${newStore.zip.trim()}&type=${encodeURIComponent(newStore.type)}`);
  };

  if (!ready || !vendor) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-white">
        <div className="h-5 w-5 animate-spin rounded-full border-2 border-brand-500 border-t-transparent" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-50">
      {/* Header */}
      <div className="border-b border-slate-200 bg-white px-6 py-5">
        <div className="mx-auto flex max-w-5xl items-center justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-widest text-brand-600">
              BodegaPlanr &rsaquo; Vendor Portal
            </p>
            <h1 className="mt-1 text-xl font-bold text-slate-900">
              Welcome back, {vendor.name.split(' ')[0]}
            </h1>
            <p className="text-sm text-slate-500">
              {vendor.stores.length === 1 ? '1 store on your account' : `${vendor.stores.length} stores on your account`}
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

        <div className="grid gap-8 lg:grid-cols-[1.2fr_1.8fr]">
          {/* Left: search + store list */}
          <div className="space-y-6">
            <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
              <label className="block text-xs font-semibold uppercase tracking-widest text-slate-500">
                Search location
              </label>
              <input
                type="text"
                value={search}
                onChange={(e) => handleSearchChange(e.target.value)}
                placeholder="Search by name, address, or ZIP code"
                className="mt-3 w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-brand-400 focus:bg-white focus:ring-1 focus:ring-brand-200"
              />
            </div>

            <div className="space-y-4">
              {(() => {
                const query = search.trim().toLowerCase();
                const filtered = vendor.stores.filter((store) => {
                  if (!query) return true;
                  return [store.name, store.address, store.zip, store.type].join(' ').toLowerCase().includes(query);
                });

                return (
                  <>
                    {filtered.map((store) => (
                      <div key={store.id} className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
                        <div className="flex items-start justify-between gap-3">
                          <div className="flex items-center gap-3">
                            <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-brand-50 text-lg font-bold text-brand-700">
                              {store.name.charAt(0)}
                            </div>
                            <div>
                              <h2 className="text-lg font-semibold text-slate-900">{store.name}</h2>
                              <p className="text-sm text-slate-500">{store.address}</p>
                              <p className="text-sm text-slate-500">{store.zip}</p>
                            </div>
                          </div>
                          <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-600">
                            {store.type}
                          </span>
                        </div>
                        <div className="mt-4 flex justify-end">
                          <Link
                            href={`/wizard?store=${encodeURIComponent(store.name)}&zip=${store.zip}&type=${encodeURIComponent(store.type)}`}
                            className="rounded-full bg-brand-600 px-4 py-2 text-xs font-semibold text-white transition-colors hover:bg-brand-700"
                          >
                            Run New Report
                          </Link>
                        </div>
                      </div>
                    ))}

                    {query && filtered.length === 0 && !showAddForm && (
                      <div className="rounded-2xl border border-slate-200 bg-white p-5 text-center shadow-sm">
                        <p className="text-sm text-slate-500">No stores match <span className="font-medium text-slate-700">&ldquo;{search}&rdquo;</span>.</p>
                        <button
                          onClick={() => openAddForm(search)}
                          className="mt-3 rounded-full bg-brand-600 px-4 py-2 text-xs font-semibold text-white transition-colors hover:bg-brand-700"
                        >
                          + Add as New Store
                        </button>
                      </div>
                    )}
                  </>
                );
              })()}

              {showAddForm ? (
                <form onSubmit={handleAddStoreSubmit} className="rounded-2xl border border-brand-200 bg-white p-5 shadow-sm">
                  <p className="mb-4 text-sm font-semibold text-slate-800">New Store Details</p>
                  <div className="space-y-3">
                    <input type="text" placeholder="Store name *" value={newStore.name}
                      onChange={(e) => setNewStore((s) => ({ ...s, name: e.target.value }))}
                      className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 text-sm text-slate-900 outline-none focus:border-brand-400 focus:bg-white focus:ring-1 focus:ring-brand-200" />
                    <input type="text" placeholder="Address" value={newStore.address}
                      onChange={(e) => setNewStore((s) => ({ ...s, address: e.target.value }))}
                      className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 text-sm text-slate-900 outline-none focus:border-brand-400 focus:bg-white focus:ring-1 focus:ring-brand-200" />
                    <input type="text" placeholder="ZIP code *" value={newStore.zip}
                      onChange={(e) => setNewStore((s) => ({ ...s, zip: e.target.value }))}
                      className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 text-sm text-slate-900 outline-none focus:border-brand-400 focus:bg-white focus:ring-1 focus:ring-brand-200" />
                  </div>
                  {formError && <p className="mt-2 text-xs text-red-500">{formError}</p>}
                  <div className="mt-4 flex gap-2">
                    <button type="submit" className="flex-1 rounded-full bg-brand-600 py-2 text-xs font-semibold text-white transition-colors hover:bg-brand-700">
                      Generate Report
                    </button>
                    <button type="button" onClick={() => setShowAddForm(false)}
                      className="rounded-full border border-slate-200 px-4 py-2 text-xs font-medium text-slate-500 transition-colors hover:text-slate-700">
                      Cancel
                    </button>
                  </div>
                </form>
              ) : (
                <button onClick={() => openAddForm()}
                  className="w-full rounded-2xl border-2 border-dashed border-slate-200 bg-white px-5 py-6 text-sm font-medium text-slate-500 transition-colors hover:border-brand-300 hover:bg-brand-50/70">
                  + Add Another Store
                </button>
              )}
            </div>
          </div>

          {/* Right: interactive map */}
          <div className="space-y-4">
            <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
              <p className="text-xs font-semibold uppercase tracking-widest text-slate-500">Interactive Map</p>
              <p className="mt-1 text-sm text-slate-400">
                {search.trim() ? `Showing results for "${search}"` : 'Your store locations — search to explore any area'}
              </p>
            </div>
            <div className="relative overflow-hidden rounded-3xl border border-slate-200 shadow-sm" style={{ height: 520 }}>
              <MapView pins={pins} center={mapCenter} zoom={mapZoom} />
              {/* Use current location button */}
              <button
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
              {locError && (
                <p className="absolute bottom-16 right-4 z-[1000] max-w-xs rounded-xl bg-red-50 px-3 py-2 text-xs text-red-600 shadow-sm ring-1 ring-red-200">
                  {locError}
                </p>
              )}
            </div>
            <p className="text-center text-xs text-slate-300">
              &copy; OpenStreetMap contributors &middot; CARTO Voyager tiles
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
