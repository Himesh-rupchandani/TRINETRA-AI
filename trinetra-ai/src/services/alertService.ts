import type { Alert, AlertFilters } from '@/types';
import { get, post, isMockMode } from './api';
import * as mock from '@/mocks/mockBackend';
import { cameraService } from './cameraService';
import { mapAlert, unwrapList } from './adapters';

/**
 * Alert service.
 *
 * Alerts arrive from the API without camera metadata (it has no location
 * column), so we join the canonical camera registry here — the operator sees a
 * real junction name instead of a blank "Location", and the data still comes
 * from the single source of truth rather than being invented per-component.
 */
let cameraIndex: Promise<Map<string, { name: string; location: string; lat: number; lng: number }>> | null =
  null;

function camerasById() {
  if (!cameraIndex) {
    cameraIndex = cameraService
      .list()
      .then((cams) => {
        const map = new Map<string, { name: string; location: string; lat: number; lng: number }>();
        cams.forEach((c) =>
          map.set(c.id.toUpperCase(), {
            name: c.name,
            location: c.location,
            lat: c.latitude,
            lng: c.longitude,
          }),
        );
        return map;
      })
      // A failed registry lookup must not take the alert list down with it.
      .catch(() => new Map());
  }
  return cameraIndex;
}

async function enrich(alerts: Alert[]): Promise<Alert[]> {
  if (!alerts.length) return alerts;
  const cams = await camerasById();
  return alerts.map((a) => {
    const cam = cams.get(a.cameraId.toUpperCase());
    if (!cam) return a;
    return {
      ...a,
      cameraName: a.cameraName ?? cam.name,
      location: a.location || cam.location,
      latitude: a.latitude ?? cam.lat,
      longitude: a.longitude ?? cam.lng,
    };
  });
}

export const alertService = {
  async list(filters: AlertFilters = {}): Promise<Alert[]> {
    if (isMockMode) return mock.getAlerts(filters);

    const params: Record<string, string | number> = { size: 100, page: 1 };
    if (filters.status && filters.status !== 'ALL') params.status = filters.status;
    if (filters.severity && filters.severity !== 'ALL') params.severity = filters.severity;

    const alerts = unwrapList(await get<unknown>('/alerts', { params })).map(mapAlert);
    const enriched = await enrich(alerts);

    // Free-text search is not a server parameter — apply it here.
    if (filters.query) {
      const q = filters.query.trim().toLowerCase();
      return enriched.filter((a) =>
        [a.plate, a.cameraId, a.cameraName, a.location, a.category].some((v) =>
          String(v ?? '').toLowerCase().includes(q),
        ),
      );
    }
    return enriched;
  },

  async acknowledge(id: string, by?: string): Promise<Alert> {
    if (isMockMode) return mock.acknowledgeAlert(id, by);
    // The API records the acting operator under `operator`.
    const [alert] = await enrich([
      mapAlert(await post<Record<string, unknown>>(`/alerts/${encodeURIComponent(id)}/ack`, { operator: by })),
    ]);
    return alert;
  },

  async resolve(id: string, note?: string): Promise<Alert> {
    if (isMockMode) return mock.resolveAlert(id, note);
    const [alert] = await enrich([
      mapAlert(await post<Record<string, unknown>>(`/alerts/${encodeURIComponent(id)}/resolve`, { operator: note })),
    ]);
    return alert;
  },
};
