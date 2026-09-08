import { useMemo } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, ShieldAlert } from 'lucide-react';
import { useAlerts } from '@/hooks/useAlerts';
import { useCameras } from '@/hooks/useCameras';
import { useLiveEvents } from '@/hooks/useLiveEvents';
import { useSystemStatus } from '@/features/system/useSystemStatus';
import { AlertItem } from '@/components/AlertItem';
import { LiveDetections } from '@/components/LiveDetections';
import { DashboardMosaic } from '@/components/DashboardMosaic';
import { VolumeChart } from '@/components/Charts';
import { useDashboardData } from '@/features/dashboard/useDashboardData';
import { buttonClass } from '@/ui/Button';
import { Card, CardBody, CardHeader, SectionLabel } from '@/ui/Card';
import { Stat } from '@/ui/Links';
import { Boundary } from '@/ui/Feedback';
import { cn } from '@/lib/utils';
import { formatTime } from '@/lib/uiHelpers';

const CONNECTION_LABEL: Record<string, { label: string; tone: string }> = {
  LIVE: { label: 'Realtime · live', tone: 'text-online' },
  SIMULATED: { label: 'Realtime · demo', tone: 'text-critical' },
  CONNECTING: { label: 'Realtime · connecting', tone: 'text-warn' },
  OFFLINE: { label: 'Realtime · offline', tone: 'text-offline' },
};

/**
 * SENTINEL Command Center — one clear hierarchy.
 * Primary: system state (cameras, pipeline, realtime) + live camera
 * mosaic with real detection overlays. Secondary: a compact KPI strip
 * from /stats/kpis. Detail: recent alerts, one click away.
 */
