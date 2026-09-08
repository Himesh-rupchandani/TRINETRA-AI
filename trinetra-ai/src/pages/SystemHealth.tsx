import { useMemo, useState } from 'react';
import { AlertTriangle, CheckCircle2, RefreshCw, XCircle } from 'lucide-react';
import { useSystemStatus } from '@/features/system/useSystemStatus';
import type { ProcessingState, ServiceHealth, ServiceStatus } from '@/types';
import { Badge } from '@/ui/Badge';
import { Button } from '@/ui/Button';
import { Card, CardBody, CardHeader } from '@/ui/Card';
import { Boundary, KeyVal } from '@/ui/Feedback';
import { Stat } from '@/ui/Links';
import { cn } from '@/lib/utils';
import { formatDateTime } from '@/lib/uiHelpers';
import { relativeTime } from '@/lib/utils';

const SERVICE_TONE: Record<ServiceStatus, { badge: 'success' | 'warn' | 'danger'; dot: string; icon: typeof CheckCircle2 }> = {
  HEALTHY: { badge: 'success', dot: 'bg-online', icon: CheckCircle2 },
  DEGRADED: { badge: 'warn', dot: 'bg-warn', icon: AlertTriangle },
  OFFLINE: { badge: 'danger', dot: 'bg-offline', icon: XCircle },
};

const PROC_LABEL: Record<ProcessingState, string> = {
  IDLE: 'Idle',
  PROCESSING: 'Processing',
  BACKLOGGED: 'Backlogged',
  STOPPED: 'Stopped',
};

function ServiceRow({ s }: { s: ServiceHealth }) {
  const tone = SERVICE_TONE[s.status];
  const Icon = tone.icon;
  const [open, setOpen] = useState<boolean>(false);
  return (
    <>
      <tr
        className="row-click"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        title="Click for service details"
      >
        <td>
          <span className="flex items-center gap-2.5">
            <Icon size={14} className={cn(s.status === 'HEALTHY' ? 'text-online' : s.status === 'DEGRADED' ? 'text-warn' : 'text-offline')} aria-hidden />
            <span>
              <span className="block text-[13px] font-medium text-ink">{s.name}</span>
              <span className="block max-w-[340px] truncate text-[11px] text-ink-faint">{s.description}</span>
            </span>
          </span>
        </td>
        <td><Badge tone={tone.badge}>{s.status[0] + s.status.slice(1).toLowerCase()}</Badge></td>
        <td className="text-ink-muted">{PROC_LABEL[s.processingState]}</td>
        <td className="mono tabular-nums text-ink-muted">{s.uptimePct.toFixed(2)}%</td>
        <td className="mono tabular-nums text-ink-muted">
          {s.latencyMs != null ? `${s.latencyMs.toFixed(0)} ms` : '—'}
        </td>
        <td className="mono tabular-nums text-ink-muted">{s.queueDepth ?? 0}</td>
        <td className="text-ink-muted" title={formatDateTime(s.lastHeartbeat)}>
          {relativeTime(s.lastHeartbeat)}
        </td>
      </tr>
      {open && (
        <tr>
          <td colSpan={7} className="bg-surface-2/50">
            <dl className="grid grid-cols-2 gap-x-6 gap-y-3 px-2 py-3 sm:grid-cols-4">
              <KeyVal label="Service ID"><span className="mono">{s.id}</span></KeyVal>
              <KeyVal label="Version">{s.version ?? '—'}</KeyVal>
              <KeyVal label="Uptime since">{formatDateTime(s.uptimeSince)}</KeyVal>
              <KeyVal label="Active connections">{s.activeConnections}</KeyVal>
              {s.latestError && (
                <div className="col-span-2 sm:col-span-4">
                  <KeyVal label="Latest error">
                    <span className="mono block whitespace-pre-wrap rounded-md border border-critical/25 bg-critical/[0.05] px-2.5 py-1.5 text-xs text-critical">
                      {s.latestError}
                    </span>
                  </KeyVal>
                </div>
              )}
            </dl>
          </td>
        </tr>
      )}
    </>
  );
}

