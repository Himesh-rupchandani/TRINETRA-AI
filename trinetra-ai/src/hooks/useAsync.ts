import { useCallback, useEffect, useRef, useState } from 'react';

export interface AsyncState<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  refresh: () => void;
  setData: (updater: T | ((prev: T | null) => T)) => void;
}

/**
 * Small async-resource hook: loading / error / data + manual refresh.
 * Keeps components free of fetch plumbing and guards against setState
 * after unmount or out-of-order responses.
 */
export function useAsync<T>(
  fn: () => Promise<T>,
  deps: React.DependencyList = [],
  options: { enabled?: boolean; initialData?: T | null } = {},
): AsyncState<T> {
  const { enabled = true, initialData = null } = options;
  const [data, setDataState] = useState<T | null>(initialData);
  const [loading, setLoading] = useState<boolean>(enabled);
  const [error, setError] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);
  const mounted = useRef(true);
  const callId = useRef(0);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  useEffect(() => {
    if (!enabled) {
      setLoading(false);
      return;
    }
    const id = ++callId.current;
    setLoading(true);
    setError(null);
    fn()
      .then((res) => {
        if (mounted.current && id === callId.current) setDataState(res);
      })
      .catch((e: unknown) => {
        if (mounted.current && id === callId.current) {
          setError(e instanceof Error ? e.message : 'Request failed');
        }
      })
      .finally(() => {
        if (mounted.current && id === callId.current) setLoading(false);
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce, enabled]);

  const refresh = useCallback(() => setNonce((n) => n + 1), []);
  const setData = useCallback((updater: T | ((prev: T | null) => T)) => {
    setDataState((prev) => (typeof updater === 'function' ? (updater as (p: T | null) => T)(prev) : updater));
  }, []);

  return { data, loading, error, refresh, setData };
}