export default function Dashboard() {
  const { active, history: alertHistory, counts, acknowledge } = useAlerts();
  const { cameras, filtered, stats, loading: camsLoading, error: camsError } = useCameras();
  const { events, connection } = useLiveEvents();
  const { health, kpis, loading: sysLoading } = useSystemStatus();

  const { attention, volume24h, watchlistToday, deptRows } = useDashboardData({
    alerts: active.length > 0 ? active : alertHistory.slice(0, 4),
    cameras: filtered ?? cameras,
    liveEvents: events,
  });

  const mosaicCameras = useMemo(
    () =>
      [...(filtered ?? cameras)].sort(
        (a, b) =>
          (b.lastEventAt ? Date.parse(b.lastEventAt) : 0) - (a.lastEventAt ? Date.parse(a.lastEventAt) : 0),
      ),
    [cameras, filtered],
  );

  const conn = CONNECTION_LABEL[connection] ?? CONNECTION_LABEL.OFFLINE;
  const services = health?.services ?? [];
  const healthy = services.filter((s) => s.status === 'HEALTHY').length;

  return (
    <div className="p-4 sm:p-6">
      {/* ── Primary: system state ─────────────────────────────────────── */}
      <div className="flex flex-col gap-4 rounded-lg border border-line bg-surface-1 p-5 lg:flex-row lg:items-stretch lg:gap-0 lg:divide-x lg:divide-line">
        <div className="grid flex-1 grid-cols-2 gap-y-1 divide-line sm:grid-cols-4 sm:divide-x">
          <Stat label="Cameras online" value={kpis ? `${kpis.camerasOnline}/${kpis.totalCameras}` : '—'} sub={stats.online != null ? `${stats.degraded} degraded · ${stats.offline} offline` : undefined} to="/cameras" />
          <Stat label="Active alerts" value={counts.ACTIVE} sub="need a decision" tone={counts.ACTIVE > 0 ? 'danger' : 'default'} to="/alerts" />
          <Stat label="Detections · 24 h" value={kpis ? kpis.vehicleDetections24h.toLocaleString('en-IN') : '—'} sub={kpis ? `${kpis.anprReads24h.toLocaleString('en-IN')} plate reads` : undefined} to="/events" />
          <Stat label="Wanted matches · 24 h" value={kpis ? kpis.watchlistMatches24h : '—'} sub="against the FIR list" tone={kpis && kpis.watchlistMatches24h > 0 ? 'danger' : 'default'} to="/watchlist" />
        </div>
        {/* Pipeline + realtime channel */}
        <div className="flex shrink-0 flex-col justify-center gap-2 border-t border-line pt-4 lg:w-56 lg:border-l lg:border-t-0 lg:pl-6 lg:pt-0">
          <span className={cn('flex items-center gap-1.5 text-xs font-semibold', conn.tone)} title={`Realtime channel: ${connection}`}>
            <span className={cn('h-1.5 w-1.5 rounded-full bg-current', connection === 'LIVE' && 'animate-pulse-dot')} aria-hidden />
            {conn.label}
          </span>
          <span className="text-xs text-ink-muted" title="Platform services reporting healthy">
            Pipeline {sysLoading ? '—' : `${healthy}/${services.length} services healthy`}
            {health ? ` · ${health.ingestFps.toFixed(1)} fps` : ''}
          </span>
          <Link to="/system" className="text-xs font-medium text-accent hover:underline">
            System status →
          </Link>
        </div>
      </div>

      {/* ── Body ──────────────────────────────────────────────────────── */}
      <div className="mt-6 grid min-h-0 gap-6 xl:grid-cols-[1fr_360px]">
        <div className="flex min-w-0 flex-col gap-10">
          {/* Primary visual: live mosaic with real detection overlays */}
          <section>
            <div className="mb-3 flex flex-wrap items-baseline justify-between gap-3">
              <div className="flex items-baseline gap-3">
                <SectionLabel>Live cameras</SectionLabel>
                <span className="text-xs text-ink-faint">
                  detection boxes rendered by the CV engine · open a camera for full control
                </span>
              </div>
              <Link to="/cameras" className={buttonClass('ghost', 'xs')}>
                All cameras <ArrowRight size={11} aria-hidden />
              </Link>
            </div>
            <Boundary
              loading={camsLoading}
              error={camsError}
              isEmpty={(filtered ?? cameras).length === 0}
              emptyTitle="No cameras in the network"
            >
              <DashboardMosaic cameras={mosaicCameras} count={4} />
            </Boundary>
          </section>

          {/* Detail: attention list */}
          <section>
            <div className="mb-3 flex items-center justify-between gap-3">
              <div className="flex items-baseline gap-3">
                <SectionLabel>Needs attention</SectionLabel>
                <span className="text-xs text-ink-faint">
                  {attention.length > 0 ? `${attention.length} alert${attention.length > 1 ? 's' : ''}, most severe first` : 'all clear'}
                </span>
              </div>
              {counts.ACTIVE > attention.length && (
                <Link to="/alerts" className={buttonClass('ghost', 'xs')}>
                  All alerts <ArrowRight size={11} aria-hidden />
                </Link>
              )}
            </div>
            <Boundary
              loading={camsLoading && active.length === 0 && alertHistory.length === 0}
              isEmpty={attention.length === 0}
              emptyTitle="No active alerts"
              emptyDetail="When a wanted vehicle is recognised, the case appears here instantly."
            >
              <div className="space-y-3">
                {attention.map((a) => (
                  <AlertItem key={a.id} alert={a} onAcknowledge={acknowledge} compact />
                ))}
              </div>
            </Boundary>
          </section>

          {/* The single trend chart */}
          <section>
            <Card>
              <CardHeader
                title="Vehicle traffic — last 24 hours"
                subtitle="Every vehicle the network recorded, by hour"
                actions={
                  <Link to="/events" className={buttonClass('ghost', 'xs')}>
                    Vehicle log <ArrowRight size={11} aria-hidden />
                  </Link>
                }
              />
              <CardBody className="p-4 pr-6">
                <VolumeChart data={volume24h} />
              </CardBody>
            </Card>
          </section>
        </div>

        {/* ── Rail ────────────────────────────────────────────────────── */}
        <aside className="flex min-w-0 flex-col gap-6">
          <Card className="max-h-[480px]">
            <CardHeader title="Detection feed" subtitle="Realtime channel" />
            <CardBody className="flex min-h-0 flex-col">
              <LiveDetections seed={events} max={30} />
            </CardBody>
          </Card>

          <Card>
            <CardHeader
              title="Wanted today"
              subtitle="Plates flagged on the FIR list"
              actions={
                <Link to="/watchlist" className={buttonClass('ghost', 'xs')}>
                  Manage
                </Link>
              }
            />
            <CardBody>
              {watchlistToday.length === 0 ? (
                <p className="flex items-center gap-2 px-5 py-4 text-xs text-ink-faint">
                  <ShieldAlert size={14} className="text-online" aria-hidden />
                  No wanted vehicle has been recognised in the last 24 hours.
                </p>
              ) : (
                <ul className="divide-y divide-line/70">
                  {watchlistToday.map((w) => (
                    <li key={w.plate}>
                      <Link
                        to={`/vehicles/${w.plate}`}
                        className="flex items-center gap-3 px-5 py-3 transition-colors hover:bg-surface-2/70 active:bg-surface-3/60"
                      >
                        <span className={cn('h-8 w-[3px] rounded-full', w.severity === 'CRITICAL' ? 'bg-critical' : 'bg-warn')} aria-hidden />
                        <span className="plate flex-1 text-[13px] font-semibold text-ink">{w.plate}</span>
                        <span className="text-[11px] text-ink-faint">{w.count}× · last {w.lastAt ? formatTime(w.lastAt) : '—'}</span>
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="Cameras by department" subtitle="Registry composition" />
            <CardBody>
              {deptRows.length === 0 ? (
                <p className="px-5 py-4 text-xs text-ink-faint">No cameras registered yet.</p>
              ) : (
                <ul className="px-5 py-2">
                  {deptRows.map((d) => (
                    <li key={d.dept} className="flex items-center justify-between border-b border-line/60 py-2.5 text-[13px] last:border-b-0">
                      <span className="min-w-0 truncate text-ink-muted">{d.dept}</span>
                      <span className="mono font-semibold tabular-nums text-ink">{d.count}</span>
                    </li>
                  ))}
                </ul>
              )}
            </CardBody>
          </Card>

          <Card>
            <CardBody className="flex flex-wrap items-center gap-x-4 gap-y-2 px-5 py-4">
              <div className="min-w-0 flex-1">
                <p className="text-[13px] font-semibold text-ink">City-wide view</p>
                <p className="text-xs text-ink-faint">Live map of every camera and route.</p>
              </div>
              <Link to="/gis" className={buttonClass('secondary', 'sm')}>
                Open City Map
              </Link>
            </CardBody>
          </Card>
        </aside>
      </div>

      <p className="mono mt-10 border-t border-line pt-4 text-center text-[10.5px] tracking-wide text-ink-faint">
        SENTINEL · TRINETRA AI — surveillance intelligence platform
      </p>
    </div>
  );
}
