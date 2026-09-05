import type { OfficerProfile } from '@/types';

/** The profile data for the currently signed-in officer. */
export const currentOfficerProfile: OfficerProfile = {
  name: 'System Operator',
  photoUrl: '/officer-profile.svg',
  policeId: 'TRI-POL-001',
  totalVehiclesCaught: 6,
  totalChallansGiven: 4,
  totalChallanAmount: 24000,
  totalAmountCollected: 18000,
  netRevenue: 18000,
  vehicleNumberPlates: [
    'GJ01AB1234',
    'GJ05XY4321',
    'GJ18MH0099',
    'GJ01ZZ0001',
    'GJ06SS1111',
    'GJ01QQ9988',
  ],
};