/**
 * System Status — platform services in one expandable table plus an
 * ingest-rate band. Click a row for the full service record.
 */
export default function SystemHealth() {
  const { health, kpis, loading, error, refresh } = useSystemStatus(15000);

  const counts = useMemo(() => {
    const services = health?.services ?? [];
    return {
      healthy: services.filter((s) => s.status === 'HEALTHY').length,
      degraded: services.filter((s) => s.status === 'DEGRADED').length,
      offline: services.filter((s) => s.status === 'OFFLINE').length,
      total: services.length,
    };
  }, [health]);

  return (
    <div className="p-4 sm:p-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold text-ink">System Status</h2>
          <p className="mt-1 max-w-2xl text-[13px] leading-relaxed text-ink-muted">
            Live state of the ingest, recognition and dispatch services behind SENTINEL. This page
            refreshes itself every 15 seconds.
          </p>
        </div>
        <Button variant="secondary" onClick={refresh}>
          <RefreshCw size={13} aria-hidden className={loading ? 'animate-spin' : ''} /> Refresh now
        </Button>
      </header>

      {/* Ingest band */}
      <div className="mt-5 grid grid-cols-2 divide-line rounded-lg border border-line bg-surface-1 sm:grid-cols-3 sm:divide-x lg:grid-cols-6">
        <Stat label="Cameras online" value={kpis ? kpis.camerasOnline : '—'} sub={kpis ? `${kpis.camerasDegraded} degraded · ${kpis.camerasOffline} offline` : undefined} />
        <Stat label="Ingest rate" value={health ? `${health.ingestFps.toFixed(1)}` : '—'} sub="frames per second" />
        <Stat label="Events" value={health ? health.eventsPerMinute.toFixed(0) : '—'} sub="per minute" />
        <Stat label="Plate reads" value={health ? health.anprPerMinute.toFixed(0) : '—'} sub="per minute" />
        <Stat
          label="Services healthy"
          value={loading && !health ? '—' : `${counts.healthy}/${counts.total}`}
          sub={counts.degraded > 0 ? `${counts.degraded} degraded` : counts.offline > 0 ? `${counts.offline} offline` : 'all nominal'}
          tone={counts.offline > 0 ? 'danger' : 'default'}
        />
        <Stat label="Snapshot" value={health ? formatDateTime(health.generatedAt).split(', ')[1] ?? '—' : '—'} sub={health ? formatDateTime(health.generatedAt).split(', ')[0] : undefined} />
      </div>

      <Card className="mt-6">
        <CardHeader
          title="Services"
          subtitle="Click a row for the full service record"
          actions={
            health && (
              <Badge tone={counts.offline > 0 ? 'danger' : counts.degraded > 0 ? 'warn' : 'success'} dot pulse>
                {counts.offline > 0 ? 'Attention needed' : counts.degraded > 0 ? 'Partial degradation' : 'All systems nominal'}
              </Badge>
            )
          }
        />
        <CardBody>
          <Boundary
            loading={loading && !health}
            error={error}
            onRetry={refresh}
            isEmpty={(health?.services.length ?? 0) === 0}
            emptyTitle="No service data"
            emptyDetail="The platform has not reported any services yet."
            loadingLabel="Reading service health"
          >
            <div className="overflow-x-auto">
              <table className="tbl">
                <thead>
                  <tr>
                    <th>Service</th>
                    <th>State</th>
                    <th>Processing</th>
                    <th>Uptime</th>
                    <th>Latency</th>
                    <th>Queue</th>
                    <th>Heartbeat</th>
                  </tr>
                </thead>
                <tbody>
                  {(health?.services ?? []).map((s) => (
                    <ServiceRow key={s.id} s={s} />
                  ))}
                </tbody>
              </table>
            </div>
          </Boundary>
        </CardBody>
      </Card>
    </div>
  );
}
