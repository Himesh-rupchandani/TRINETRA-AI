import type { VehicleEvent, VehicleProfile, VehicleRoute, WatchlistRecord } from '@/types';
import { get, isMockMode } from './api';
import * as mock from '@/mocks/mockBackend';
import {
  cameraDirectory,
  toVehicleEvent,
  toVehicleProfile,
  toVehicleRoute,
  toWatchlistRecord,
  type RouteDto,
  type VehicleEventDto,
  type WatchlistDto,
} from './adapters';
import { normalisePlate } from '@/lib/utils';

interface ProfileDto {
  plate_number: string;
  vehicle_class?: string | null;
  first_seen?: string | null;
  last_seen?: string | null;
  total_sightings: number;
  cameras_touched: number;
  watchlist?: WatchlistDto | null;
}

interface EventsDto {
  items: VehicleEventDto[];
  total: number;
}

interface WatchlistListDto {
  items: WatchlistDto[];
}

export const vehicleService = {
  async events(plate: string): Promise<VehicleEvent[]> {
    const p = normalisePlate(plate);
    if (isMockMode) return mock.getVehicleEvents(p);
    const [res, dir] = await Promise.all([
      get<EventsDto>(`/vehicles/${encodeURIComponent(p)}/events`, { params: { size: 100 } }),
      cameraDirectory().catch(() => null),
    ]);
    // Backend caps a page at 100 sightings; the investigation timeline stays
    // chronological (asc) exactly as delivered.
    return (res.items ?? []).map((dto) => toVehicleEvent(dto, dir));
  },

  async route(plate: string): Promise<VehicleRoute> {
    const p = normalisePlate(plate);
    if (isMockMode) return mock.getVehicleRoute(p);
    const dir = await cameraDirectory().catch(() => null);
    return toVehicleRoute(await get<RouteDto>(`/vehicles/${encodeURIComponent(p)}/route`), dir);
  },

  async profile(plate: string): Promise<VehicleProfile | null> {
    const p = normalisePlate(plate);
    if (isMockMode) return mock.getVehicleProfile(p);
    return toVehicleProfile(await get<ProfileDto>(`/vehicles/${encodeURIComponent(p)}`));
  },

  async watchlist(): Promise<WatchlistRecord[]> {
    if (isMockMode) return mock.getWatchlist();
    const res = await get<WatchlistListDto | WatchlistDto[]>('/watchlist', {
      params: { size: 100 }, // backend caps page size at 100
    });
    const items = Array.isArray(res) ? res : (res.items ?? []);
    return items.map(toWatchlistRecord);
  },
};
