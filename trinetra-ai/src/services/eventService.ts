import type { EventFilters, Paginated, VehicleEvent } from '@/types';
import { get, isMockMode } from './api';
import * as mock from '@/mocks/mockBackend';
import { normalisePlate } from '@/lib/utils';
import { cameraService } from './cameraService';
import {
  toVehicleEvent,
  unwrapList,
  withCameraContext,
  type Envelope,
  type VehicleEventDto,
} from './adapters';

/**
 * Translate UI filters into the backend's query contract
 * (`camera_id`, `plate_number`, `watchlist_match`, `from_time`, `to_time`).
 */
function toParams(f: EventFilters, page: number, pageSize: number) {
  const p: Record<string, string | number | boolean> = { page, size: pageSize };
  if (f.plate) p.plate_number = normalisePlate(f.plate);
  if (f.cameraId && f.cameraId !== 'ALL') p.camera_id = f.cameraId;
  if (f.watchlistOnly) p.watchlist_match = true;

  // The backend filters on a single datetime range; combine the date + time inputs.
  if (f.dateFrom) p.from_time = `${f.dateFrom}T${f.timeFrom || '00:00'}:00`;
  if (f.dateTo) p.to_time = `${f.dateTo}T${f.timeTo || '23:59'}:59`;
  return p;
}

/** Filters the backend cannot express are applied client-side on the page. */
function applyLocalFilters(rows: VehicleEvent[], f: EventFilters): VehicleEvent[] {
  return rows.filter((e) => {
    if (f.eventType && f.eventType !== 'ALL' && e.eventType !== f.eventType) return false;
    if (f.severity && f.severity !== 'ALL' && (e.severity ?? 'INFO') !== f.severity) return false;
    return true;
  });
}

async function fetchEvents(
  params: Record<string, string | number | boolean>,
): Promise<{ rows: VehicleEvent[]; total: number }> {
  const [raw, cameras] = await Promise.all([
    get<unknown>('/events', { params }),
    cameraService.index(),
  ]);
  const envelope = (raw ?? {}) as Envelope<VehicleEventDto>;
  const rows = withCameraContext(unwrapList<VehicleEventDto>(raw).map(toVehicleEvent), cameras);
  return { rows, total: envelope.total ?? rows.length };
}

export const eventService = {
  async search(
    filters: EventFilters = {},
    page = 1,
    pageSize = 25,
  ): Promise<Paginated<VehicleEvent>> {
    if (isMockMode) return mock.getEvents(filters, page, pageSize);

    const { rows, total } = await fetchEvents(toParams(filters, page, pageSize));
    return { items: applyLocalFilters(rows, filters), total, page, pageSize };
  },

  async recent(limit = 20): Promise<VehicleEvent[]> {
    if (isMockMode) return mock.getRecentEvents(limit);
    // The backend already orders by event_time DESC.
    const { rows } = await fetchEvents({ page: 1, size: limit });
    return rows;
  },

  async byCamera(cameraId: string, limit = 25): Promise<VehicleEvent[]> {
    if (isMockMode) return mock.getEventsByCamera(cameraId, limit);
    const { rows } = await fetchEvents({ camera_id: cameraId, page: 1, size: limit });
    return rows;
  },

  /**
   * Single event lookup. The backend has no `/events/{id}` resource, so we
   * resolve it from the most recent page rather than inventing an endpoint.
   */
  async byId(id: string): Promise<VehicleEvent> {
    if (isMockMode) return mock.getEvent(id);
    const { rows } = await fetchEvents({ page: 1, size: 100 });
    const found = rows.find((e) => e.id === String(id));
    if (!found) throw new Error(`Event ${id} not found`);
    return found;
  },
};
