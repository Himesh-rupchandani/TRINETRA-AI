import type { VehicleEvent, VehicleProfile, VehicleRoute, WatchlistRecord } from '@/types';
import { get, isMockMode } from './api';
import * as mock from '@/mocks/mockBackend';
import { normalisePlate } from '@/lib/utils';

export const vehicleService = {
  events(plate: string): Promise<VehicleEvent[]> {
    const p = normalisePlate(plate);
    return isMockMode ? mock.getVehicleEvents(p) : get<VehicleEvent[]>(`/vehicles/${p}/events`);
  },

  route(plate: string): Promise<VehicleRoute> {
    const p = normalisePlate(plate);
    return isMockMode ? mock.getVehicleRoute(p) : get<VehicleRoute>(`/vehicles/${p}/route`);
  },

  profile(plate: string): Promise<VehicleProfile | null> {
    const p = normalisePlate(plate);
    return isMockMode ? mock.getVehicleProfile(p) : get<VehicleProfile | null>(`/vehicles/${p}`);
  },

  watchlist(): Promise<WatchlistRecord[]> {
    return isMockMode ? mock.getWatchlist() : get<WatchlistRecord[]>('/watchlist');
  },
};
