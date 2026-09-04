import type { Alert, AlertFilters } from '@/types';
import { get, post, isMockMode } from './api';
import * as mock from '@/mocks/mockBackend';
import { cameraService } from './cameraService';
import { toAlert, unwrapList, type AlertDto } from './adapters';

/** Backend filter names differ from the UI filter names — map them here only. */
function toParams(f: AlertFilters): Record<string, string | number> {
  const p: Record<string, string | number> = { size: 100 };
  if (f.status && f.status !== 'ALL') p.status = f.status;
  if (f.severity && f.severity !== 'ALL') p.severity = f.severity;
  return p;
}

export const alertService = {
  async list(filters: AlertFilters = {}): Promise<Alert[]> {
    if (isMockMode) return mock.getAlerts(filters);

    const [raw, cameras] = await Promise.all([
      get<unknown>('/alerts', { params: toParams(filters) }),
      cameraService.index(),
    ]);
    let alerts = unwrapList<AlertDto>(raw).map((d) => toAlert(d, cameras));

    // Free-text search is client-side: the backend has no `q` parameter and we
    // do not invent endpoints (spec Phase 6).
    const q = filters.query?.trim().toUpperCase();
    if (q) {
      alerts = alerts.filter((a) =>
        `${a.plate} ${a.cameraId} ${a.location} ${a.category}`.toUpperCase().includes(q),
      );
    }
    return alerts.sort(
      (a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime(),
    );
  },

  async acknowledge(id: string, by?: string): Promise<Alert> {
    if (isMockMode) return mock.acknowledgeAlert(id, by);
    const [dto, cameras] = await Promise.all([
      post<AlertDto>(`/alerts/${encodeURIComponent(id)}/ack`, { operator: by }),
      cameraService.index(),
    ]);
    return toAlert(dto, cameras);
  },

  async resolve(id: string, note?: string): Promise<Alert> {
    if (isMockMode) return mock.resolveAlert(id, note);
    const [dto, cameras] = await Promise.all([
      post<AlertDto>(`/alerts/${encodeURIComponent(id)}/resolve`, { operator: note }),
      cameraService.index(),
    ]);
    return toAlert(dto, cameras);
  },
};
