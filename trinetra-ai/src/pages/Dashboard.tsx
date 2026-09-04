import { useMemo } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  Activity,
  ArrowRight,
  Bell,
  Car,
  Cctv,
  Map as MapIcon,
  ScanLine,
  ShieldAlert,
  Signal,
} from 'lucide-react';
import { KpiCard } from '@/components/dashboard/KpiCard';
import { CameraActivityChart, DetectionTrend } from '@/components/dashboard/Charts';
import { LiveEventFeed } from '@/components/events/LiveEventFeed';
import { AlertCard } from '@/components/alerts/AlertCard';
import { TraceSearchBar } from '@/components/vehicle/TraceSearchBar';
import { LazyMap } from '@/components/gis/LazyMap';
import { CameraCard } from '@/components/camera/CameraCard';
import { Panel, AsyncBoundary, EmptyState } from '@/components/common/Panel';
import { IconTile } from '@/components/common/IconTile';
import { ServiceStatusChip, StatusChip } from '@/components/common/Chips';
import { useCameras } from '@/hooks/useCameras';
import { useAlerts } from '@/hooks/useAlerts';
import { useAsync } from '@/hooks/useAsync';
import { eventService } from '@/services/eventService';
import { systemService } from '@/services/systemService';
import { formatNumber, formatTime, prettyVehicleClass } from '@/lib/utils';
import { demoFlow } from '@/data/demoFlow';

