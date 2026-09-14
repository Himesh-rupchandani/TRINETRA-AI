import type { WatchlistRecord } from '@/types';

/**
 * Returns an ISO timestamp for a clock time on today's date (local).
 * If that instant is still in the future (e.g. a 14:12 demo sighting viewed
 * at 09:00), it rolls back one day so the demo data always reads as history.
 */
export function atToday(h: number, m: number, s = 0, dayOffset = 0): string {
  const d = new Date();
  d.setDate(d.getDate() + dayOffset);
  d.setHours(h, m, s, 0);
  if (dayOffset === 0 && d.getTime() > Date.now()) d.setDate(d.getDate() - 1);
  return d.toISOString();
}

/** DEMO / SYNTHETIC watchlist — no real case data. */
export const mockWatchlist: WatchlistRecord[] = [
  {
    id: 'wl-001',
    plate: 'GJ01AB1234',
    category: 'STOLEN VEHICLE',
    severity: 'HIGH',
    reason: 'Reported stolen from Paldi residential parking. FIR filed 02:40 hrs.',
    caseRef: 'FIR/2026/PLD/0417',
    addedBy: 'Insp. R. Chauhan',
    addedAt: atToday(2, 40, 0, -1),
    active: true,
    contact: 'Paldi PS — 100',
  },
  {
    id: 'wl-002',
    plate: 'GJ05XY4321',
    category: 'WANTED SUSPECT',
    severity: 'CRITICAL',
    reason: 'Vehicle linked to suspect in armed robbery investigation.',
    caseRef: 'CR/2026/CID/1129',
    addedBy: 'DySP M. Patel',
    addedAt: atToday(9, 15, 0, -3),
    active: true,
    contact: 'CID Crime — 1090',
  },
  {
    id: 'wl-003',
    plate: 'GJ18MH0099',
    category: 'BLACKLISTED',
    severity: 'MEDIUM',
    reason: 'Commercial permit revoked; repeated overload violations.',
    caseRef: 'RTO/BL/2026/0083',
    addedBy: 'RTO Enforcement',
    addedAt: atToday(11, 0, 0, -8),
    active: true,
  },
  {
    id: 'wl-004',
    plate: 'GJ27CJ7788',
    category: 'AMBER ALERT',
    severity: 'CRITICAL',
    reason: 'Suspected vehicle in minor abduction case. Immediate intercept.',
    caseRef: 'AMB/2026/AHM/004',
    addedBy: 'Control Room',
    addedAt: atToday(6, 5, 0, 0),
    active: true,
    contact: 'Control Room — 112',
  },
  {
    id: 'wl-005',
    plate: 'GJ06KL2211',
    category: 'PERSON OF INTEREST',
    severity: 'LOW',
    reason: 'Surveillance request — movement logging only, no intercept.',
    caseRef: 'SUR/2026/SB/0231',
    addedBy: 'Special Branch',
    addedAt: atToday(16, 20, 0, -5),
    active: true,
  },
  {
    id: 'wl-006',
    plate: 'GJ03DT5566',
    category: 'EXPIRED PERMIT',
    severity: 'LOW',
    reason: 'Goods carrier operating with lapsed fitness certificate.',
    caseRef: 'RTO/FC/2026/1902',
    addedBy: 'RTO Enforcement',
    addedAt: atToday(10, 45, 0, -12),
    active: true,
  },
  {
    id: 'wl-007',
    plate: 'GJ12PQ8899',
    category: 'STOLEN VEHICLE',
    severity: 'HIGH',
    reason: 'Two-wheeler stolen from Kalupur station parking.',
    caseRef: 'FIR/2026/KLP/0338',
    addedBy: 'Railway Police',
    addedAt: atToday(20, 10, 0, -2),
    active: true,
  },
  {
    id: 'wl-008',
    plate: 'GJ21RS3344',
    category: 'BLACKLISTED',
    severity: 'MEDIUM',
    reason: 'Unauthorised commercial operation inside restricted zone.',
    caseRef: 'AMC/EN/2026/0771',
    addedBy: 'Municipal Enforcement',
    addedAt: atToday(13, 30, 0, -6),
    active: true,
  },
  {
    id: 'wl-009',
    plate: 'GJ16TU9090',
    category: 'WANTED SUSPECT',
    severity: 'HIGH',
    reason: 'Absconding accused — vehicle registered to known address.',
    caseRef: 'CR/2026/NRD/0455',
    addedBy: 'Insp. S. Vaghela',
    addedAt: atToday(8, 0, 0, -10),
    active: true,
  },
  {
    id: 'wl-010',
    plate: 'GJ09VW1212',
    category: 'STOLEN VEHICLE',
    severity: 'HIGH',
    reason: 'Recovered on 28th — record retained for audit.',
    caseRef: 'FIR/2026/VTV/0119',
    addedBy: 'Vatva PS',
    addedAt: atToday(7, 25, 0, -20),
    active: false,
  },
];

export const watchlistByPlate = (plate: string): WatchlistRecord | undefined =>
  mockWatchlist.find((w) => w.plate === plate.toUpperCase());

export const activeWatchlistPlates = mockWatchlist.filter((w) => w.active).map((w) => w.plate);
