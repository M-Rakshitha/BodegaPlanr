export type Store = {
  id: string;
  name: string;
  zip: string;
  type: string;
  lastReport: string | null;
  address: string;
};

export type Vendor = {
  id: string;
  password: string;
  name: string;
  stores: Store[];
};

export const VENDORS: Record<string, Vendor> = {
  carlos01: {
    id: 'carlos01',
    password: 'store123',
    name: 'Carlos Morales',
    stores: [
      {
        id: 's1',
        name: 'Morales Corner Store',
        zip: '10031',
        type: 'Bodega',
        lastReport: 'Apr 18, 2026',
        address: '2241 Amsterdam Ave, New York, NY',
      },
      {
        id: 's2',
        name: 'West Side Bodega',
        zip: '10025',
        type: 'Bodega',
        lastReport: 'Apr 10, 2026',
        address: '785 Columbus Ave, New York, NY',
      },
    ],
  },
  maria02: {
    id: 'maria02',
    password: 'store456',
    name: 'Maria Santos',
    stores: [
      {
        id: 's3',
        name: 'Santos Deli',
        zip: '10040',
        type: 'Bodega',
        lastReport: 'Mar 28, 2026',
        address: '4512 Broadway, New York, NY',
      },
    ],
  },
  joe03: {
    id: 'joe03',
    password: 'store789',
    name: 'Joe Kim',
    stores: [
      {
        id: 's4',
        name: "Kim's Convenience",
        zip: '10002',
        type: 'Bodega',
        lastReport: null,
        address: '218 Grand St, New York, NY',
      },
      {
        id: 's5',
        name: 'Lower East Grocery',
        zip: '10009',
        type: 'Bodega',
        lastReport: 'Apr 5, 2026',
        address: '512 E 11th St, New York, NY',
      },
      {
        id: 's6',
        name: 'Chinatown Bodega',
        zip: '10013',
        type: 'Bodega',
        lastReport: null,
        address: '88 Mott St, New York, NY',
      },
    ],
  },
};

export function authenticate(id: string, password: string): Vendor | null {
  const vendor = VENDORS[id.toLowerCase().trim()];
  if (!vendor) return null;
  if (vendor.password !== password) return null;
  return vendor;
}