/**
 * COMMAND CENTER
 * Camera network (left) · live event feed (centre) · active alerts (right),
 * with GIS, trend and system health below. Everything is one click from an
 * investigation.
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
    () => [...cameras].sort((a, b) => (b.eventCount24h ?? 0) - (a.eventCount24h ?? 0)).slice(0, 12),
    [cameras],
  );
  const detectionPoints = useMemo(
    () => recentEvents.filter((e) => e.watchlistMatch).slice(0, 25),
    [recentEvents],
  );

  return (
    <div className="flex flex-col gap-4 p-4 sm:p-5 xl:p-6">
      {/* Hero: registration number is always the fastest path into the product */}
      <section className="panel flex flex-col gap-5 p-5 sm:p-6 lg:flex-row lg:items-stretch">
        <div className="flex flex-col justify-center lg:w-[280px] lg:shrink-0">
          <div className="flex items-center gap-3">
            <IconTile tone="blue" size="lg">
              <Car size={20} aria-hidden />
            </IconTile>
            <h2 className="text-lg font-bold text-ink">Find a Vehicle</h2>
          </div>
          <p className="mt-2.5 text-sm leading-relaxed text-ink-muted">
            Search any vehicle by number plate to see all camera sightings, routes, and alerts.
          </p>
        </div>
        <div className="flex min-w-0 flex-1 flex-col">
          <TraceSearchBar onTrace={(p) => navigate(`/vehicles/${p}`)} />
          <nav
            className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4"
            aria-label="Common tasks"
          >
            {demoFlow.map((task) => (
              <Link
                key={task.step}
                to={task.to}
                className="group flex flex-col gap-2 rounded-xl border border-line bg-surface-2/60 p-3.5 transition-colors hover:border-brand/40 hover:bg-surface-2"
              >
                <span className="flex items-start justify-between gap-2">
                  <span className="text-xs font-bold text-ink-faint/70">{task.step}</span>
                  <IconTile tone={task.tone} size="md">
                    <task.icon size={17} aria-hidden />
                  </IconTile>
                </span>
                <span className="min-w-0">
                  <span className="block text-sm font-semibold text-ink group-hover:text-brand">
                    {task.label}
                  </span>
                  <span className="mt-1 block text-2xs leading-snug text-ink-faint">{task.hint}</span>
                </span>
                <ArrowRight
                  size={14}
                  className="mt-auto text-ink-faint/60 transition-colors group-hover:text-brand"
                  aria-hidden
                />
              </Link>
            ))}
          </nav>
        </div>
      </section>

      {/* KPI strip */}
      <section
        className="grid grid-cols-2 gap-3 sm:grid-cols-3 sm:gap-4"
        aria-label="Key performance indicators"
      >
        <KpiCard
          label="Cameras in System"
          value={formatNumber(kpis.data?.totalCameras ?? stats.total)}
          sub="Total cameras installed"
          tile="blue"
          icon={Cctv}
          to="/registry"
          cta="View all cameras"
          loading={kpis.loading && camsLoading}
        />
        <KpiCard
          label="Cameras Working"
          value={formatNumber(kpis.data?.camerasOnline ?? stats.online)}
          sub={`${stats.degraded} with problems · ${stats.offline} offline`}
          tile="green"
          icon={Signal}
          to="/cameras"
          cta="View status"
          loading={kpis.loading && camsLoading}
        />
        <KpiCard
          label="Alerts to Action"
          value={formatNumber(activeAlerts.length)}
          sub="Active alerts pending"
          tone={activeAlerts.length ? 'critical' : 'neutral'}
          tile="orange"
          icon={Bell}
          to="/alerts"
          cta="View alerts"
        />
        <KpiCard
          label="Vehicles Seen"
          value={formatNumber(kpis.data?.vehicleDetections24h)}
          sub="In last 24 hours"
          tile="purple"
          icon={Car}
          to="/events"
          cta="View vehicles"
          loading={kpis.loading}
        />
        <KpiCard
          label="Number Plates Read"
          value={formatNumber(kpis.data?.anprReads24h)}
          sub="Read automatically"
          tile="sky"
          icon={ScanLine}
          to="/events"
          cta="View logs"
          loading={kpis.loading}
        />
        <KpiCard
          label="Wanted Vehicles Found"
          value={formatNumber(kpis.data?.watchlistMatches24h)}
          sub="In last 24 hours"
          tone="critical"
          tile="red"
          icon={ShieldAlert}
          to="/watchlist"
          cta="View wanted list"
          loading={kpis.loading}
        />
      </section>

      {/* Main three-column operations row */}
      <section className="grid gap-3 sm:gap-4 xl:grid-cols-12">
        <Panel
          title="Live Cameras"
          icon={Cctv}
          className="max-h-[720px] xl:col-span-5"
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
            <div className="flex flex-col gap-2.5 p-3">
              {watchCameras.map((c) => (
                <CameraCard key={c.id} camera={c} variant="list" />
              ))}
            </div>
          </AsyncBoundary>
        </Panel>

        <Panel
          title="Recent Detections"
          icon={Activity}
          className="min-h-[340px] xl:col-span-3"
          bodyClassName="flex flex-col min-h-0"
          actions={
            <button type="button" className="link-btn" onClick={() => navigate('/events')}>
              View all <ArrowRight size={13} aria-hidden />
            </button>
          }
        >
          <LiveEventFeed seed={recentEvents.slice(0, 25)} max={40} />
        </Panel>

        <Panel
          title="Recent Alerts"
          icon={Bell}
          className="min-h-[340px] xl:col-span-4"
          bodyClassName="overflow-y-auto"
          actions={
            <button type="button" className="link-btn" onClick={() => navigate('/alerts')}>
              View all <ArrowRight size={13} aria-hidden />
            </button>
          }
        >
          {activeAlerts.length === 0 ? (
            <EmptyState title="No active alerts" detail="Nothing needs your attention right now." />
          ) : (
            <div className="space-y-3 p-3">
              {activeAlerts.slice(0, 4).map((a) => (
                <AlertCard key={a.id} alert={a} onAcknowledge={acknowledge} onResolve={resolve} compact />
              ))}
            </div>
          )}
        </Panel>
      </section>

      {/* Bottom row: GIS · trend · health */}
      <section className="grid gap-3 sm:gap-4 xl:grid-cols-12">
        <Panel
          title="Where vehicles are being seen"
          icon={MapIcon}
          className="min-h-[320px] xl:col-span-5"
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

        <div className="grid gap-3 sm:gap-4 xl:col-span-4">
          <Panel title="Vehicles seen each hour" icon={Activity} className="min-h-[160px]" bodyClassName="p-2.5">
            <div className="h-[130px]">
              <DetectionTrend events={recentEvents} />
            </div>
          </Panel>
          <Panel title="Busiest cameras" icon={Cctv} className="min-h-[160px]" bodyClassName="p-2.5">
            <div className="h-[150px]">
              <CameraActivityChart events={recentEvents} />
            </div>
          </Panel>
        </div>

        <Panel
          title="Is everything working?"
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
                <li key={s.id} className="flex items-center justify-between gap-2 px-4 py-2.5">
                  <div className="min-w-0">
                    <p className="truncate text-xs text-ink">{s.name}</p>
                    <p className="text-2xs text-ink-faint">
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

      {/* Recent detections table */}
      <Panel
        title="Latest vehicles seen"
        icon={ScanLine}
        actions={
          <button type="button" className="link-btn" onClick={() => navigate('/events')}>
            Open Event See all <ArrowRight size={13} aria-hidden />
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
                        <span className="chip border-critical/45 bg-critical/10 text-critical">Watchlist</span>
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
