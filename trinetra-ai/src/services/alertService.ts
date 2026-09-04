import type { Alert, AlertFilters } from '@/types';
import { get, post, isMockMode } from './api';
import * as mock from '@/mocks/mockBackend';
import { getCameraIndex, mapAlert, type AlertDto, type PageDto } from './backendAdapter';

export const alertService = {
  async list(filters: AlertFilters = {}): Promise<Alert[]> {
    if (isMockMode) return mock.getAlerts(filters);
    const params: Record<string, string | number> = { size: 100 };
    if (filters.status && filters.status !== 'ALL') params.status = filters.status;
    if (filters.severity && filters.severity !== 'ALL') params.severity = filters.severity;
    const [page, cameras] = await Promise.all([
      get<PageDto<AlertDto>>('/alerts', { params }),
      getCameraIndex(),
    ]);
    return page.items.map((a) => mapAlert(a, cameras));
  },

  /**
   * NEW → ACKNOWLEDGED. The backend records `operator` + timestamp.
   * Alert IDs from the backend are numeric strings.
   */
  async acknowledge(id: string, by?: string): Promise<Alert> {
    if (isMockMode) return mock.acknowledgeAlert(id, by);
    const [raw, cameras] = await Promise.all([
      post<AlertDto>(`/alerts/${encodeURIComponent(id)}/ack`, { operator: by ?? 'Operator' }),
      getCameraIndex(),
    ]);
    return mapAlert(raw, cameras);
  },

  async resolve(id: string, note?: string): Promise<Alert> {
    if (isMockMode) return mock.resolveAlert(id, note);
    const [raw, cameras] = await Promise.all([
      post<AlertDto>(`/alerts/${encodeURIComponent(id)}/resolve`, {
        operator: 'Operator',
        ...(note ? { note } : {}),
      }),
      getCameraIndex(),
    ]);
    return mapAlert(raw, cameras);
  },
};
