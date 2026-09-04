import type { EventFilters, Paginated, VehicleEvent } from '@/types';
import { get, isMockMode } from './api';
import * as mock from '@/mocks/mockBackend';
import { mapEvent, unwrapList, unwrapPaginated } from './adapters';

/**
 * Translate the UI's filter vocabulary onto the query parameters the events
 * endpoint actually accepts. Filters the API cannot express (event type,
 * severity, time-of-day) are applied client-side after the page is fetched,
 * rather than being silently dropped.
 */
function toParams(f: EventFilters, page: number, pageSize: number) {
  const p: Record<string, string | number | boolean> = { page, size: pageSize };
  if (f.plate) p.plate_number = f.plate;
  if (f.cameraId && f.cameraId !== 'ALL') p.camera_id = f.cameraId;
  if (f.watchlistOnly) p.watchlist_match = true;
  const from = [f.dateFrom, f.timeFrom].filter(Boolean).join(f.timeFrom ? 'T' : '');
  const to = [f.dateTo, f.timeTo].filter(Boolean).join(f.timeTo ? 'T' : '');
  if (from) p.from_time = from;
  if (to) p.to_time = to;
  return p;
}

/** Client-side pass for the filters the REST endpoint does not support. */
function applyLocalFilters(events: VehicleEvent[], f: EventFilters): VehicleEvent[] {
  return events.filter((e) => {
    if (f.eventType && f.eventType !== 'ALL' && e.eventType !== f.eventType) return false;
    if (f.severity && f.severity !== 'ALL' && e.severity !== f.severity) return false;
    return true;
  });
}

export const eventService = {
  async search(
    filters: EventFilters = {},
    page = 1,
    pageSize = 25,
  ): Promise<Paginated<VehicleEvent>> {
    if (isMockMode) return mock.getEvents(filters, page, pageSize);
    const result = unwrapPaginated(await get<unknown>('/events', {
      params: toParams(filters, page, pageSize),
    }), mapEvent);
    return { ...result, items: applyLocalFilters(result.items, filters) };
  },

  async recent(limit = 20): Promise<VehicleEvent[]> {
    if (isMockMode) return mock.getRecentEvents(limit);
    // The list endpoint is newest-first by default.
    return unwrapList(await get<unknown>('/events', { params: { size: limit, page: 1 } }))
      .map(mapEvent)
      .slice(0, limit);
  },

  async byCamera(cameraId: string, limit = 25): Promise<VehicleEvent[]> {
    if (isMockMode) return mock.getEventsByCamera(cameraId, limit);
    return unwrapList(await get<unknown>('/events', {
      params: { camera_id: cameraId, size: limit, page: 1 },
    }))
      .map(mapEvent)
      .slice(0, limit);
  },

  async byId(id: string): Promise<VehicleEvent> {
    if (isMockMode) return mock.getEvent(id);
    return mapEvent(await get<Record<string, unknown>>(`/events/${encodeURIComponent(id)}`));
  },
};
