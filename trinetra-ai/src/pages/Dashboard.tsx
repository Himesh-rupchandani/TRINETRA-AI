import { useMemo } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  Activity,
  ArrowRight,
  Bell,
  Cctv,
  Map as MapIcon,
  ScanLine,
} from 'lucide-react';
import { CameraActivityChart, DetectionTrend } from '@/components/dashboard/Charts';
import { LiveEventFeed } from '@/components/events/LiveEventFeed';
import { AlertCard } from '@/components/alerts/AlertCard';
import { TraceSearchBar } from '@/components/vehicle/TraceSearchBar';
import { LazyMap } from '@/components/gis/LazyMap';
import { CameraCard } from '@/components/camera/CameraCard';
import { Panel, AsyncBoundary, EmptyState } from '@/components/common/Panel';
import { PageHeader } from '@/components/layout/PageHeader';
import { ServiceStatusChip, StatusChip } from '@/components/common/Chips';
import { useCameras } from '@/hooks/useCameras';
import { useAlerts } from '@/hooks/useAlerts';
import { useAsync } from '@/hooks/useAsync';
import { eventService } from '@/services/eventService';
import { systemService } from '@/services/systemService';
import { cn, formatNumber, formatTime, prettyVehicleClass } from '@/lib/utils';
import { demoFlow } from '@/data/demoFlow';
import { config } from '@/lib/config';

/** One quiet stat in the network overview strip. */
function Stat({
  label,
  value,
  sub,
  to,
  tone,
  loading,
}: {
  label: string;
  value: React.ReactNode;
  sub?: React.ReactNode;
  to: string;
  tone?: 'critical';
  loading?: boolean;
}) {
  return (
    <Link
      to={to}
      className="group flex h-full min-w-0 flex-col gap-2.5 bg-surface-1 px-5 py-5 transition-colors hover:bg-surface-2/60 sm:px-6"
    >
      <p className="text-xs font-medium text-ink-muted">{label}</p>
      {loading ? (
        <div className="skeleton h-8 w-16" />
      ) : (
        <p
          className={cn(
            'font-mono text-[1.75rem] font-semibold leading-none tracking-tight tabular-nums',
            tone === 'critical' && value !== 0 ? 'text-critical' : 'text-ink',
          )}
        >
          {value}
        </p>
      )}
      {sub && <p className="text-2xs leading-snug text-ink-faint">{sub}</p>}
    </Link>
  );
}

/**
 * COMMAND CENTER
 * Hierarchy: network overview → primary action (vehicle trace) + attention →
 * live operations (cameras, detections) → geography & trend → detailed log.
 */
