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

/** The officer currently logged into the control room (the Senior Officer). */
export const currentOfficerId = 'OFF-02471';

export const mockOfficers: OfficerProfile[] = [
  buildOfficer({
    officerId: 'OFF-02471',
    name: 'Insp. Anjali Deshmukh',
    photoUrl: '/officer-profile.jpg',
    policeId: 'GJ-02471',
    department: 'Gujarat Police · Traffic Control',
    designation: 'Senior Officer',
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
    officerId: 'OFF-05118',
    name: 'SI Priya Sharma',
    photoUrl: '/officers/priya-sharma.jpg',
    policeId: 'GJ-05118',
    department: 'Gujarat Police · Traffic Control',
    designation: 'Junior Officer',
    plates: ['GJ01CD2345', 'GJ05LM7788', 'GJ27AK9021', 'MH04TR6610', 'GJ11GH3302', 'GJ01ZX5570'],
    challans: [
      { plate: 'GJ01CD2345', amount: 1000, amountPaid: 1000, status: 'PAID' },
      { plate: 'GJ05LM7788', amount: 2000, amountPaid: 2000, status: 'PAID' },
      { plate: 'GJ27AK9021', amount: 500, amountPaid: 0, status: 'PENDING' },
      { plate: 'MH04TR6610', amount: 5000, amountPaid: 2500, status: 'PARTIAL' },
      { plate: 'GJ11GH3302', amount: 1500, amountPaid: 1500, status: 'PAID' },
      { plate: 'GJ01ZX5570', amount: 1000, amountPaid: 1000, status: 'PAID' },
      { plate: 'GJ05LM7788', amount: 500, amountPaid: 500, status: 'PAID' },
      { plate: 'GJ01CD2345', amount: 2000, amountPaid: 0, status: 'PENDING' },
    ],
  }),
  buildOfficer({
    officerId: 'OFF-05342',
    name: 'SI Rahul Patel',
    photoUrl: '/officers/rahul-patel.jpg',
    policeId: 'GJ-05342',
    department: 'Gujarat Police · Traffic Control',
    designation: 'Junior Officer',
    plates: ['GJ02MN5588', 'GJ21CV1190', 'MH14KD7788', 'GJ08HP3160', 'GJ16FE2231', 'RJ27PQ4410', 'GJ03YT8891'],
    challans: [
      { plate: 'GJ02MN5588', amount: 1000, amountPaid: 1000, status: 'PAID' },
      { plate: 'GJ21CV1190', amount: 500, amountPaid: 0, status: 'PENDING' },
      { plate: 'MH14KD7788', amount: 2000, amountPaid: 2000, status: 'PAID' },
      { plate: 'GJ08HP3160', amount: 1500, amountPaid: 750, status: 'PARTIAL' },
      { plate: 'GJ16FE2231', amount: 3000, amountPaid: 3000, status: 'PAID' },
      { plate: 'RJ27PQ4410', amount: 5000, amountPaid: 0, status: 'PENDING' },
      { plate: 'GJ03YT8891', amount: 1000, amountPaid: 1000, status: 'PAID' },
      { plate: 'GJ16FE2231', amount: 500, amountPaid: 500, status: 'PAID' },
      { plate: 'GJ02MN5588', amount: 2000, amountPaid: 2000, status: 'PAID' },
    ],
  }),
  buildOfficer({
    officerId: 'OFF-06077',
    name: 'ASI Amit Kumar',
    photoUrl: '/officers/amit-kumar.jpg',
    policeId: 'GJ-06077',
    department: 'Gujarat Police · Traffic Control',
    designation: 'Junior Officer',
    plates: ['GJ06KL4412', 'GJ18BN7720', 'MH02WE9034', 'GJ09OP1178', 'GJ01QA6655'],
    challans: [
      { plate: 'GJ06KL4412', amount: 500, amountPaid: 500, status: 'PAID' },
      { plate: 'GJ18BN7720', amount: 1000, amountPaid: 1000, status: 'PAID' },
      { plate: 'MH02WE9034', amount: 2000, amountPaid: 1000, status: 'PARTIAL' },
      { plate: 'GJ09OP1178', amount: 1500, amountPaid: 0, status: 'PENDING' },
      { plate: 'GJ01QA6655', amount: 1000, amountPaid: 1000, status: 'PAID' },
      { plate: 'GJ06KL4412', amount: 2000, amountPaid: 2000, status: 'PAID' },
    ],
  }),
  buildOfficer({
    officerId: 'OFF-06215',
    name: 'ASI Neha Joshi',
    photoUrl: '/officers/neha-joshi.jpg',
    policeId: 'GJ-06215',
    department: 'Gujarat Police · Traffic Control',
    designation: 'Junior Officer',
    plates: ['GJ05RS9910', 'GJ12TY2288', 'GJ03UI7734', 'RJ14ER3306', 'GJ07DF5521', 'GJ01HJ0087'],
    challans: [
      { plate: 'GJ05RS9910', amount: 1000, amountPaid: 1000, status: 'PAID' },
      { plate: 'GJ12TY2288', amount: 500, amountPaid: 500, status: 'PAID' },
      { plate: 'GJ03UI7734', amount: 5000, amountPaid: 5000, status: 'PAID' },
      { plate: 'RJ14ER3306', amount: 2000, amountPaid: 0, status: 'PENDING' },
      { plate: 'GJ07DF5521', amount: 1500, amountPaid: 500, status: 'PARTIAL' },
      { plate: 'GJ01HJ0087', amount: 1000, amountPaid: 1000, status: 'PAID' },
      { plate: 'GJ12TY2288', amount: 1000, amountPaid: 0, status: 'PENDING' },
    ],
  }),
  buildOfficer({
    officerId: 'OFF-07430',
    name: 'HC Vikram Singh',
    photoUrl: '/officers/vikram-singh.jpg',
    policeId: 'GJ-07430',
    department: 'Gujarat Police · Traffic Control',
    designation: 'Police Officer',
    plates: ['GJ01VB3345', 'GJ08NM6612', 'GJ15CX8890', 'MH12LK2207'],
    challans: [
      { plate: 'GJ01VB3345', amount: 500, amountPaid: 500, status: 'PAID' },
      { plate: 'GJ08NM6612', amount: 1000, amountPaid: 1000, status: 'PAID' },
      { plate: 'GJ15CX8890', amount: 2000, amountPaid: 0, status: 'PENDING' },
      { plate: 'MH12LK2207', amount: 1500, amountPaid: 1500, status: 'PAID' },
      { plate: 'GJ01VB3345', amount: 1000, amountPaid: 500, status: 'PARTIAL' },
    ],
  }),
];

export function officerById(id: string): OfficerProfile | undefined {
  return mockOfficers.find((o) => o.officerId === id);
}
