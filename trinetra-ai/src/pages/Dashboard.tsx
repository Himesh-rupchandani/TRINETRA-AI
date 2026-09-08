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
import { DEMO_PLATE } from '@/data/demoFlow';

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
  const featuredCamera = cameras.find((c) => c.status === 'ONLINE') ?? cameras[0] ?? null;

  return (
    <div className="flex flex-col gap-4 p-4 sm:p-5 xl:p-6">

      {/* Hero: registration number is always the fastest path into the product */}
      <section className="panel flex flex-col gap-5 bg-gradient-to-br from-white via-white to-sky-50 p-5 sm:p-6 lg:flex-row lg:items-stretch">
        <div className="flex flex-col justify-center lg:w-[290px] lg:shrink-0">
          <span className="chip w-fit border-brand/25 bg-brand/10 font-bold uppercase tracking-widest text-brand">
            Start here
          </span>
          <div className="mt-3 flex items-center gap-3">
            <span className="float-soft grid h-12 w-12 shrink-0 place-items-center rounded-2xl bg-gradient-to-br from-blue-500 to-blue-700 text-white shadow-md" aria-hidden>
              <Car size={24} aria-hidden />
            </span>
            <h2 className="text-xl font-bold tracking-tight text-ink">Find a Vehicle</h2>
          </div>
          <p className="mt-2.5 text-sm leading-relaxed text-ink-muted">
            Search any vehicle by number plate to see all camera sightings, routes, and alerts.
          </p>
          <ul className="mt-3.5 space-y-2" aria-label="What you get">
            {[
              { icon: Cctv, text: 'Every camera sighting' },
              { icon: MapIcon, text: 'Route from camera to camera' },
              { icon: Bell, text: 'Instant wanted-list alerts' },
            ].map((f) => (
              <li key={f.text} className="flex items-center gap-2 text-xs font-medium text-ink-muted">
                <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-emerald-500/12 text-emerald-600">
                  <f.icon size={13} aria-hidden />
                </span>
                {f.text}
              </li>
            ))}
          </ul>
        </div>
        <div className="flex min-w-0 flex-1 flex-col">
          <TraceSearchBar onTrace={(p) => navigate(`/vehicles/${p}`)} />
          <button
            type="button"
            onClick={() => navigate(featuredCamera ? `/cameras/${featuredCamera.id}` : '/cameras')}
            className="group relative mt-4 block w-full overflow-hidden rounded-xl text-left shadow-panel ring-1 ring-black/5"
          >
            <img
              src="/cctv/cctv-02.jpg"
              alt=""
              aria-hidden
              className="h-44 w-full object-cover transition-transform duration-300 group-hover:scale-105"
            />
            <span aria-hidden className="absolute inset-0 bg-gradient-to-t from-slate-950/85 via-slate-950/20 to-transparent" />
            <span className="absolute left-3 top-3 inline-flex items-center gap-1.5 rounded-full bg-critical px-2.5 py-1 text-2xs font-bold uppercase tracking-widest text-white">
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-white" aria-hidden /> Live
            </span>
            <span className="absolute inset-x-3 bottom-3 flex items-end justify-between gap-2">
              <span className="min-w-0">
                <span className="block truncate text-sm font-bold text-white">
                  {featuredCamera ? `${featuredCamera.id.toUpperCase()} · ${featuredCamera.name}` : 'Live camera network'}
                </span>
                <span className="block truncate text-2xs text-slate-300">
                  {featuredCamera ? featuredCamera.location : 'Open the live wall'}
                </span>
              </span>
              <span className="inline-flex shrink-0 items-center gap-1.5 rounded-lg bg-white/15 px-3 py-2 text-xs font-bold text-white backdrop-blur-sm transition-colors group-hover:bg-white/25">
                Open live view <ArrowRight size={14} aria-hidden />
              </span>
            </span>
          </button>
        </div>
      </section>

      {/* Who built this and what it does — plain words, no jargon. */}
      <section className="panel p-5 sm:p-6" aria-label="About the team and the project">
        <div className="grid gap-6 lg:grid-cols-2 lg:gap-8">
          <div>
            <div className="flex items-center gap-3">
              <IconTile tone="blue" size="lg">
                <Cctv size={20} aria-hidden />
              </IconTile>
              <div>
                <p className="text-2xs font-bold uppercase tracking-[0.14em] text-ink-faint">
                  About the project
                </p>
                <h2 className="text-base font-bold text-ink">One screen for every camera in the city</h2>
              </div>
            </div>
            <p className="mt-3 text-sm leading-relaxed text-ink-muted">
              TRINETRA AI started with a simple observation: a control room may have dozens
              of CCTV feeds, but an officer can only watch a few at a time. So we joined
              the pieces together — live cameras, automatic number-plate reading, and a
              wanted-vehicle list — in a single dashboard. When a listed vehicle passes
              any camera, the control room knows within seconds, with the photo, the
              camera location, and the route it took.
            </p>
            <ul className="mt-4 space-y-2.5">
              <li className="flex items-start gap-2.5 text-sm text-ink-muted">
                <IconTile tone="green" size="sm" className="mt-0.5">
                  <Cctv size={14} aria-hidden />
                </IconTile>
                <span>
                  <button type="button" className="link-btn" onClick={() => navigate('/cameras')}>
                    Live Cameras
                  </button>{' '}
                  — open any feed straight from the bar above.
                </span>
              </li>
              <li className="flex items-start gap-2.5 text-sm text-ink-muted">
                <IconTile tone="sky" size="sm" className="mt-0.5">
                  <Car size={14} aria-hidden />
                </IconTile>
                <span>
                  <button type="button" className="link-btn" onClick={() => navigate('/vehicles')}>
                    Find a Vehicle
                  </button>{' '}
                  — trace a number plate across every sighting.
                </span>
              </li>
              <li className="flex items-start gap-2.5 text-sm text-ink-muted">
                <IconTile tone="red" size="sm" className="mt-0.5">
                  <Bell size={14} aria-hidden />
                </IconTile>
                <span>
                  <button type="button" className="link-btn" onClick={() => navigate('/alerts')}>
                    Alerts
                  </button>{' '}
                  — wanted-list matches flagged the moment they happen.
                </span>
              </li>
            </ul>
          </div>

          <div className="lg:border-l lg:border-line lg:pl-8">
            <div className="flex items-center gap-3">
              <IconTile tone="purple" size="lg">
                <Users size={20} aria-hidden />
              </IconTile>
              <div>
                <p className="text-2xs font-bold uppercase tracking-[0.14em] text-ink-faint">
                  About our team
                </p>
                <h2 className="text-base font-bold text-ink">Built by students, for the officers on duty</h2>
              </div>
            </div>
            <p className="mt-3 text-sm leading-relaxed text-ink-muted">
              We are Team Trinetra, building for the Gujarat Police Innovation Hackathon.
              Our aim was practical rather than flashy: software a duty officer can learn
              in ten minutes and trust at 2 in the morning. Everything on this screen
              runs on real camera events — detection, tracking and plate reading feed
              straight into the log, the map and the alerts you see here.
            </p>
            <dl className="mt-4 space-y-2.5 rounded-xl border border-line bg-surface-2/60 p-3.5">
              <div className="flex items-center justify-between gap-3">
                <dt className="text-2xs font-semibold uppercase tracking-wide text-ink-faint">Built for</dt>
                <dd className="text-right text-xs font-semibold text-ink">Gujarat Police Hackathon</dd>
              </div>
              <div className="flex items-center justify-between gap-3">
                <dt className="text-2xs font-semibold uppercase tracking-wide text-ink-faint">What it does</dt>
                <dd className="text-right text-xs font-semibold text-ink">CCTV + plate reading + alerts</dd>
              </div>
              <div className="flex items-center justify-between gap-3">
                <dt className="text-2xs font-semibold uppercase tracking-wide text-ink-faint">Try it now</dt>
                <dd className="text-right text-xs">
                  <Link className="link-btn font-mono" to={`/vehicles/${DEMO_PLATE}`}>
                    Trace {DEMO_PLATE} <ArrowRight size={13} aria-hidden />
                  </Link>
                </dd>
              </div>
            </dl>
          </div>
        </div>
      </section>

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
    </div>
  );
}
