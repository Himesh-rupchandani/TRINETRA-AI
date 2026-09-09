import { useMemo } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  ArrowRight,
  Bell,
  Car,
  Cctv,
  Map as MapIcon,
  ScanLine,
  ShieldAlert,
  Users,
} from 'lucide-react';
import { KpiCard } from '@/components/dashboard/KpiCard';
import { AlertCard } from '@/components/alerts/AlertCard';
import { LazyMap } from '@/components/gis/LazyMap';
import { Panel, EmptyState } from '@/components/common/Panel';
import { useCameras } from '@/hooks/useCameras';
import { useAlerts } from '@/hooks/useAlerts';
import { useAsync } from '@/hooks/useAsync';
import { eventService } from '@/services/eventService';
import { systemService } from '@/services/systemService';
import { cn, formatNumber, formatPct, relativeTime } from '@/lib/utils';
import type { VehicleEvent } from '@/types';

/**
 * COMMAND CENTER (tight home)
 * Status board up top, then the only two live blocks that earn their place
 * here - alerts that need action and the map - with the team story closing
 * the page. Full lists live on their own pages, one click away.
 */

export default function Dashboard() {
  const navigate = useNavigate();
  const { cameras, stats } = useCameras();
  const { active: activeAlerts, acknowledge, resolve } = useAlerts();
  const recent = useAsync(() => eventService.recent(120), []);
  const kpis = useAsync(() => systemService.kpis(), []);

  const recentEvents = useMemo(() => recent.data ?? [], [recent.data]);
  const detectionPoints = useMemo(
    () => recentEvents.filter((e) => e.watchlistMatch).slice(0, 25),
    [recentEvents],
  );
  const sevCounts = useMemo(() => {
    const c: Record<string, number> = { CRITICAL: 0, HIGH: 0, MEDIUM: 0, LOW: 0 };
    activeAlerts.forEach((a) => {
      if (a.severity in c) c[a.severity] += 1;
    });
    return c;
  }, [activeAlerts]);
  const latestSeen = useMemo(() => {
    let best: string | undefined;
    let t = -Infinity;
    for (const e of recentEvents) {
      const d = new Date(e.timestamp).getTime();
      if (d > t) {
        t = d;
        best = e.timestamp;
      }
    }
    return best;
  }, [recentEvents]);
  const lastHourCount = useMemo(
    () => recentEvents.filter((e) => Date.now() - new Date(e.timestamp).getTime() <= 3_600_000).length,
    [recentEvents],
  );
  const lastMatch = useMemo(() => {
    let best: VehicleEvent | undefined;
    let t = -Infinity;
    for (const e of recentEvents) {
      if (!e.watchlistMatch) continue;
      const d = new Date(e.timestamp).getTime();
      if (d > t) {
        t = d;
        best = e;
      }
    }
    return best;
  }, [recentEvents]);
  const camerasOnline = kpis.data?.camerasOnline ?? stats.online;
  const camerasTotal = kpis.data?.totalCameras ?? stats.total;
  const camerasHealthPct = camerasTotal > 0 ? Math.round((camerasOnline / camerasTotal) * 100) : 0;
  const readRate =
    kpis.data?.anprReads24h != null && kpis.data?.vehicleDetections24h
      ? kpis.data.anprReads24h / kpis.data.vehicleDetections24h
      : undefined;
  return (
    <div className="flex flex-col gap-4 p-4 sm:p-5 xl:p-6">

      {/* Ops status board: alerts hero first, then network health and 24h counters. */}
      <section
        className="kpi-stagger grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-6"
        aria-label="Operations status board"
      >
        <KpiCard
          label="Alerts to Action"
          value={formatNumber(activeAlerts.length)}
          sub={activeAlerts.length ? 'Needs an officer\u2019s eyes' : 'All clear \u2014 nothing pending'}
          tone={activeAlerts.length ? 'critical' : 'online'}
          tile={activeAlerts.length ? 'red' : 'green'}
          icon={Bell}
          to="/alerts"
          cta="View alerts"
          className="col-span-2 lg:col-span-2"
          extra={
            activeAlerts.length > 0 ? (
              <div className="flex flex-wrap gap-1.5">
                {sevCounts.CRITICAL > 0 && (
                  <span className="chip border-red-200 bg-red-500/10 text-red-700">
                    {sevCounts.CRITICAL} critical
                  </span>
                )}
                {sevCounts.HIGH > 0 && (
                  <span className="chip border-orange-200 bg-orange-500/10 text-orange-700">
                    {sevCounts.HIGH} high
                  </span>
                )}
                {sevCounts.MEDIUM > 0 && (
                  <span className="chip border-amber-200 bg-amber-500/10 text-amber-700">
                    {sevCounts.MEDIUM} medium
                  </span>
                )}
                {sevCounts.LOW > 0 && (
                  <span className="chip border-slate-200 bg-slate-500/10 text-slate-600">
                    {sevCounts.LOW} low
                  </span>
                )}
              </div>
            ) : undefined
          }
        />
        <KpiCard
          label="Camera Network"
          value={`${formatNumber(camerasOnline)}/${formatNumber(camerasTotal)}`}
          sub={
            stats.degraded + stats.offline > 0
              ? `${stats.degraded} with problems \u00b7 ${stats.offline} offline`
              : 'Every camera is online'
          }
          tile="green"
          icon={Cctv}
          to="/registry"
          cta="View all cameras"
          loading={kpis.loading}
          extra={
            <div
              className="h-1.5 overflow-hidden rounded-full bg-slate-500/15"
              role="progressbar"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={camerasHealthPct}
              aria-label="Cameras online"
            >
              <div
                className={cn(
                  'h-full rounded-full',
                  stats.offline > 0 ? 'bg-red-500' : stats.degraded > 0 ? 'bg-amber-500' : 'bg-emerald-500',
                )}
                style={{ width: `${camerasHealthPct}%` }}
              />
            </div>
          }
        />
        <KpiCard
          label="Vehicles Seen"
          value={formatNumber(kpis.data?.vehicleDetections24h)}
          sub={
            latestSeen ? (
              <>
                Last seen {relativeTime(latestSeen)} · {lastHourCount} in the last hour
              </>
            ) : (
              'In last 24 hours'
            )
          }
          tile="blue"
          icon={Car}
          to="/events"
          cta="View vehicles"
          loading={kpis.loading}
        />
        <KpiCard
          label="Number Plates Read"
          value={formatNumber(kpis.data?.anprReads24h)}
          sub={readRate != null ? `${formatPct(readRate)} of vehicles read` : 'Read automatically'}
          tile="sky"
          icon={ScanLine}
          to="/events"
          cta="View logs"
          loading={kpis.loading}
        />
        <KpiCard
          label="Wanted Vehicles Found"
          value={formatNumber(kpis.data?.watchlistMatches24h)}
          sub={
            lastMatch?.plate ? (
              <>
                Last: <span className="font-mono">{lastMatch.plate}</span> ·{' '}
                {relativeTime(lastMatch.timestamp)}
              </>
            ) : (
              'No matches in 24 hours'
            )
          }
          tone={kpis.data?.watchlistMatches24h ? 'critical' : 'neutral'}
          tile="orange"
          icon={ShieldAlert}
          to="/watchlist"
          cta="View wanted list"
          loading={kpis.loading}
        />
      </section>

      {/* The only two live blocks that earn home-page space: alerts that
          need action, and the map. Full lists live on their own pages. */}
      <section className="grid gap-3 sm:gap-4 xl:grid-cols-12" aria-label="Alerts and map">
        <Panel
          title="Recent Alerts"
          icon={Bell}
          className="xl:col-span-7"
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
              {activeAlerts.slice(0, 3).map((a) => (
                <AlertCard key={a.id} alert={a} onAcknowledge={acknowledge} onResolve={resolve} compact />
              ))}
            </div>
          )}
        </Panel>

        <Panel
          title="Where vehicles are being seen"
          icon={MapIcon}
          className="min-h-[380px] xl:col-span-5"
          bodyClassName="relative isolate"
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
      </section>

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
