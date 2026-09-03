import type { EventFilters, Paginated, VehicleEvent } from '@/types';
import { get, isMockMode } from './api';
import * as mock from '@/mocks/mockBackend';

function toParams(f: EventFilters, page: number, pageSize: number) {
  const p: Record<string, string | number | boolean> = { page, pageSize };
  Object.entries(f).forEach(([k, v]) => {
    if (v !== undefined && v !== '' && v !== 'ALL' && v !== false) p[k] = v as string;
  });
  return p;
}

export const eventService = {
  search(filters: EventFilters = {}, page = 1, pageSize = 25): Promise<Paginated<VehicleEvent>> {
    return isMockMode
      ? mock.getEvents(filters, page, pageSize)
      : get<Paginated<VehicleEvent>>('/events', { params: toParams(filters, page, pageSize) });
  },

  recent(limit = 20): Promise<VehicleEvent[]> {
    return isMockMode
      ? mock.getRecentEvents(limit)
      : get<VehicleEvent[]>('/events', { params: { limit, sort: 'desc' } }).then((r) =>
          Array.isArray(r) ? r : [],
        );
  },

  byCamera(cameraId: string, limit = 25): Promise<VehicleEvent[]> {
    return isMockMode
      ? mock.getEventsByCamera(cameraId, limit)
      : get<VehicleEvent[]>('/events', { params: { cameraId, limit } });
  },

  byId(id: string): Promise<VehicleEvent> {
    return isMockMode ? mock.getEvent(id) : get<VehicleEvent>(`/events/${encodeURIComponent(id)}`);
  },
};
