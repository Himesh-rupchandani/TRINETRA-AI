import { useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Activity,
  ArrowRight,
  Bell,
  Cctv,
  ScanLine,
  ShieldAlert,
} from 'lucide-react';
import { KpiCard } from '@/components/dashboard/KpiCard';
import { CameraActivityChart, DetectionTrend } from '@/components/dashboard/Charts';
import { LiveEventFeed } from '@/components/events/LiveEventFeed';
import { AlertCard } from '@/components/alerts/AlertCard';
import { TraceSearchBar } from '@/components/vehicle/TraceSearchBar';
import { CameraCard } from '@/components/camera/CameraCard';
import { Panel, AsyncBoundary, EmptyState } from '@/components/common/Panel';
import { EyeMark } from '@/components/common/EyeMark';
import { useCameras } from '@/hooks/useCameras';
import { useAlerts } from '@/hooks/useAlerts';
import { useLiveEvents } from '@/hooks/useLiveEvents';
import { useClock } from '@/hooks/useUi';
import { useAsync } from '@/hooks/useAsync';
import { eventService } from '@/services/eventService';
import { systemService } from '@/services/systemService';
import { cn, formatNumber } from '@/lib/utils';
import { demoFlow } from '@/data/demoFlow';
import type { ServiceHealth } from '@/types';

/** Count of timestamps per hour, oldest → newest, for sparklines. */
function hourlySeries(dates: string[], nowMs: number, hours = 12): number[] {
  const buckets = new Array<number>(hours).fill(0);
  dates.forEach((d) => {
    const t = new Date(d).getTime();
    if (Number.isNaN(t)) return;
    const ageH = Math.floor((nowMs - t) / 3_600_000);
    if (ageH >= 0 && ageH < hours) buckets[hours - 1 - ageH] += 1;
  });
  return buckets;
}

/** This hour minus the previous hour. */
function hourlyDelta(dates: string[], nowMs: number): number {
  let cur = 0;
  let prev = 0;
  dates.forEach((d) => {
    const ageH = (nowMs - new Date(d).getTime()) / 3_600_000;
    if (ageH < 1) cur += 1;
    else if (ageH < 2) prev += 1;
  });
  return cur - prev;
}

function healthVerdict(services: ServiceHealth[]): { label: string; cls: string; dot: string } {
  const bad = services.filter((s) => s.status !== 'HEALTHY').length;
  if (!services.length) return { label: 'HEALTH UNKNOWN', cls: 'border-line bg-surface-2 text-ink-faint', dot: 'bg-ink-faint' };
  if (bad === 0) return { label: 'ALL SYSTEMS NOMINAL', cls: 'border-online/40 bg-online/10 text-online', dot: 'bg-online live-dot' };
  return { label: `${bad} SERVICE${bad > 1 ? 'S' : ''} NEED ATTENTION`, cls: 'border-degraded/40 bg-degraded/10 text-degraded', dot: 'bg-degraded' };
}

/**
 * COMMAND CENTER — the money screen.
 * Command strip (lockup · live clock · cameras online · system health)
 * → 4 KPIs with sparkline + delta vs last hour
 * → live camera mosaic + watchlist alerts + live detection feed
 * → 24h detections chart. Sized to fit 1440x900 with no page scroll.
 */
