import type { EventFilters, Paginated, VehicleEvent } from '@/types';
import { get, isMockMode } from './api';
import * as mock from '@/mocks/mockBackend';
import { cameraDirectory, toPaginated, toVehicleEvent, type VehicleEventDto } from './adapters';
import { normalisePlate } from '@/lib/utils';

interface PaginatedEventsDto {
  items: VehicleEventDto[];
  total: number;
  page: number;
  size: number;
}

/**
 * Map frontend filter names onto the backend query contract
 * (camera_id / plate_number / watchlist_match / from_time / to_time / size).
 */
function toParams(f: EventFilters, page: number, pageSize: number) {
  const p: Record<string, string | number> = { page, size: pageSize };
  if (f.plate) p.plate_number = normalisePlate(f.plate);
  if (f.cameraId && f.cameraId !== 'ALL') p.camera_id = f.cameraId;
  if (f.watchlistOnly) p.watchlist_match = 'true';
  if (f.dateFrom) p.from_time = f.timeFrom ? `${f.dateFrom}T${f.timeFrom}` : `${f.dateFrom}T00:00:00`;
  if (f.dateTo) p.to_time = f.timeTo ? `${f.dateTo}T${f.timeTo}` : `${f.dateTo}T23:59:59`;
  return p;
}

export const eventService = {
  async search(
    filters: EventFilters = {},
    page = 1,
    pageSize = 25,
  ): Promise<Paginated<VehicleEvent>> {
    if (isMockMode) return mock.getEvents(filters, page, pageSize);

    const [res, dir] = await Promise.all([
      get<PaginatedEventsDto>('/events', { params: toParams(filters, page, pageSize) }),
      cameraDirectory().catch(() => null),
    ]);
    let result = toPaginated(res, (dto) => toVehicleEvent(dto, dir));
    // eventType/severity are UI-level facets over the same rows — applied
    // client-side so live and demo filtering behave identically.
    if (filters.eventType && filters.eventType !== 'ALL') {
      result = {
        ...result,
        items: result.items.filter((e) => e.eventType === filters.eventType),
        total: result.items.length,
      };
    }
    if (filters.severity && filters.severity !== 'ALL') {
      const keep = result.items.filter((e) => (e.severity ?? 'INFO') === filters.severity);
      result = { ...result, items: keep, total: keep.length };
    }
    return result;
  },

  async recent(limit = 20): Promise<VehicleEvent[]> {
    if (isMockMode) return mock.getRecentEvents(limit);
    // The backend rejects size > 100 — clamp instead of erroring the dashboard.
    const size = Math.min(limit, 100);
    const [res, dir] = await Promise.all([
      get<PaginatedEventsDto>('/events', { params: { page: 1, size } }),
      cameraDirectory().catch(() => null),
    ]);
    return (res.items ?? []).map((dto) => toVehicleEvent(dto, dir));
  },

  async byCamera(cameraId: string, limit = 25): Promise<VehicleEvent[]> {
    if (isMockMode) return mock.getEventsByCamera(cameraId, limit);
    const [res, dir] = await Promise.all([
      get<PaginatedEventsDto>('/events', {
        params: { camera_id: cameraId, page: 1, size: Math.min(limit, 100) },
      }),
      cameraDirectory().catch(() => null),
    ]);
    return (res.items ?? []).map((dto) => toVehicleEvent(dto, dir));
  },

  async byId(id: string): Promise<VehicleEvent> {
    if (isMockMode) return mock.getEvent(id);
    const [dto, dir] = await Promise.all([
      get<VehicleEventDto>(`/events/${encodeURIComponent(id)}`),
      cameraDirectory().catch(() => null),
    ]);
    return toVehicleEvent(dto, dir);
  },
};
