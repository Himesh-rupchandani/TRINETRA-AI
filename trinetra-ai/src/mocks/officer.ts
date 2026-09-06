import type { OfficerProfile } from '@/types';

/**
 * MOCK OFFICER DATA
 * -----------------
 * Synthetic officer records for the Profile section. Each officer is built
 * from their own plate + challan records, and every statistic is derived only
 * from that officer's own data — figures for different officers are never
 * mixed. The live backend is expected to behave the same way per officer.
 */

type ChallanStatus = 'PAID' | 'PARTIAL' | 'PENDING';

interface Challan {
  plate: string;
  amount: number;
  amountPaid: number;
  status: ChallanStatus;
}

interface OfficerSeed {
  officerId: string;
  name: string;
  photoUrl: string;
  policeId: string;
  department: string;
  designation: string;
  plates: string[];
  challans: Challan[];
}

/** Derives an officer's aggregate figures from only their own records. */
function buildOfficer(seed: OfficerSeed): OfficerProfile {
  const plates = Array.from(new Set(seed.plates));
  const totalChallanAmount = seed.challans.reduce((s, c) => s + c.amount, 0);
  const totalAmountCollected = seed.challans.reduce((s, c) => s + c.amountPaid, 0);
  const netRevenue = seed.challans
    .filter((c) => c.status === 'PAID')
    .reduce((s, c) => s + c.amountPaid, 0);

  return {
    officerId: seed.officerId,
    name: seed.name,
    photoUrl: seed.photoUrl,
    policeId: seed.policeId,
    department: seed.department,
    designation: seed.designation,
    vehiclesCaught: plates.length,
    totalChallans: seed.challans.length,
    totalChallanAmount,
    totalAmountCollected,
    netRevenue,
    plates,
  };
}

/** The officer currently logged into the control room. */
export const currentOfficerId = 'OFF-02471';

export const mockOfficers: OfficerProfile[] = [
  buildOfficer({
    officerId: 'OFF-02471',
    name: 'Insp. Anjali Deshmukh',
    photoUrl: '/officer-profile.jpg',
    policeId: 'GJ-02471',
    department: 'Gujarat Police · Traffic Control',
    designation: 'Inspector',
    plates: [
      'GJ01AB1234',
      'GJ05XY4321',
      'GJ18MH0099',
      'GJ03JK6671',
      'GJ06RT2210',
      'MH12QE3344',
      'GJ12PL8080',
      'GJ09WD5543',
      'RJ14TU7071',
      'GJ07BM4412',
    ],
    challans: [
      { plate: 'GJ01AB1234', amount: 2000, amountPaid: 2000, status: 'PAID' },
      { plate: 'GJ05XY4321', amount: 5000, amountPaid: 5000, status: 'PAID' },
      { plate: 'GJ18MH0099', amount: 1000, amountPaid: 1000, status: 'PAID' },
      { plate: 'GJ03JK6671', amount: 1500, amountPaid: 1500, status: 'PAID' },
      { plate: 'GJ06RT2210', amount: 500, amountPaid: 500, status: 'PAID' },
      { plate: 'MH12QE3344', amount: 2000, amountPaid: 0, status: 'PENDING' },
      { plate: 'GJ12PL8080', amount: 500, amountPaid: 500, status: 'PAID' },
      { plate: 'GJ09WD5543', amount: 2000, amountPaid: 1000, status: 'PARTIAL' },
      { plate: 'RJ14TU7071', amount: 5000, amountPaid: 0, status: 'PENDING' },
      { plate: 'GJ01AB1234', amount: 1000, amountPaid: 1000, status: 'PAID' },
      { plate: 'GJ05XY4321', amount: 1500, amountPaid: 1500, status: 'PAID' },
      { plate: 'GJ03JK6671', amount: 1000, amountPaid: 0, status: 'PENDING' },
      { plate: 'GJ07BM4412', amount: 3000, amountPaid: 3000, status: 'PAID' },
      { plate: 'GJ06RT2210', amount: 500, amountPaid: 500, status: 'PAID' },
    ],
  }),
  buildOfficer({
    officerId: 'OFF-04192',
    name: 'SI. Vikram Rathod',
    photoUrl: '/officer-profile.jpg',
    policeId: 'GJ-04192',
    department: 'Gujarat Police · Traffic Control',
    designation: 'Sub-Inspector',
    plates: ['GJ02MN5588', 'GJ21CV1190', 'MH14KD7788', 'GJ08HP31600'],
    challans: [
      { plate: 'GJ02MN5588', amount: 1000, amountPaid: 1000, status: 'PAID' },
      { plate: 'GJ21CV1190', amount: 500, amountPaid: 0, status: 'PENDING' },
      { plate: 'MH14KD7788', amount: 2000, amountPaid: 2000, status: 'PAID' },
      { plate: 'GJ08HP31600', amount: 1500, amountPaid: 750, status: 'PARTIAL' },
    ],
  }),
];

export function officerById(id: string): OfficerProfile | undefined {
  return mockOfficers.find((o) => o.officerId === id);
}
