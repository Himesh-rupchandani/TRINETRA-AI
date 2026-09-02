import type { Alert, AlertFilters } from '@/types';
import { get, post, isMockMode } from './api';
import * as mock from '@/mocks/mockBackend';

export const alertService = {
  list(filters: AlertFilters = {}): Promise<Alert[]> {
    return isMockMode ? mock.getAlerts(filters) : get<Alert[]>('/alerts', { params: filters });
  },

  acknowledge(id: string, by?: string): Promise<Alert> {
    return isMockMode
      ? mock.acknowledgeAlert(id, by)
      : post<Alert>(`/alerts/${encodeURIComponent(id)}/ack`, { by });
  },

  resolve(id: string, note?: string): Promise<Alert> {
    return isMockMode
      ? mock.resolveAlert(id, note)
      : post<Alert>(`/alerts/${encodeURIComponent(id)}/resolve`, { note });
  },
};
