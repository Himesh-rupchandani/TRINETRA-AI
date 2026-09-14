import { useMemo } from 'react';
import { cameraService } from '@/services/cameraService';
import { useAsync } from './useAsync';
import type { Camera, CameraFilters } from '@/types';
import { unique } from '@/lib/utils';

/** Camera registry with client-side filtering and facet options. */
export function useCameras(filters: CameraFilters = {}) {
  const { data, loading, error, refresh } = useAsync<Camera[]>(() => cameraService.list(), []);
  const cameras = useMemo(() => data ?? [], [data]);

  const filtered = useMemo(() => {
    const q = filters.query?.trim().toLowerCase();
    return cameras.filter((c) => {
      if (q && !`${c.id} ${c.name} ${c.location} ${c.department ?? ''} ${c.zone ?? ''}`.toLowerCase().includes(q))
        return false;
      if (filters.status && filters.status !== 'ALL' && c.status !== filters.status) return false;
      if (filters.department && filters.department !== 'ALL' && c.department !== filters.department) return false;
      if (filters.zone && filters.zone !== 'ALL' && c.zone !== filters.zone) return false;
      if (filters.codec && filters.codec !== 'ALL' && c.codec !== filters.codec) return false;
      if (filters.activity === 'ACTIVE' && !(c.eventCount24h ?? 0)) return false;
      if (filters.activity === 'QUIET' && (c.eventCount24h ?? 0) > 0) return false;
      return true;
    });
  }, [cameras, filters.query, filters.status, filters.department, filters.zone, filters.codec, filters.activity]);

  const facets = useMemo(
    () => ({
      departments: unique(cameras.map((c) => c.department).filter(Boolean) as string[]).sort(),
      zones: unique(cameras.map((c) => c.zone).filter(Boolean) as string[]).sort(),
      codecs: unique(cameras.map((c) => c.codec).filter(Boolean) as string[]).sort(),
    }),
    [cameras],
  );

  const stats = useMemo(
    () => ({
      total: cameras.length,
      online: cameras.filter((c) => c.status === 'ONLINE').length,
      degraded: cameras.filter((c) => c.status === 'DEGRADED').length,
      offline: cameras.filter((c) => c.status === 'OFFLINE').length,
    }),
    [cameras],
  );

  return { cameras, filtered, facets, stats, loading, error, refresh };
}

/** Single camera record. */
export function useCamera(id?: string) {
  return useAsync<Camera>(() => cameraService.byId(id!), [id], { enabled: Boolean(id) });
}
