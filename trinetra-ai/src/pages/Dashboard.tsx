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
  Users,
} from 'lucide-react';
import { KpiCard } from '@/components/dashboard/KpiCard';
import { CameraActivityChart, DetectionTrend } from '@/components/dashboard/Charts';
import { LiveEventFeed } from '@/components/events/LiveEventFeed';
import { AlertCard } from '@/components/alerts/AlertCard';
import { LazyMap } from '@/components/gis/LazyMap';
import { CameraCard } from '@/components/camera/CameraCard';
import { Panel, AsyncBoundary, EmptyState } from '@/components/common/Panel';
import { ServiceStatusChip, StatusChip } from '@/components/common/Chips';
import { useCameras } from '@/hooks/useCameras';
import { useAlerts } from '@/hooks/useAlerts';
import { useAsync } from '@/hooks/useAsync';
import { eventService } from '@/services/eventService';
import { systemService } from '@/services/systemService';
import { formatNumber, formatTime, prettyVehicleClass } from '@/lib/utils';

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

      {/* KPI strip */}
      <section
        className="kpi-stagger grid grid-cols-2 gap-3 sm:grid-cols-3 sm:gap-4"
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

      {/* Who built this and what it does — plain words, no jargon. */}
      <section className="panel overflow-hidden" aria-label="About the team and the project">
        <div className="grid lg:grid-cols-2">
          <div className="flex flex-col bg-gradient-to-br from-blue-100/60 via-blue-50/40 to-white p-5 sm:p-6">
            <div className="flex items-center gap-3">
              <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-gradient-to-br from-blue-500 to-blue-700 text-white shadow-md" aria-hidden>
                <Cctv size={20} aria-hidden />
              </span>
              <div>
                <p className="chip w-fit border-blue-200 bg-blue-500/10 font-bold uppercase tracking-widest text-blue-700">
                  About the project
                </p>
                <h2 className="mt-1.5 text-lg font-extrabold tracking-tight text-ink">One screen for every camera in the city</h2>
              </div>
            </div>
            <p className="mb-4 mt-3 text-sm leading-relaxed text-ink-muted">
              TRINETRA AI started with a simple observation: a control room may have dozens
              of CCTV feeds, but an officer can only watch a few at a time. So we joined
              the pieces together — live cameras, automatic number-plate reading, and a
              wanted-vehicle list — in a single dashboard. When a listed vehicle passes
              any camera, the control room knows within seconds, with the photo, the
              camera location, and the route it took.
            </p>
            <dl className="mt-auto divide-y divide-line/70 rounded-xl border border-line bg-white/80 px-4 shadow-sm">
              <div className="flex items-center justify-between gap-3 py-3">
                <dt className="text-2xs font-semibold uppercase tracking-wide text-ink-faint">Live Cameras</dt>
                <dd className="text-right text-xs">
                  <button type="button" className="link-btn" onClick={() => navigate('/cameras')}>
                    Open feeds <ArrowRight size={13} aria-hidden />
                  </button>
                </dd>
              </div>
              <div className="flex items-center justify-between gap-3 py-3">
                <dt className="text-2xs font-semibold uppercase tracking-wide text-ink-faint">Find a Vehicle</dt>
                <dd className="text-right text-xs">
                  <button type="button" className="link-btn" onClick={() => navigate('/vehicles')}>
                    Trace a plate <ArrowRight size={13} aria-hidden />
                  </button>
                </dd>
              </div>
              <div className="flex items-center justify-between gap-3 py-3">
                <dt className="text-2xs font-semibold uppercase tracking-wide text-ink-faint">Alerts</dt>
                <dd className="text-right text-xs">
                  <button type="button" className="link-btn" onClick={() => navigate('/alerts')}>
                    View alerts <ArrowRight size={13} aria-hidden />
                  </button>
                </dd>
              </div>
            </dl>
          </div>

          <div className="flex flex-col border-t border-line bg-gradient-to-bl from-violet-100/60 via-violet-50/40 to-white p-5 sm:p-6 lg:border-l lg:border-t-0">
            <div className="flex items-center gap-3">
              <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-gradient-to-br from-violet-500 to-violet-700 text-white shadow-md" aria-hidden>
                <Users size={20} aria-hidden />
              </span>
              <div>
                <p className="chip w-fit border-violet-200 bg-violet-500/10 font-bold uppercase tracking-widest text-violet-700">
                  About our team
                </p>
                <h2 className="mt-1.5 text-lg font-extrabold tracking-tight text-ink">Built by students, for the officers on duty</h2>
              </div>
            </div>
            <p className="mb-4 mt-3 text-sm leading-relaxed text-ink-muted">
              We are Team Trinetra, building for the Gujarat Police Innovation Hackathon.
              Our aim was practical rather than flashy: software a duty officer can learn
              in ten minutes and trust at 2 in the morning. Everything on this screen
              runs on real camera events — detection, tracking and plate reading feed
              straight into the log, the map and the alerts you see here.
            </p>
            <dl className="mt-auto divide-y divide-line/70 rounded-xl border border-line bg-white/80 px-4 shadow-sm">
              <div className="flex items-center justify-between gap-3 py-3">
                <dt className="text-2xs font-semibold uppercase tracking-wide text-ink-faint">Built for</dt>
                <dd className="text-right text-xs font-bold text-ink">Gujarat Police Hackathon</dd>
              </div>
              <div className="flex items-center justify-between gap-3 py-3">
                <dt className="text-2xs font-semibold uppercase tracking-wide text-ink-faint">What it does</dt>
                <dd className="text-right text-xs font-bold text-ink">CCTV + plate reading + alerts</dd>
              </div>
              <div className="flex items-center justify-between gap-3 py-3">
                <dt className="text-2xs font-semibold uppercase tracking-wide text-ink-faint">Vehicle search</dt>
                <dd className="text-right text-xs">
                  <Link className="link-btn" to="/vehicles">
                    Open Find Vehicle <ArrowRight size={13} aria-hidden />
                  </Link>
                </dd>
              </div>
            </dl>
          </div>
        </div>
      </section>
    </div>
  );
}
