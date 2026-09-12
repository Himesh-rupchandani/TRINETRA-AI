import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ArrowRight,
  Bell,
  Car,
  Cctv,
  Map as MapIcon,
  ScanLine,
  ShieldAlert,
  Video,
  Brain,
  Shield,
} from 'lucide-react';
import { KpiCard } from '@/components/dashboard/KpiCard';
import { AlertCard } from '@/components/alerts/AlertCard';
import { CameraPlayer } from '@/components/camera/CameraPlayer';
import { LazyMap } from '@/components/gis/LazyMap';
import { Panel, EmptyState } from '@/components/common/Panel';
import { useCameras } from '@/hooks/useCameras';
import { useAlerts } from '@/hooks/useAlerts';
import { useAsync } from '@/hooks/useAsync';
import { eventService } from '@/services/eventService';
import { systemService } from '@/services/systemService';
import { cn, formatNumber, formatPct, relativeTime } from '@/lib/utils';
import { config } from '@/lib/config';
import type { VehicleEvent } from '@/types';

// Professional Modules
import { CommandCenterHero } from '@/components/dashboard/CommandCenterHero';
import { BandwidthEngine } from '@/components/dashboard/BandwidthEngine';
import { AIInsightsDashboard } from '@/components/dashboard/AIInsightsDashboard';
import { VoiceAlertSystem } from '@/components/common/VoiceAlertSystem';

/** How often the Command Center KPI strip re-reads the backend (ms). */
const KPI_REFRESH_MS = 15_000;
/** How often relative "x minutes ago" labels are re-rendered (ms). */
const CLOCK_TICK_MS = 30_000;

