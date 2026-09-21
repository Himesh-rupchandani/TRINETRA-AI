import { useCallback, useEffect, useRef, useState } from 'react';
import { eventService } from '@/services/eventService';
import { useLive } from '@/features/alerts/LiveProvider';
import type { EventFilters, Paginated, VehicleEvent } from '@/types';

/** Paginated log, refreshed quietly after sightings without resetting filters/page. */
export function useEventSearch(filters: EventFilters, page: number, pageSize = 25) {
  const [data, setData] = useState<Paginated<VehicleEvent> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const { eventsSeen, connection } = useLive();
  const callId = useRef(0);
  const inFlight = useRef(false);
  const mounted = useRef(false);
  const pending = useRef<ReturnType<typeof setTimeout> | null>(null);
  const key = JSON.stringify(filters);

  const run = useCallback((background = false) => {
    if (background && inFlight.current) return;
    inFlight.current = true;
    const id = ++callId.current;
    if (!background) {
      setLoading(true);
      setError(null);
    }
    eventService.search(filters, page, pageSize)
      .then((res) => {
        if (mounted.current && id === callId.current) {
          setData(res);
          setError(null);
        }
      })
      .catch((e: unknown) => {
        // A transient background failure must not replace a populated log
        // with an error screen. Keep the last successful rows until recovery.
        if (!background && mounted.current && id === callId.current) {
          setError(e instanceof Error ? e.message : 'Search failed');
        }
      })
      .finally(() => {
        if (id === callId.current) {
          inFlight.current = false;
          if (mounted.current) setLoading(false);
        }
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, page, pageSize]);
  const runRef = useRef(run);
  runRef.current = run;
  const refresh = useCallback(() => run(), [run]);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      callId.current++;
      if (pending.current) clearTimeout(pending.current);
      pending.current = null;
    };
  }, []);
  useEffect(refresh, [refresh]);

  useEffect(() => {
    // Throttle (not debounce): continuous traffic cannot postpone a refresh
    // forever. Always read the newest filters when the scheduled fetch fires.
    if (!pending.current) pending.current = setTimeout(() => {
      pending.current = null;
      runRef.current(true);
    }, 750);
  }, [eventsSeen, connection]);

  useEffect(() => {
    // REST reconciliation also catches missed SSE messages after reconnect.
    // Never simulate plates when the realtime transport goes offline.
    const timer = setInterval(() => {
      if (!document.hidden) runRef.current(true);
    }, connection === 'OFFLINE' ? 5000 : 15_000);
    return () => clearInterval(timer);
  }, [connection]);

  return { data, loading, error, refresh };
}