export default function Dashboard() {
  const navigate = useNavigate();
  const { cameras, stats, loading: camsLoading, error: camsError, refresh } = useCameras();
  const { active: activeAlerts, acknowledge, resolve } = useAlerts();
  const recent = useAsync(() => eventService.recent(120), []);
  const kpis = useAsync(() => systemService.kpis(), []);
  const health = useAsync(() => systemService.health(), []);

  const recentEvents = useMemo(() => recent.data ?? [], [recent.data]);
  const watchCameras = useMemo(
    () => [...cameras].sort((a, b) => (b.eventCount24h ?? 0) - (a.eventCount24h ?? 0)).slice(0, 8),
    [cameras],
  );
  const detectionPoints = useMemo(
    () => recentEvents.filter((e) => e.watchlistMatch).slice(0, 25),
    [recentEvents],
  );

  return (
    <div className="animate-page-in flex flex-col gap-6 p-5 sm:p-6 xl:p-8">
      <PageHeader
        title="Command Center"
        subtitle={
          <>
            {config.productName} — AI-powered surveillance intelligence by {config.appName}. Live
            camera monitoring, vehicle detection and number-plate recognition in one operations
            picture.
          </>
        }
        actions={
          <button type="button" className="btn-ghost" onClick={() => navigate('/system')}>
            <Activity size={14} aria-hidden /> System Status
          </button>
        }
      />

      {/* Network overview — one calm strip, hairline-divided at every width */}
      <section
        className="panel grid grid-cols-2 gap-px overflow-hidden bg-line sm:grid-cols-3 xl:grid-cols-6"
        aria-label="Key performance indicators"
      >
        <Stat
          label="Cameras in system"
          value={formatNumber(kpis.data?.totalCameras ?? stats.total)}
          sub="Total installed"
          to="/registry"
          loading={kpis.loading && camsLoading}
        />
        <Stat
          label="Cameras working"
          value={formatNumber(kpis.data?.camerasOnline ?? stats.online)}
          sub={`${stats.degraded} degraded · ${stats.offline} offline`}
          to="/cameras"
          loading={kpis.loading && camsLoading}
        />
        <Stat
          label="Alerts to action"
          value={formatNumber(activeAlerts.length)}
          sub="Active, pending review"
          to="/alerts"
          tone={activeAlerts.length ? 'critical' : undefined}
        />
        <Stat
          label="Vehicles seen"
          value={formatNumber(kpis.data?.vehicleDetections24h)}
          sub="Last 24 hours"
          to="/events"
          loading={kpis.loading}
        />
        <Stat
          label="Plates read"
          value={formatNumber(kpis.data?.anprReads24h)}
          sub="Automatic recognition"
          to="/events"
          loading={kpis.loading}
        />
        <Stat
          label="Wanted vehicles found"
          value={formatNumber(kpis.data?.watchlistMatches24h)}
          sub="Last 24 hours"
          to="/watchlist"
          loading={kpis.loading}
        />
      </section>

      {/* Primary action + what needs attention */}
      <section className="grid gap-5 xl:grid-cols-12">
        <Panel className="xl:col-span-8" bodyClassName="p-5 sm:p-6">
          <h2 className="text-base font-semibold text-ink">Find a vehicle</h2>
          <p className="mt-1.5 max-w-lg text-sm leading-relaxed text-ink-muted">
            Enter a registration number to see every camera sighting, the route between cameras,
            and any watchlist matches.
          </p>
          <div className="mt-5">
            <TraceSearchBar onTrace={(p) => navigate(`/vehicles/${p}`)} />
          </div>

          <div className="mt-6 border-t border-line pt-5">
            <p className="eyebrow">Guided demo</p>
            <nav className="mt-3 grid gap-2.5 sm:grid-cols-2" aria-label="Common tasks">
              {demoFlow.map((task) => (
                <Link
                  key={task.step}
                  to={task.to}
                  className="group flex items-center gap-3.5 rounded-lg border border-line px-4 py-3 transition-colors hover:border-line-strong hover:bg-surface-2/60"
                >
                  <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full border border-line font-mono text-[11px] font-semibold text-ink-faint">
                    {task.step}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-medium text-ink">{task.label}</span>
                    <span className="block truncate text-2xs text-ink-faint">{task.hint}</span>
                  </span>
                  <ArrowRight
                    size={14}
                    className="shrink-0 text-ink-faint/60 transition-colors group-hover:text-brand"
                    aria-hidden
                  />
                </Link>
              ))}
            </nav>
          </div>
        </Panel>

        <Panel
          title="Needs attention"
          icon={Bell}
          className="xl:col-span-4"
          bodyClassName="overflow-y-auto"
          actions={
            <button type="button" className="link-btn" onClick={() => navigate('/alerts')}>
              All alerts <ArrowRight size={13} aria-hidden />
            </button>
          }
        >
          {activeAlerts.length === 0 ? (
            <EmptyState title="No active alerts" detail="Nothing needs your attention right now." />
          ) : (
            <div className="space-y-3 p-4">
              {activeAlerts.slice(0, 3).map((a) => (
                <AlertCard key={a.id} alert={a} onAcknowledge={acknowledge} onResolve={resolve} compact />
              ))}
            </div>
          )}
        </Panel>
      </section>

      {/* Live operations */}
      <section className="grid gap-5 xl:grid-cols-12">
        <Panel
          title="Live cameras"
          icon={Cctv}
          className="max-h-[640px] xl:col-span-5"
          bodyClassName="overflow-y-auto"
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
          >
            <div className="flex flex-col gap-2.5 p-4">
              {watchCameras.map((c) => (
                <CameraCard key={c.id} camera={c} variant="list" />
              ))}
            </div>
          </AsyncBoundary>
        </Panel>

        <Panel
          title="Recent detections"
          icon={Activity}
          className="min-h-[360px] xl:col-span-4"
          bodyClassName="flex flex-col min-h-0"
          actions={
            <button type="button" className="link-btn" onClick={() => navigate('/events')}>
              Vehicle log <ArrowRight size={13} aria-hidden />
            </button>
          }
        >
          <LiveEventFeed seed={recentEvents.slice(0, 25)} max={40} />
        </Panel>

        <Panel
          title="Service health"
          icon={Activity}
          className="xl:col-span-3"
          actions={
            <button type="button" className="link-btn" onClick={() => navigate('/system')}>
              Details <ArrowRight size={13} aria-hidden />
            </button>
          }
        >
          <AsyncBoundary loading={health.loading} error={health.error} onRetry={health.refresh}>
            <ul className="divide-y divide-line/60">
              {(health.data?.services ?? []).map((s) => (
                <li key={s.id} className="flex items-center justify-between gap-3 px-5 py-3">
                  <div className="min-w-0">
                    <p className="truncate text-xs font-medium text-ink">{s.name}</p>
                    <p className="mt-0.5 text-2xs text-ink-faint">
                      {s.uptimePct.toFixed(2)}% · hb {formatTime(s.lastHeartbeat)}
                    </p>
                  </div>
                  <ServiceStatusChip status={s.status} />
                </li>
              ))}
            </ul>
          </AsyncBoundary>
        </Panel>
      </section>

      {/* Geography + trend */}
      <section className="grid gap-5 xl:grid-cols-12">
        <Panel
          title="Where vehicles are being seen"
          icon={MapIcon}
          className="min-h-[340px] xl:col-span-7"
          bodyClassName="relative"
          actions={
            <button type="button" className="link-btn" onClick={() => navigate('/gis')}>
              Full map <ArrowRight size={13} aria-hidden />
            </button>
          }
        >
          <LazyMap
            cameras={cameras}
            events={detectionPoints}
            className="absolute inset-0"
            onSelectCamera={(c) => navigate(`/cameras/${c.id}`)}
            zoom={11}
          />
        </Panel>

        <div className="grid gap-5 xl:col-span-5">
          <Panel title="Vehicles seen each hour" icon={Activity} className="min-h-[180px]" bodyClassName="p-4">
            <div className="h-[140px]">
              <DetectionTrend events={recentEvents} />
            </div>
          </Panel>
          <Panel title="Busiest cameras" icon={Cctv} className="min-h-[180px]" bodyClassName="p-4">
            <div className="h-[160px]">
              <CameraActivityChart events={recentEvents} />
            </div>
          </Panel>
        </div>
      </section>

      {/* Detailed log */}
      <Panel
        title="Latest vehicles seen"
        icon={ScanLine}
        actions={
          <button type="button" className="link-btn" onClick={() => navigate('/events')}>
            View all <ArrowRight size={13} aria-hidden />
          </button>
        }
      >
        <AsyncBoundary loading={recent.loading} error={recent.error} onRetry={recent.refresh}>
          <div className="overflow-x-auto">
            <table className="data-table">
              <thead>
                <tr>
                  <th scope="col">Time</th>
                  <th scope="col">Camera</th>
                  <th scope="col">Place</th>
                  <th scope="col">Plate</th>
                  <th scope="col">Vehicle type</th>
                  <th scope="col">Plate match</th>
                  <th scope="col">Status</th>
                </tr>
              </thead>
              <tbody>
                {recentEvents.slice(0, 8).map((e) => (
                  <tr
                    key={e.id}
                    className={e.plate ? 'cursor-pointer' : undefined}
                    onClick={e.plate ? () => navigate(`/vehicles/${e.plate}`) : undefined}
                  >
                    <td className="font-mono tabular-nums text-ink-muted">{formatTime(e.timestamp)}</td>
                    <td className="font-mono text-ink-muted">{e.cameraName}</td>
                    <td className="max-w-[220px] truncate text-ink-muted">{e.location}</td>
                    <td className="plate text-ink">{e.plate || '—'}</td>
                    <td className="text-ink-muted">{prettyVehicleClass(e.vehicleClass)}</td>
                    <td className="font-mono tabular-nums text-ink-muted">
                      {e.plateConfidence ? `${e.plateConfidence.toFixed(1)}%` : '—'}
                    </td>
                    <td>
                      {e.watchlistMatch ? (
                        <span className="chip border-critical/30 bg-critical/10 text-critical">Watchlist</span>
                      ) : (
                        <StatusChip status="ONLINE" showDot={false} />
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </AsyncBoundary>
      </Panel>
    </div>
  );
}
