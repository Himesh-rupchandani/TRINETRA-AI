import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import type { OfficerProfile } from '@/types';
import { officerService } from '@/services/officerService';

interface OfficerContextValue {
  /** Every officer available for selection. */
  officers: OfficerProfile[];
  /** The officer signed into the control room (shown in header/sidebar). */
  current: OfficerProfile | null;
  /** The officer whose profile is currently being viewed in the Profile section. */
  active: OfficerProfile | null;
  /** Officers other than the signed-in Senior Officer (for the selection list). */
  others: OfficerProfile[];
  loading: boolean;
  error: string | null;
  selectOfficer: (officerId: string) => void;
  refresh: () => void;
}

const OfficerContext = createContext<OfficerContextValue | null>(null);

/**
 * Owns the officer roster and the currently selected officer so the header,
 * sidebar and Profile section all reflect the same person.
 */
export function OfficerProvider({ children }: { children: ReactNode }) {
  const [officers, setOfficers] = useState<OfficerProfile[]>([]);
  const [currentId, setCurrentId] = useState<string | null>(null);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    Promise.all([officerService.current(), officerService.list()])
      .then(([current, list]) => {
        if (cancelled) return;
        const roster = list.some((o) => o.officerId === current.officerId) ? list : [current, ...list];
        setOfficers(roster);
        setCurrentId(current.officerId);
        setActiveId((prev) => (prev && roster.some((o) => o.officerId === prev) ? prev : current.officerId));
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(e instanceof Error ? e.message : 'Request failed');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [nonce]);

  /**
   * Selecting an officer makes them the current officer everywhere: the
   * header, sidebar and Profile section all follow the selection.
   */
  const selectOfficer = useCallback((officerId: string) => {
    setActiveId(officerId);
    setCurrentId(officerId);
  }, []);
  const refresh = useCallback(() => setNonce((n) => n + 1), []);

  const value = useMemo<OfficerContextValue>(() => {
    const active = officers.find((o) => o.officerId === activeId) ?? null;
    const current = officers.find((o) => o.officerId === currentId) ?? null;
    return {
      officers,
      current,
      active,
      others: officers.filter((o) => o.officerId !== (activeId ?? currentId)),
      loading,
      error,
      selectOfficer,
      refresh,
    };
  }, [officers, activeId, currentId, loading, error, selectOfficer, refresh]);

  return <OfficerContext.Provider value={value}>{children}</OfficerContext.Provider>;
}

export function useOfficer(): OfficerContextValue {
  const ctx = useContext(OfficerContext);
  if (!ctx) throw new Error('useOfficer must be used within OfficerProvider');
  return ctx;
}
