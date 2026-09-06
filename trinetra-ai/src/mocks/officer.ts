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
  position: string;
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
    position: seed.position,
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

const DEPARTMENT = 'Gujarat Police · Traffic Control';

export const mockOfficers: OfficerProfile[] = [
  buildOfficer({
    officerId: 'OFF-02471',
    name: 'Insp. Anjali Deshmukh',
    photoUrl: '/officer-profile.jpg',
    policeId: 'GJ-02471',
    department: DEPARTMENT,
    designation: 'Inspector',
    position: 'Senior Officer',
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
    officerId: 'OFF-03318',
    name: 'Insp. Priya Sharma',
    photoUrl: '/officers/priya-sharma.jpg',
    policeId: 'GJ-03318',
    department: DEPARTMENT,
    designation: 'Inspector',
    position: 'Senior Officer',
    plates: ['GJ01KL2277', 'GJ27NB9014', 'GJ05DC7742', 'MH02RS4108', 'GJ16TY6390', 'GJ11QA5528'],
    challans: [
      { plate: 'GJ01KL2277', amount: 3000, amountPaid: 3000, status: 'PAID' },
      { plate: 'GJ27NB9014', amount: 1500, amountPaid: 1500, status: 'PAID' },
      { plate: 'GJ05DC7742', amount: 2000, amountPaid: 1000, status: 'PARTIAL' },
      { plate: 'MH02RS4108', amount: 5000, amountPaid: 0, status: 'PENDING' },
      { plate: 'GJ16TY6390', amount: 1000, amountPaid: 1000, status: 'PAID' },
      { plate: 'GJ11QA5528', amount: 500, amountPaid: 500, status: 'PAID' },
      { plate: 'GJ01KL2277', amount: 1500, amountPaid: 1500, status: 'PAID' },
      { plate: 'GJ16TY6390', amount: 2000, amountPaid: 0, status: 'PENDING' },
    ],
  }),
  buildOfficer({
    officerId: 'OFF-04192',
    name: 'SI Rahul Patel',
    photoUrl: '/officers/rahul-patel.jpg',
    policeId: 'GJ-04192',
    department: DEPARTMENT,
    designation: 'Sub-Inspector',
    position: 'Police Officer',
    plates: ['GJ02MN5588', 'GJ21CV1190', 'MH14KD7788', 'GJ08HP3160'],
    challans: [
      { plate: 'GJ02MN5588', amount: 1000, amountPaid: 1000, status: 'PAID' },
      { plate: 'GJ21CV1190', amount: 500, amountPaid: 0, status: 'PENDING' },
      { plate: 'MH14KD7788', amount: 2000, amountPaid: 2000, status: 'PAID' },
      { plate: 'GJ08HP3160', amount: 1500, amountPaid: 750, status: 'PARTIAL' },
      { plate: 'GJ02MN5588', amount: 500, amountPaid: 500, status: 'PAID' },
    ],
  }),
  buildOfficer({
    officerId: 'OFF-05127',
    name: 'Insp. Amit Kumar',
    photoUrl: '/officers/amit-kumar.jpg',
    policeId: 'GJ-05127',
    department: DEPARTMENT,
    designation: 'Inspector',
    position: 'Senior Officer',
    plates: ['GJ04FG8821', 'GJ13ZP3376', 'RJ09LM2204', 'GJ18UV7719', 'GJ06EK4462', 'GJ23WX1085', 'MH31JN6603'],
    challans: [
      { plate: 'GJ04FG8821', amount: 2500, amountPaid: 2500, status: 'PAID' },
      { plate: 'GJ13ZP3376', amount: 1000, amountPaid: 1000, status: 'PAID' },
      { plate: 'RJ09LM2204', amount: 5000, amountPaid: 2500, status: 'PARTIAL' },
      { plate: 'GJ18UV7719', amount: 1500, amountPaid: 1500, status: 'PAID' },
      { plate: 'GJ06EK4462', amount: 2000, amountPaid: 0, status: 'PENDING' },
      { plate: 'GJ23WX1085', amount: 3000, amountPaid: 3000, status: 'PAID' },
      { plate: 'MH31JN6603', amount: 1000, amountPaid: 0, status: 'PENDING' },
      { plate: 'GJ04FG8821', amount: 500, amountPaid: 500, status: 'PAID' },
      { plate: 'GJ13ZP3376', amount: 2000, amountPaid: 2000, status: 'PAID' },
    ],
  }),
  buildOfficer({
    officerId: 'OFF-06044',
    name: 'SI Neha Joshi',
    photoUrl: '/officers/neha-joshi.jpg',
    policeId: 'GJ-06044',
    department: DEPARTMENT,
    designation: 'Sub-Inspector',
    position: 'Police Officer',
    plates: ['GJ10BQ3341', 'GJ15SD9962', 'GJ01YH5507'],
    challans: [
      { plate: 'GJ10BQ3341', amount: 1000, amountPaid: 1000, status: 'PAID' },
      { plate: 'GJ15SD9962', amount: 2000, amountPaid: 500, status: 'PARTIAL' },
      { plate: 'GJ01YH5507', amount: 500, amountPaid: 500, status: 'PAID' },
      { plate: 'GJ10BQ3341', amount: 1500, amountPaid: 0, status: 'PENDING' },
    ],
  }),
  buildOfficer({
    officerId: 'OFF-07310',
    name: 'Insp. Vikram Singh',
    photoUrl: '/officers/vikram-singh.jpg',
    policeId: 'GJ-07310',
    department: DEPARTMENT,
    designation: 'Inspector',
    position: 'Senior Officer',
    plates: ['GJ03TR6648', 'GJ07MG2295', 'GJ12AC8830', 'MH04PD1177', 'GJ19FS4423'],
    challans: [
      { plate: 'GJ03TR6648', amount: 5000, amountPaid: 5000, status: 'PAID' },
      { plate: 'GJ07MG2295', amount: 1500, amountPaid: 1500, status: 'PAID' },
      { plate: 'GJ12AC8830', amount: 2000, amountPaid: 1000, status: 'PARTIAL' },
      { plate: 'MH04PD1177', amount: 1000, amountPaid: 0, status: 'PENDING' },
      { plate: 'GJ19FS4423', amount: 2500, amountPaid: 2500, status: 'PAID' },
      { plate: 'GJ03TR6648', amount: 1000, amountPaid: 1000, status: 'PAID' },
      { plate: 'GJ07MG2295', amount: 500, amountPaid: 500, status: 'PAID' },
    ],
  }),
];

export function officerById(id: string): OfficerProfile | undefined {
  return mockOfficers.find((o) => o.officerId === id);
}