export default function Dashboard() {
  const navigate = useNavigate();
  const now = useClock(1000);
  const { cameras, stats, loading: camsLoading, error: camsError, refresh } = useCameras();
  const { active: activeAlerts, alerts: allAlerts, acknowledge, resolve } = useAlerts();
  const { connection } = useLiveEvents();
  const recent = useAsync(() => eventService.recent(120), []);
  const kpis = useAsync(() => systemService.kpis(), []);
  const health = useAsync(() => systemService.health(), []);

  const recentEvents = useMemo(() => recent.data ?? [], [recent.data]);

  /* ---- KPI series (derived from real session data, clock-driven) ---- */
  const nowMs = now.getTime();
  const alertDates = useMemo(() => allAlerts.map((a) => a.createdAt), [allAlerts]);
  const plateDates = useMemo(
    () => recentEvents.filter((e) => e.plate && e.plate !== '—').map((e) => e.timestamp),
    [recentEvents],
  );
  const watchDates = useMemo(
    () => recentEvents.filter((e) => e.watchlistMatch).map((e) => e.timestamp),
    [recentEvents],
  );
  const platesReadToday = kpis.data?.anprReads24h ?? plateDates.length;
  const watchHitsToday = kpis.data?.watchlistMatches24h ?? watchDates.length;

  /* ---- Camera wall: busiest online cameras ---- */
  const wallCameras = useMemo(
    () =>
      [...cameras]
        .filter((c) => c.status !== 'OFFLINE')
        .sort((a, b) => (b.eventCount24h ?? 0) - (a.eventCount24h ?? 0))
        .slice(0, 6),
    [cameras],
  );

  /** Detections per camera in the last 15 minutes (feeds the tile HUD). */
  const recentPerCamera = useMemo(() => {
    const cutoff = nowMs - 15 * 60_000;
    const counts = new Map<string, number>();
    recentEvents.forEach((e) => {
      if (new Date(e.timestamp).getTime() >= cutoff) {
        counts.set(e.cameraId, (counts.get(e.cameraId) ?? 0) + 1);
      }
    });
    return counts;
  }, [recentEvents, nowMs]);

  const live = connection === 'LIVE';
  const healthPill = healthVerdict(health.data?.services ?? []);
  const clockTime = now.toLocaleTimeString('en-IN', { hour12: false, timeZone: 'Asia/Kolkata' });
  const clockDate = now.toLocaleDateString('en-IN', {
    weekday: 'short',
    day: '2-digit',
    month: 'short',
    timeZone: 'Asia/Kolkata',
  });

  return (
    <div className="flex h-full min-h-0 flex-col gap-3 overflow-y-auto p-3.5 xl:overflow-hidden">
      {/* ---------------- Command strip ---------------- */}
      <section
        className="panel relative flex shrink-0 flex-col gap-3 overflow-hidden px-4 py-3"
        aria-label="Command strip"
      >
        <div
          className="eye-rings pointer-events-none absolute -right-10 top-1/2 h-64 w-64 -translate-y-1/2 opacity-30 [mask-image:linear-gradient(to_right,transparent,black)]"
          aria-hidden
        />
        <div className="relative flex flex-wrap items-center gap-x-5 gap-y-3">
          {/* Product lockup */}
          <div className="flex min-w-0 items-center gap-3">
            <EyeMark size={40} />
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <p className="truncate text-base font-extrabold tracking-[0.02em] text-ink">TRINETRA AI</p>
                <span className="chip hidden border-brand/30 bg-brand/10 font-mono uppercase tracking-wider text-brand sm:inline-flex">
                  Sentinel Hackathon
                </span>
              </div>
              <p className="truncate text-2xs text-ink-faint">
                Intelligent Vision · Faster Response — CCTV intelligence for Gujarat Police
              </p>
            </div>
          </div>

          {/* Live clock */}
          <div className="flex items-center gap-2.5 border-l border-line pl-5">
            <div>
              <p className="font-mono text-lg font-bold leading-none tabular-nums text-ink" aria-label="Control room time">
                {clockTime}
              </p>
              <p className="mt-1 text-[10px] font-medium uppercase tracking-[0.1em] text-ink-faint">
                {clockDate} · IST
              </p>
            </div>
          </div>

          {/* Cameras online */}
          <div className="flex items-center gap-2.5 border-l border-line pl-5">
            <span className="live-dot h-2 w-2 shrink-0 bg-online" aria-hidden />
            <div>
              <p className="font-mono text-lg font-bold leading-none tabular-nums text-ink">
                {formatNumber(stats.online)}
                <span className="text-ink-faint">/{formatNumber(stats.total)}</span>
              </p>
              <p className="mt-1 text-[10px] font-medium uppercase tracking-[0.1em] text-ink-faint">
                Cameras online
              </p>
            </div>
          </div>

          {/* System health pill */}
          <div className="border-l border-line pl-5">
            {health.loading ? (
              <span className="skeleton inline-block h-6 w-40" />
            ) : (
              <span
                className={cn('chip font-mono uppercase tracking-wider', healthPill.cls)}
                title="Backend services heartbeat"
              >
                <span className={cn('h-1.5 w-1.5 rounded-full bg-current', healthPill.dot)} aria-hidden />
                {healthPill.label}
              </span>
            )}
          </div>

          {/* Trace search — the fastest path into the product */}
          <div className="ml-auto hidden min-w-[240px] max-w-[340px] flex-1 lg:block">
            <TraceSearchBar onTrace={(p) => navigate(`/vehicles/${p}`)} showSuggestions={false} />
          </div>
        </div>

        {/* Guided demo flow — the four things an officer does, in order */}
        <nav className="relative flex flex-wrap items-center gap-2" aria-label="Guided demo flow">
          <span className="section-label mr-1 hidden sm:inline">Demo flow</span>
          {demoFlow.map((task) => (
            <button
              key={task.step}
              type="button"
              onClick={() => navigate(task.to)}
              className="group flex h-7 items-center gap-1.5 rounded-md border border-line bg-surface-2/60 px-2.5 text-2xs font-semibold text-ink-muted transition-colors hover:border-brand/40 hover:bg-brand/10 hover:text-brand"
            >
              <span className="font-mono text-[10px] font-bold text-brand/80">{String(task.step).padStart(2, '0')}</span>
              {task.label}
              <ArrowRight size={11} className="opacity-0 transition-opacity group-hover:opacity-100" aria-hidden />
            </button>
          ))}
          <span className="ml-auto hidden items-center gap-1.5 text-2xs text-ink-faint md:flex">
            <span
              className={cn(
                'h-1.5 w-1.5 rounded-full',
                live ? 'live-dot bg-online' : connection === 'OFFLINE' ? 'bg-offline' : 'bg-degraded',
              )}
              aria-hidden
            />
            {live ? 'Realtime channel connected' : `Realtime channel: ${connection.toLowerCase()}`}
          </span>
        </nav>
      </section>

      {/* ---------------- KPI row ---------------- */}
      <section
        className="grid shrink-0 grid-cols-2 gap-3 lg:grid-cols-4"
        aria-label="Key performance indicators"
      >
        <KpiCard
          label="Active Alerts"
          value={formatNumber(activeAlerts.length)}
          sub="Pending operator action"
          tone={activeAlerts.length ? 'critical' : 'neutral'}
          tile="red"
          icon={Bell}
          to="/alerts"
          cta="Open triage"
          spark={hourlySeries(alertDates, nowMs)}
          sparkTone="critical"
          delta={hourlyDelta(alertDates, nowMs)}
          deltaTone="bad"
        />
        <KpiCard
          label="Cameras Live"
          value={`${formatNumber(stats.online)}/${formatNumber(stats.total)}`}
          sub={`${stats.degraded} degraded · ${stats.offline} offline`}
          tile="green"
          icon={Cctv}
          to="/cameras"
          cta="Open camera wall"
          loading={camsLoading && !cameras.length}
          spark={hourlySeries(recentEvents.map((e) => e.timestamp), nowMs)}
          sparkTone="online"
          delta={hourlyDelta(recentEvents.map((e) => e.timestamp), nowMs)}
          deltaTone="good"
        />
        <KpiCard
          label="Plates Read Today"
          value={formatNumber(platesReadToday)}
          sub="ANPR reads in the last 24 hours"
          tile="blue"
          icon={ScanLine}
          to="/events"
          cta="View vehicle log"
          loading={kpis.loading && !recentEvents.length}
          spark={hourlySeries(plateDates, nowMs)}
          sparkTone="brand"
          delta={hourlyDelta(plateDates, nowMs)}
          deltaTone="good"
        />
        <KpiCard
          label="Watchlist Hits"
          value={formatNumber(watchHitsToday)}
          sub="Wanted vehicles found in 24 hours"
          tone="critical"
          tile="orange"
          icon={ShieldAlert}
          to="/watchlist"
          cta="Open wanted list"
          loading={kpis.loading && !recentEvents.length}
          spark={hourlySeries(watchDates, nowMs)}
          sparkTone="accent"
          delta={hourlyDelta(watchDates, nowMs)}
          deltaTone="bad"
        />
      </section>

      {/* ---------------- Operations row: camera wall + alerts ---------------- */}
      <section className="grid min-h-0 flex-1 grid-cols-1 gap-3 xl:grid-cols-12">
        <Panel
          title="Live Camera Wall"
          icon={Cctv}
          className="min-h-[380px] xl:col-span-8"
          bodyClassName="min-h-0"
          actions={
            <button type="button" className="link-btn" onClick={() => navigate('/cameras')}>
              View all <ArrowRight size={13} aria-hidden />
            </button>
          }
        >
          <AsyncBoundary
            loading={camsLoading}
            error={camsError}
            onRetry={refresh}
            isEmpty={!cameras.length}
            loadingLabel="Loading camera registry"
            emptyTitle="No cameras registered"
            emptyDetail="The camera registry is empty. Add cameras or enable demo data to see the live wall."
          >
            <div className="grid h-full grid-cols-1 content-start gap-2 overflow-y-auto p-2.5 sm:grid-cols-2 lg:grid-cols-3">
              {wallCameras.map((c) => (
                <CameraCard
                  key={c.id}
                  camera={c}
                  variant="feed"
                  recentCount={recentPerCamera.get(c.id) ?? 0}
                />
              ))}
            </div>
          </AsyncBoundary>
        </Panel>

        <div className="flex min-h-0 flex-col gap-3 xl:col-span-4">
          <Panel
            title="Watchlist Alerts"
            icon={ShieldAlert}
            className="min-h-[260px] flex-1"
            bodyClassName="overflow-y-auto min-h-0"
            actions={
              <button type="button" className="link-btn" onClick={() => navigate('/alerts')}>
                Triage all <ArrowRight size={13} aria-hidden />
              </button>
            }
          >
            {activeAlerts.length === 0 ? (
              <EmptyState
                icon={ShieldAlert}
                title="No active alerts"
                detail="Nothing needs your attention right now."
                action={
                  <button type="button" className="btn-tint btn-xs" onClick={() => navigate('/watchlist')}>
                    Open wanted list
                  </button>
                }
              />
            ) : (
              <div className="space-y-2 p-2.5">
                {activeAlerts.slice(0, 6).map((a) => (
                  <AlertCard key={a.id} alert={a} onAcknowledge={acknowledge} onResolve={resolve} compact />
                ))}
              </div>
            )}
          </Panel>

          <Panel
            title="Live Detections"
            icon={Activity}
            className="h-[300px] shrink-0"
            bodyClassName="overflow-y-auto min-h-0"
          >
            <LiveEventFeed seed={recentEvents.slice(0, 20)} max={40} />
          </Panel>
        </div>
      </section>

      {/* ---------------- Bottom row: 24h trend + busiest cameras ---------------- */}
      <section className="grid shrink-0 grid-cols-1 gap-3 xl:grid-cols-12" aria-label="Detection trends">
        <Panel
          title="Detections — last 24 hours"
          icon={Activity}
          className="min-h-[180px] xl:col-span-8"
          bodyClassName="p-2.5"
        >
          <AsyncBoundary
            loading={recent.loading}
            error={recent.error}
            onRetry={recent.refresh}
            loadingLabel="Loading detection history"
          >
            <div className="h-[120px]">
              <DetectionTrend events={recentEvents} />
            </div>
          </AsyncBoundary>
        </Panel>

        <Panel
          title="Busiest cameras"
          icon={Cctv}
          className="min-h-[180px] xl:col-span-4"
          bodyClassName="p-2.5"
        >
          <div className="h-[120px]">
            <CameraActivityChart events={recentEvents} />
          </div>
        </Panel>
      </section>
    </div>
  );
}
