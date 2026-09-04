import type { EventFilters, Paginated, VehicleEvent } from '@/types';
import { get, isMockMode } from './api';
import * as mock from '@/mocks/mockBackend';
import {
  getCameraIndex,
  mapPage,
  mapVehicleEvent,
  type PageDto,
  type VehicleEventDto,
} from './backendAdapter';

const normalise = (s: string) => s.toUpperCase().replace(/[^A-Z0-9]/g, '');

/** Map UI filters onto the backend's documented query parameters. */
function toParams(f: EventFilters, page: number, pageSize: number) {
  const p: Record<string, string | number | boolean> = { page, size: pageSize };
  if (f.plate) p.plate_number = normalise(f.plate);
  if (f.cameraId && f.cameraId !== 'ALL') p.camera_id = f.cameraId;
  if (f.eventType === 'WATCHLIST_MATCH' || f.watchlistOnly) p.watchlist_match = true;
  if (f.severity && f.severity !== 'ALL') p.severity = f.severity;
  if (f.dateFrom) p.from_time = `${f.dateFrom}T${f.timeFrom ?? '00:00'}:00`;
  if (f.dateTo) p.to_time = `${f.dateTo}T${f.timeTo ?? '23:59'}:59`;
  return p;
}

export const eventService = {
  async search(
    filters: EventFilters = {},
    page = 1,
    pageSize = 25,
  ): Promise<Paginated<VehicleEvent>> {
    if (isMockMode) return mock.getEvents(filters, page, pageSize);
    const [raw, cameras] = await Promise.all([
      get<PageDto<VehicleEventDto>>('/events', { params: toParams(filters, page, pageSize) }),
      getCameraIndex(),
    ]);
    return { ...mapPage(raw), items: raw.items.map((e) => mapVehicleEvent(e, cameras)) };
  },

  async recent(limit = 20): Promise<VehicleEvent[]> {
    if (isMockMode) return mock.getRecentEvents(limit);
    const [raw, cameras] = await Promise.all([
      get<PageDto<VehicleEventDto>>('/events', { params: { size: Math.min(limit, 100) } }),
      getCameraIndex(),
    ]);
    return raw.items.map((e) => mapVehicleEvent(e, cameras));
  },

  async byCamera(cameraId: string, limit = 25): Promise<VehicleEvent[]> {
    if (isMockMode) return mock.getEventsByCamera(cameraId, limit);
    const [raw, cameras] = await Promise.all([
      get<PageDto<VehicleEventDto>>('/events', {
        params: { camera_id: cameraId, size: Math.min(limit, 100) },
      }),
      getCameraIndex(),
    ]);
    return raw.items.map((e) => mapVehicleEvent(e, cameras));
  },

  async byId(id: string): Promise<VehicleEvent> {
    if (isMockMode) return mock.getEvent(id);
    const [raw, cameras] = await Promise.all([
      get<VehicleEventDto>(`/events/${encodeURIComponent(id)}`),
      getCameraIndex(),
    ]);
    return mapVehicleEvent(raw, cameras);
  },
};
