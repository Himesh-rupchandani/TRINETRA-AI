import type { VehicleEvent, VehicleProfile, VehicleRoute, WatchlistRecord } from '@/types';
import { get, isMockMode } from './api';
import * as mock from '@/mocks/mockBackend';
import { normalisePlate } from '@/lib/utils';
import {
  getCameraIndex,
  mapVehicleEvent,
  mapVehicleRoute,
  mapWatchlist,
  profileFromEvents,
  type PageDto,
  type RouteDto,
  type VehicleEventDto,
  type WatchlistDto,
} from './backendAdapter';

export const vehicleService = {
  async events(plate: string): Promise<VehicleEvent[]> {
    const p = normalisePlate(plate);
    if (isMockMode) return mock.getVehicleEvents(p);
    const [page, cameras] = await Promise.all([
      get<PageDto<VehicleEventDto>>(`/vehicles/${p}/events`, { params: { size: 100 } }),
      getCameraIndex(),
    ]);
    return page.items.map((e) => mapVehicleEvent(e, cameras));
  },

  async route(plate: string): Promise<VehicleRoute> {
    const p = normalisePlate(plate);
    if (isMockMode) return mock.getVehicleRoute(p);
    // Backend owns the chronological sequencing; the event list supplies the
    // event IDs (for evidence + detection links) and the camera index the names.
    const [route, events, cameras] = await Promise.all([
      get<RouteDto>(`/vehicles/${p}/route`),
      this.events(p),
      getCameraIndex(),
    ]);
    return mapVehicleRoute(route, events, cameras);
  },

  async profile(plate: string): Promise<VehicleProfile | null> {
    const p = normalisePlate(plate);
    if (isMockMode) return mock.getVehicleProfile(p);
    const [events, watchlist] = await Promise.all([this.events(p), this.watchlist()]);
    const wl = watchlist.find((w) => w.plate === p && w.active) ?? null;
    return profileFromEvents(p, events, wl);
  },

  async watchlist(): Promise<WatchlistRecord[]> {
    if (isMockMode) return mock.getWatchlist();
    const page = await get<PageDto<WatchlistDto>>('/watchlist', { params: { size: 100 } });
    return page.items.map(mapWatchlist);
  },
};


