import { useEffect } from 'react';
import { useAsync } from '@/hooks/useAsync';
import { systemService } from '@/services/systemService';
import type { DashboardKpis, SystemSummary } from '@/types';

/** Platform health + KPI summary (dashboard band, system page). */
export function useSystemStatus(pollMs?: number) {
  const health = useAsync(() => systemService.health(), []);
  const kpis = useAsync(() => systemService.kpis(), []);

  // Optional polling (system page); dashboard reads a single snapshot.
  useEffect(() => {
    if (!pollMs) return;
    const t = setInterval(() => {
      health.refresh();
      kpis.refresh();
    }, pollMs);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pollMs]);

  return {
    health: health.data as SystemSummary | null,
    kpis: kpis.data as DashboardKpis | null,
    loading: health.loading || kpis.loading,
    error: health.error ?? kpis.error,
    refresh: () => {
      health.refresh();
      kpis.refresh();
    },
  };
}
