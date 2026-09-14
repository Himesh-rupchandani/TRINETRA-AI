import { useCallback, useEffect, useRef, useState } from 'react';
import { eventService } from '@/services/eventService';
import type { EventFilters, Paginated, VehicleEvent } from '@/types';

/** Paginated Event Explorer query. Only the current page is ever rendered. */
export function useEventSearch(filters: EventFilters, page: number, pageSize = 25) {
  const [data, setData] = useState<Paginated<VehicleEvent> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const callId = useRef(0);
  const key = JSON.stringify(filters);

  const run = useCallback(() => {
    const id = ++callId.current;
    setLoading(true);
    setError(null);
    eventService
      .search(filters, page, pageSize)
      .then((res) => {
        if (id === callId.current) setData(res);
      })
      .catch((e: unknown) => {
        if (id === callId.current) setError(e instanceof Error ? e.message : 'Search failed');
      })
      .finally(() => {
        if (id === callId.current) setLoading(false);
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, page, pageSize]);

  useEffect(run, [run]);

  return { data, loading, error, refresh: run };
}
