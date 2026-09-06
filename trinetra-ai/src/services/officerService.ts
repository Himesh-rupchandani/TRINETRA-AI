import type { OfficerProfile } from '@/types';
import { get, isMockMode } from './api';
import * as mock from '@/mocks/mockBackend';

/**
 * Backend DTO for an officer's own profile. The backend returns only the
 * requesting officer's figures (never another officer's data).
 */
interface OfficerDto {
  officer_id: string;
  name: string;
  photo_url: string;
  police_id: string;
  department: string;
  designation: string;
  /** Rank/position label; falls back to the designation when absent. */
  position?: string;
  vehicles_caught: number;
  total_challans: number;
  total_challan_amount: number;
  total_amount_collected: number;
  net_revenue: number;
  plates: string[];
}

function toOfficerProfile(dto: OfficerDto): OfficerProfile {
  return {
    officerId: dto.officer_id,
    name: dto.name,
    photoUrl: dto.photo_url,
    policeId: dto.police_id,
    department: dto.department,
    designation: dto.designation,
    position: dto.position ?? dto.designation,
    vehiclesCaught: dto.vehicles_caught,
    totalChallans: dto.total_challans,
    totalChallanAmount: dto.total_challan_amount,
    totalAmountCollected: dto.total_amount_collected,
    netRevenue: dto.net_revenue,
    plates: dto.plates ?? [],
  };
}

export const officerService = {
  /** Profile for the officer currently signed in. */
  async current(): Promise<OfficerProfile> {
    if (isMockMode) return mock.getCurrentOfficer();
    return toOfficerProfile(await get<OfficerDto>('/officers/me'));
  },

  /** Profile for a specific officer (their own data only). */
  async byId(id: string): Promise<OfficerProfile> {
    if (isMockMode) return mock.getOfficerProfile(id);
    return toOfficerProfile(await get<OfficerDto>(`/officers/${encodeURIComponent(id)}`));
  },

  /** Roster the control room can switch between. */
  async list(): Promise<OfficerProfile[]> {
    if (isMockMode) return mock.listOfficers();
    const res = await get<OfficerDto[] | { items: OfficerDto[] }>('/officers');
    const items = Array.isArray(res) ? res : (res.items ?? []);
    return items.map(toOfficerProfile);
  },
};