export default function Dashboard() {
  const navigate = useNavigate();
  const { cameras, stats } = useCameras();
  const { active: activeAlerts, acknowledge, resolve } = useAlerts();
  const recent = useAsync(() => eventService.recent(120), []);
  const kpis = useAsync(() => systemService.kpis(), []);

  // The Command Center is a live wall: it used to fetch events + KPIs exactly
  // once per page load, so every counter, "last seen" and "last hour" figure
  // froze for the whole session (only alerts moved, via the realtime channel).
  // Poll both resources instead; `refresh` is a stable callback.
  useEffect(() => {
    const id = window.setInterval(() => {
      recent.refresh();
      kpis.refresh();
    }, KPI_REFRESH_MS);
    return () => window.clearInterval(id);
  }, [recent.refresh, kpis.refresh]);

  // Clock tick so relative timestamps keep ageing even when no new event lands.
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), CLOCK_TICK_MS);
    return () => window.clearInterval(id);
  }, []);

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
    () => recentEvents.filter((e) => now - new Date(e.timestamp).getTime() <= 3_600_000).length,
    [recentEvents, now],
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

  const liveCamera = useMemo(() => {
    if (!cameras.length) return null;
    const preferred = cameras.find((c) => c.id === config.defaultLiveCameraId.toLowerCase());
    if (preferred) return preferred;
    return cameras.find((c) => c.status === 'ONLINE') ?? cameras[0] ?? null;
  }, [cameras]);

  return (
    <div className="flex flex-col gap-5 p-4 sm:p-5 xl:p-6">
      {/* Command Center — Tour: command-center */}
      <div data-tour="command-center">
        <CommandCenterHero />
      </div>

      {/* System Controls */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Shield size={16} className="text-blue-600" />
          <span className="text-xs font-semibold text-ink">Gujarat Police — Statewide CCTV Intelligence Platform</span>
          <span className="hidden sm:inline-flex chip border-blue-200 bg-blue-50 text-blue-700 text-[10px] font-bold">LIVE OPERATIONS</span>
        </div>
        <VoiceAlertSystem />
      </div>

      {/* Live Camera — Tour: live-camera */}
      {liveCamera && (
        <section aria-label="Live camera" data-tour="live-camera">
          <Panel
            title={`Live Feed — ${liveCamera.name} • ${liveCamera.location}`}
            icon={Video}
            actions={
              <button type="button" className="link-btn" onClick={() => navigate(`/cameras/${liveCamera.id}`)}>
                Open full view <ArrowRight size={13} aria-hidden />
              </button>
            }
          >
            <CameraPlayer camera={liveCamera} autoRequest />
            <div className="flex items-center justify-between px-3 py-2.5 text-2xs border-t border-line bg-surface-2/50">
              <span className="text-ink-faint">Secure HLS/WHEP feed • Encrypted • Auto-reconnect 2s→30s • PTS timing</span>
              <span className="chip border-emerald-200 bg-emerald-500 text-white font-bold text-[10px]">● REC • YOLO11 • 25 FPS • 120ms latency</span>
            </div>
          </Panel>
        </section>
      )}

      {/* Operations KPIs — Tour: kpis */}
      <section
        className="kpi-stagger grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-6"
        aria-label="Operations status"
        data-tour="kpis"
      >
        <KpiCard
          label="Active Alerts"
          value={formatNumber(activeAlerts.length)}
          sub={activeAlerts.length ? 'Requires immediate attention' : 'All clear — no pending alerts'}
          tone={activeAlerts.length ? 'critical' : 'online'}
          tile={activeAlerts.length ? 'red' : 'green'}
          icon={Bell}
          to="/alerts"
          cta="View alerts"
          className="col-span-2 lg:col-span-2"
          extra={
            activeAlerts.length > 0 ? (
              <div className="flex flex-wrap gap-1.5">
                {sevCounts.CRITICAL > 0 && <span className="chip border-red-200 bg-red-500/10 text-red-700">{sevCounts.CRITICAL} critical</span>}
                {sevCounts.HIGH > 0 && <span className="chip border-orange-200 bg-orange-500/10 text-orange-700">{sevCounts.HIGH} high</span>}
                {sevCounts.MEDIUM > 0 && <span className="chip border-amber-200 bg-amber-500/10 text-amber-700">{sevCounts.MEDIUM} medium</span>}
                {sevCounts.LOW > 0 && <span className="chip border-slate-200 bg-slate-500/10 text-slate-600\">{sevCounts.LOW} low</span>}
              </div>
            ) : undefined
          }
        />
        <KpiCard
          label="Camera Network"
          value={`${formatNumber(camerasOnline)}/${formatNumber(camerasTotal)}`}
          sub={stats.degraded + stats.offline > 0 ? `${stats.degraded} degraded · ${stats.offline} offline` : 'All cameras operational'}
          tile="green"
          icon={Cctv}
          to="/registry"
          cta="View registry"
          loading={kpis.loading && !kpis.data}
          extra={
            <div className="h-1.5 overflow-hidden rounded-full bg-slate-500/15" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={camerasHealthPct}>
              <div className={cn('h-full rounded-full', stats.offline > 0 ? 'bg-red-500' : stats.degraded > 0 ? 'bg-amber-500' : 'bg-emerald-500')} style={{ width: `${camerasHealthPct}%` }} />
            </div>
          }
        />
        <KpiCard label="Vehicle Detections" value={formatNumber(kpis.data?.vehicleDetections24h)} sub={latestSeen ? <>Last seen {relativeTime(latestSeen, now)} · {lastHourCount} last hour</> : 'Last 24 hours'} tile="blue" icon={Car} to="/events" cta="View events" loading={kpis.loading && !kpis.data} />
        <KpiCard label="ANPR Reads" value={formatNumber(kpis.data?.anprReads24h)} sub={readRate != null ? `${formatPct(readRate)} read rate` : 'Automated recognition'} tile="sky" icon={ScanLine} to="/events" cta="View logs" loading={kpis.loading && !kpis.data} />
        <KpiCard label="Watchlist Matches" value={formatNumber(kpis.data?.watchlistMatches24h)} sub={lastMatch?.plate ? <>Last: <span className="font-mono\">{lastMatch.plate}</span> · {relativeTime(lastMatch.timestamp, now)}</> : 'No matches 24h'} tone={kpis.data?.watchlistMatches24h ? 'critical' : 'neutral'} tile="orange" icon={ShieldAlert} to="/watchlist" cta="Watchlist" loading={kpis.loading && !kpis.data} />
      </section>

      {/* Intelligence Modules — Tour: bandwidth-engine + ai-insights */}
      <section className="grid gap-4">
        <div className="flex items-center gap-2">
          <Brain size={18} className="text-violet-600" />
          <h2 className="text-sm font-bold tracking-tight">Intelligence & Federation Modules</h2>
          <span className="chip border-violet-200 bg-violet-50 text-violet-700 text-[10px] font-bold">PRODUCTION READY • 80K SCALE</span>
        </div>
        <div className="grid gap-4 xl:grid-cols-2">
          <div data-tour="bandwidth-engine">
            <BandwidthEngine />
          </div>
          <div data-tour="ai-insights">
            <AIInsightsDashboard />
          </div>
        </div>
      </section>

      {/* Alerts + Map — Tour: alerts-panel + map-panel */}
      <section className="grid gap-3 sm:gap-4 xl:grid-cols-12" aria-label="Alerts and map">
        <div className="xl:col-span-7" data-tour="alerts-panel">
          <Panel title="Active Alerts" icon={Bell} actions={<button type="button" className="link-btn" onClick={() => navigate('/alerts')}>View all <ArrowRight size={13} aria-hidden /></button>}>
            {activeAlerts.length === 0 ? <EmptyState title="No active alerts" detail="System is monitoring — no threats detected." /> : <div className="space-y-3 p-3">{activeAlerts.slice(0, 3).map((a) => <AlertCard key={a.id} alert={a} onAcknowledge={acknowledge} onResolve={resolve} compact />)}</div>}
          </Panel>
        </div>
        <div className="xl:col-span-5" data-tour="map-panel">
          <Panel title="Live Vehicle Sightings" icon={MapIcon} className="min-h-[380px]" bodyClassName="relative isolate" actions={<button type="button" className="link-btn" onClick={() => navigate('/gis')}>Open GIS <ArrowRight size={13} aria-hidden /></button>}>
            <div className="relative h-[340px]">
              <LazyMap cameras={cameras} events={detectionPoints} className="absolute inset-0" onSelectCamera={(c) => navigate(`/cameras/${c.id}`)} zoom={11} />
            </div>
          </Panel>
        </div>
      </section>

      {/* Live Investigation Demo — Tour: investigation-demo */}
      <section className="panel overflow-hidden border-blue-200" data-tour="investigation-demo">
        <div className="panel-header bg-gradient-to-r from-blue-50 to-indigo-50">
          <div className="flex items-center gap-3">
            <div className="grid h-9 w-9 place-items-center rounded-xl bg-blue-600 text-white shadow-sm">
              <MapIcon size={18} />
            </div>
            <div>
              <h3 className="panel-title">Live Investigation — Vehicle Journey Reconstruction</h3>
              <p className="text-[11px] text-ink-faint">GJ01AB1234 • 359 km • 4 cameras • 5h 37m • Paldi → Rajkot → Junagadh → Gir Somnath • BSA 2023 Compliant</p>
            </div>
          </div>
          <button className="btn-primary gap-1.5 text-xs" onClick={() => navigate('/vehicles/GJ01AB1234')}>
            <Brain size={14} /> Open Investigation
          </button>
        </div>
        <div className="grid gap-3 p-4 sm:grid-cols-4">
          <div className="rounded-xl border border-line bg-gradient-to-br from-blue-50 to-white p-3.5">
            <p className="text-[10px] font-bold uppercase tracking-widest text-blue-700">CAM04 • Paldi Circle</p>
            <p className="mt-1 font-mono text-xs font-bold">17:26 • GJ01AB1234</p>
            <p className="text-[11px] text-ink-faint">Ahmedabad • 94% confidence • YOLO11</p>
            <p className="mt-2 inline-flex chip border-emerald-200 bg-emerald-500/10 text-emerald-700 text-[10px] font-bold">✓ START • Hash: c4a3dc55 • BSA Sec 63</p>
          </div>
          <div className="rounded-xl border border-line bg-gradient-to-br from-violet-50 to-white p-3.5">
            <p className="text-[10px] font-bold uppercase tracking-widest text-violet-700">CAM17 • Rajkot Bus Port</p>
            <p className="mt-1 font-mono text-xs font-bold">20:32 • GJ01AB1234</p>
            <p className="text-[11px] text-ink-faint">Rajkot • 198 km • 63.9 km/h • 93%</p>
            <p className="mt-2 inline-flex chip border-emerald-200 bg-emerald-500/10 text-emerald-700 text-[10px] font-bold">✓ 3h 6m • Section speed OK</p>
          </div>
          <div className="rounded-xl border border-line bg-gradient-to-br from-amber-50 to-white p-3.5">
            <p className="text-[10px] font-bold uppercase tracking-widest text-amber-700">CAM08 • Majewadi Gate</p>
            <p className="mt-1 font-mono text-xs font-bold">21:58 • GJ01AB1234</p>
            <p className="text-[11px] text-ink-faint">Junagadh • 91 km • 63.8 km/h • Optical OK</p>
            <p className="mt-2 inline-flex chip border-emerald-200 bg-emerald-500/10 text-emerald-700 text-[10px] font-bold">✓ 1h 26m • No violation</p>
          </div>
          <div className="rounded-xl border border-line bg-gradient-to-br from-emerald-50 to-white p-3.5">
            <p className="text-[10px] font-bold uppercase tracking-widest text-emerald-700">CAM07 • Gir Somnath</p>
            <p className="mt-1 font-mono text-xs font-bold">23:03 • GJ01AB1234</p>
            <p className="text-[11px] text-ink-faint">Gir • 69 km • 64.3 km/h • Court-admissible</p>
            <p className="mt-2 inline-flex chip border-blue-200 bg-blue-500/10 text-blue-700 text-[10px] font-bold">✓ END • 359 km • BSA Sec 65B</p>
          </div>
        </div>
        <div className="border-t border-line bg-slate-50 px-4 py-2.5">
          <p className="text-[11px] text-ink-muted">
            <span className="font-bold">Technical:</span> Haversine GPS distance calculation, PTS-based timing, SHA256 hash chain per segment, BSA 2023 Section 63 + Section 65B compliance,
            printable court-admissible certificate, predictive next-camera with ETA, threat level auto-calculated. Full investigation at <span className="font-mono font-bold">/vehicles/GJ01AB1234</span> with speed engine + evidence vault.
          </p>
        </div>
      </section>
    </div>
  );
}
