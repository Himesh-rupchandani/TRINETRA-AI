import { useMemo } from 'react';
import { useLive } from '@/features/alerts/LiveProvider';
import type { AlertFilters } from '@/types';

/** Session-wide alert state with optional client-side filtering. */
export function useAlerts(filters: AlertFilters = {}) {
  const { alerts, counts, acknowledge, resolve, refreshAlerts, latestAlert, dismissLatest } = useLive();

  const filtered = useMemo(() => {
    const q = filters.query?.trim().toUpperCase();
    return alerts
      .filter((a) => {
        if (filters.status && filters.status !== 'ALL' && a.status !== filters.status) return false;
        if (filters.severity && filters.severity !== 'ALL' && a.severity !== filters.severity) return false;
        if (q && !`${a.plate} ${a.cameraId} ${a.cameraName} ${a.location} ${a.category}`.toUpperCase().includes(q))
          return false;
        return true;
      })
      .sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime());
  }, [alerts, filters.status, filters.severity, filters.query]);

  const active = useMemo(() => filtered.filter((a) => a.status !== 'RESOLVED'), [filtered]);
  const history = useMemo(() => filtered.filter((a) => a.status === 'RESOLVED'), [filtered]);

  return { alerts: filtered, active, history, counts, acknowledge, resolve, refreshAlerts, latestAlert, dismissLatest };
}
