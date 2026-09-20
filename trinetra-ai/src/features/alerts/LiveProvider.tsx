import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import type { Alert, AlertStatus, VehicleEvent } from '@/types';
import { connectRealtime, triggerAlertNow, type ConnectionState, type RealtimeMessage } from '@/services/realtimeService';
import { alertService } from '@/services/alertService';
import { subscribeToStore } from '@/mocks/mockBackend';
import { isMockMode } from '@/services/api';

const MAX_LIVE_EVENTS = 60;

interface LiveContextValue {
  /** Rolling buffer of the most recent detections (newest first). */
  liveEvents: VehicleEvent[];
  /** Every alert known to the session — live + historical. */
  alerts: Alert[];
  connection: ConnectionState;
  paused: boolean;
  setPaused: (v: boolean) => void;
  /** Alert raised in the last few seconds — drives the alert banner. */
  latestAlert: Alert | null;
  dismissLatest: () => void;
  acknowledge: (id: string) => Promise<void>;
  resolve: (id: string, note?: string) => Promise<void>;
  refreshAlerts: () => void;
  counts: Record<AlertStatus | 'ACTIVE', number>;
  eventsSeen: number;
  /** Seconds remaining until the next 60s automated alert notification */
  secondsUntilNextAlert: number;
  /** Immediately trigger the next unique vehicle alert in the rotation */
  triggerNextAlert: () => Promise<void>;
}

const LiveContext = createContext<LiveContextValue | null>(null);

export function LiveProvider({ children }: { children: ReactNode }) {
  const [liveEvents, setLiveEvents] = useState<VehicleEvent[]>([]);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [connection, setConnection] = useState<ConnectionState>('CONNECTING');
  const [paused, setPaused] = useState(false);
  const [latestAlert, setLatestAlert] = useState<Alert | null>(null);
  const [eventsSeen, setEventsSeen] = useState(0);
  const [secondsUntilNextAlert, setSecondsUntilNextAlert] = useState(60);
  const pausedRef = useRef(paused);
  useEffect(() => {
    pausedRef.current = paused;
  }, [paused]);

  // 60-second alert countdown
  useEffect(() => {
    const timer = window.setInterval(() => {
      setSecondsUntilNextAlert((s) => (s <= 1 ? 60 : s - 1));
    }, 1000);
    return () => window.clearInterval(timer);
  }, []);

  const triggerNextAlert = useCallback(async () => {
    if (!isMockMode) {
      try {
        const res = await fetch('/api/alerts/trigger', { method: 'POST' });
        if (res.ok) {
          setSecondsUntilNextAlert(60);
          return;
        }
      } catch {
        // Fall back to client simulation if backend trigger fails
      }
    }
    const { event, alert } = triggerAlertNow();
    setLiveEvents((prev) => [event, ...prev].slice(0, MAX_LIVE_EVENTS));
    setAlerts((prev) => [alert, ...prev]);
    setLatestAlert(alert);
    setSecondsUntilNextAlert(60);
  }, []);

  const loadAlerts = useCallback(() => {
    alertService
      .list()
      .then((data) => {
        setAlerts(data);
        // If backend is reachable (alerts loaded), ensure we don't stay OFFLINE forever
        // - SSE may fail in preview/proxy environments, but backend is still LIVE
        setConnection((prev) => (prev === 'OFFLINE' && !isMockMode ? 'LIVE' : prev));
      })
      .catch(() => {
        setAlerts([]);
        // Keep OFFLINE if backend unreachable
      });
  }, []);

  useEffect(loadAlerts, [loadAlerts]);

  // Keep alert state in sync when the mock store mutates elsewhere.
  useEffect(() => (isMockMode ? subscribeToStore(loadAlerts) : undefined), [loadAlerts]);

  useEffect(() => {
    const onMessage = (msg: RealtimeMessage) => {
      if (msg.type === 'EVENT') {
        setEventsSeen((n) => n + 1);
        if (!pausedRef.current) {
          setLiveEvents((prev) => [msg.payload, ...prev].slice(0, MAX_LIVE_EVENTS));
        }
      } else if (msg.type === 'ALERT') {
        const incoming = msg.payload;
        setSecondsUntilNextAlert(60);
        setAlerts((prev) => {
          const idx = prev.findIndex((a) => a.id === incoming.id);
          if (idx === -1) return [incoming, ...prev];
          // Already listed: merge instead of dropping the frame, so a later
          // broadcast (status change, resolution note, corrected severity)
          // still updates the card the operator is looking at.
          const next = [...prev];
          next[idx] = { ...next[idx], ...incoming };
          return next;
        });
        setLatestAlert(incoming);
      }
    };
    const channel = connectRealtime(onMessage, setConnection);
    return () => channel.close();
  }, []);

  // Auto-dismiss the banner so it never blocks the operator's view.
  useEffect(() => {
    if (!latestAlert) return;
    const t = setTimeout(() => setLatestAlert(null), 12_000);
    return () => clearTimeout(t);
  }, [latestAlert]);

  const acknowledge = useCallback(async (id: string) => {
    const updated = await alertService.acknowledge(id, 'Operator');
    setAlerts((prev) => prev.map((a) => (a.id === id ? updated : a)));
    setLatestAlert((cur) => (cur?.id === id ? null : cur));
  }, []);

  const resolve = useCallback(async (id: string, note?: string) => {
    // Operator identity and note are separate fields — the backend stores the
    // note in `resolution_note`, never inside `resolved_by`.
    const updated = await alertService.resolve(id, note, 'Operator');
    setAlerts((prev) => prev.map((a) => (a.id === id ? updated : a)));
    setLatestAlert((cur) => (cur?.id === id ? null : cur));
  }, []);

  const counts = useMemo(() => {
    const c = { NEW: 0, ACKNOWLEDGED: 0, RESOLVED: 0, ACTIVE: 0 } as Record<
      AlertStatus | 'ACTIVE',
      number
    >;
    alerts.forEach((a) => {
      c[a.status] += 1;
      if (a.status !== 'RESOLVED') c.ACTIVE += 1;
    });
    return c;
  }, [alerts]);

  const value = useMemo<LiveContextValue>(
    () => ({
      liveEvents,
      alerts,
      connection,
      paused,
      setPaused,
      latestAlert,
      dismissLatest: () => setLatestAlert(null),
      acknowledge,
      resolve,
      refreshAlerts: loadAlerts,
      counts,
      eventsSeen,
      secondsUntilNextAlert,
      triggerNextAlert,
    }),
    [
      liveEvents,
      alerts,
      connection,
      paused,
      latestAlert,
      acknowledge,
      resolve,
      loadAlerts,
      counts,
      eventsSeen,
      secondsUntilNextAlert,
      triggerNextAlert,
    ],
  );

  return <LiveContext.Provider value={value}>{children}</LiveContext.Provider>;
}

export function useLive(): LiveContextValue {
  const ctx = useContext(LiveContext);
  if (!ctx) throw new Error('useLive must be used inside <LiveProvider>');
  return ctx;
}
