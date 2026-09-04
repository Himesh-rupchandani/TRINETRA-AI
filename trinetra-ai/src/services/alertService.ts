import type { Alert, AlertFilters } from '@/types';
import { get, post, isMockMode } from './api';
import * as mock from '@/mocks/mockBackend';
import { cameraDirectory, toAlert, type AlertDto } from './adapters';

interface PaginatedAlertsDto {
  items: AlertDto[];
  total: number;
}

function toParams(filters: AlertFilters): Record<string, string> {
  const p: Record<string, string> = {};
  if (filters.status && filters.status !== 'ALL') p.status = filters.status;
  if (filters.severity && filters.severity !== 'ALL') p.severity = filters.severity;
  p.size = '100';
  return p;
}

export const alertService = {
  async list(filters: AlertFilters = {}): Promise<Alert[]> {
    if (isMockMode) return mock.getAlerts(filters);
    // Backend returns a paginated envelope; enrich each alert with canonical
    // camera name/location from the shared registry directory.
    const [res, dir] = await Promise.all([
      get<PaginatedAlertsDto | AlertDto[]>('/alerts', { params: toParams(filters) }),
      cameraDirectory().catch(() => null),
    ]);
    const items = Array.isArray(res) ? res : (res.items ?? []);
    const mapped = items.map((dto) => toAlert(dto, dir));
    return filters.query
      ? mapped.filter((a) =>
          `${a.plate} ${a.cameraId} ${a.cameraName} ${a.category}`.toUpperCase().includes(filters.query!.toUpperCase()),
        )
      : mapped;
  },

  async acknowledge(id: string, by?: string): Promise<Alert> {
    if (isMockMode) return mock.acknowledgeAlert(id, by);
    return toAlert(
      await post<AlertDto>(`/alerts/${encodeURIComponent(id)}/ack`, { operator: by }),
    );
  },

  async resolve(id: string, note?: string): Promise<Alert> {
    if (isMockMode) return mock.resolveAlert(id, note);
    return toAlert(
      await post<AlertDto>(`/alerts/${encodeURIComponent(id)}/resolve`, {
        operator: note ? `resolve: ${note}` : undefined,
      }),
    );
  },
};
