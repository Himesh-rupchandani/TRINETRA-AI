import { useMemo } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ArrowRight, ShieldAlert } from 'lucide-react';
import { useAlerts } from '@/hooks/useAlerts';
import { useCameras } from '@/hooks/useCameras';
import { useLiveEvents } from '@/hooks/useLiveEvents';
import { useSystemStatus } from '@/features/system/useSystemStatus';
import { AlertItem } from '@/components/AlertItem';
import { CameraCard } from '@/components/CameraCard';
import { LiveDetections } from '@/components/LiveDetections';
import { DeptChart, VolumeChart } from '@/components/Charts';
import { useDashboardData } from '@/features/dashboard/useDashboardData';
import { Button, buttonClass } from '@/ui/Button';
import { Badge } from '@/ui/Badge';
import { Card, CardBody, CardHeader } from '@/ui/Card';
import { SectionLabel } from '@/ui/Card';
import { Stat } from '@/ui/Links';
import { Boundary } from '@/ui/Feedback';
import { cn } from '@/lib/utils';
import { formatTime } from '@/lib/uiHelpers';

/**
 * SENTINEL Command Center — the single pane of operations:
 * attention → live network → detail. One screen, no card sprawl.
 */
export default function Dashboard() {
  const navigate = useNavigate();
  const { active, counts, acknowledge } = useAlerts();
  const { cameras, filtered, stats, loading: camsLoading, error: camsError } = useCameras();
  const { events } = useLiveEvents();
  const { health, kpis, loading: sysLoading } = useSystemStatus();

  const {
    cameraWall,
    attention,
    volume24h,
    deptBars,
    watchlistToday,
  } = useDashboardData({ alerts: active, cameras: filtered ?? cameras, liveEvents: events });

  const live = useMemo(
    () => (health?.services ?? []).filter((s) => s.status === 'HEALTHY').length,
    [health],
  );
  const services = health?.services?.length ?? 0;

  return (
    <div className="p-4 sm:p-6 lg:p-8">
      {/* ── Status band: the health of the platform, one line ─────────── */}
      <div className="grid grid-cols-2 divide-line rounded-xl border border-line bg-surface-1 shadow-xs sm:grid-cols-3 sm:divide-x lg:grid-cols-6">
        <Stat label="Cameras online" value={kpis ? kpis.camerasOnline : '—'} sub={kpis ? `${kpis.totalCameras} in the network` : undefined} to="/cameras" />
        <Stat label="Active alerts" value={counts.ACTIVE} sub="need a decision" tone={counts.ACTIVE > 0 ? 'danger' : 'default'} to="/alerts" />
        <Stat label="Detections · 24 h" value={kpis ? kpis.vehicleDetections24h.toLocaleString('en-IN') : '—'} sub="vehicles recorded" to="/events" />
        <Stat label="Plate reads · 24 h" value={kpis ? kpis.anprReads24h.toLocaleString('en-IN') : '—'} sub="ANPR engine" to="/events?eventType=ANPR_READ" />
        <Stat label="Wanted matches · 24 h" value={kpis ? kpis.watchlistMatches24h : '—'} sub="cross-checked against FIR list" tone={kpis && kpis.watchlistMatches24h > 0 ? 'danger' : 'default'} to="/watchlist" />
        <Stat label="Platform services" value={sysLoading ? '—' : `${live}/${services}`} sub={health ? `ingest ${health.ingestFps.toFixed(1)} fps` : undefined} to="/system" />
      </div>

      {/* ── Body: attention first, then the network, then detail ──────── */}
      <div className="mt-6 grid min-h-0 gap-6 xl:grid-cols-[1fr_380px]">
        <div className="flex min-w-0 flex-col gap-6">
          {/* Attention list */}
          <section>
            <div className="mb-3 flex items-center justify-between gap-3">
              <div className="flex items-baseline gap-3">
                <SectionLabel>Needs attention</SectionLabel>
                <span className="text-xs text-ink-faint">
                  {attention.length > 0 ? `${attention.length} open alert${attention.length > 1 ? 's' : ''}, most severe first` : 'all clear'}
                </span>
              </div>
              {counts.ACTIVE > attention.length && (
                <Link to="/alerts" className={buttonClass('ghost', 'xs')}>
                  All alerts <ArrowRight size={11} aria-hidden />
                </Link>
              )}
            </div>
            <Boundary
              loading={camsLoading && active.length === 0}
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

          {/* Camera network */}
          <section>
            <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
              <div className="flex items-baseline gap-3">
                <SectionLabel>Camera network</SectionLabel>
                <span className="text-xs text-ink-faint">
                  {camsLoading ? 'loading…' : `${stats.online} online · ${stats.degraded} degraded · ${stats.offline} offline`}
                </span>
              </div>
              <div className="flex items-center gap-2">
                <Badge tone="neutral">{kpis ? kpis.totalCameras : '—'} total</Badge>
                <Link to="/cameras" className={buttonClass('ghost', 'xs')}>
                  Open monitors <ArrowRight size={11} aria-hidden />
                </Link>
              </div>
            </div>
            <Boundary
              loading={camsLoading}
              error={camsError}
              isEmpty={(cameraWall?.length ?? 0) === 0}
              emptyTitle="No cameras in the network"
            >
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 2xl:grid-cols-3">
                {(cameraWall ?? []).map((c) => (
                  <CameraCard key={c.id} camera={c} />
                ))}
              </div>
            </Boundary>
          </section>

          {/* Traffic profile */}
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

        {/* ── Rail: live feed, watchlist, departments ─────────────────── */}
        <aside className="flex min-w-0 flex-col gap-6">
          <Card className="max-h-[520px]">
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
                        <span className={cn('h-8 w-[3px] rounded-full', w.severity === 'CRITICAL' ? 'bg-critical' : 'bg-high')} aria-hidden />
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
            <CardHeader title="Cameras by department" subtitle="Network composition" />
            <CardBody className="p-4">
              <DeptChart data={deptBars} />
            </CardBody>
          </Card>

          <Card>
            <CardBody className="flex flex-wrap items-center gap-x-4 gap-y-2 px-5 py-4">
              <div className="min-w-0 flex-1">
                <p className="text-[13px] font-semibold text-ink">City-wide view</p>
                <p className="text-xs text-ink-faint">Live map of every camera and route.</p>
              </div>
              <Button variant="secondary" onClick={() => navigate('/gis')}>
                Open City Map
              </Button>
            </CardBody>
          </Card>
        </aside>
      </div>

      <p className="mono mt-8 border-t border-line pt-4 text-center text-[10.5px] tracking-wide text-ink-faint">
        SENTINEL · TRINETRA AI — surveillance intelligence platform
      </p>
    </div>
  );
}
