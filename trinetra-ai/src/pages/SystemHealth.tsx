import { Activity, AlertTriangle, Cpu, Gauge, Plug, RefreshCcw } from 'lucide-react';
import { PageHeader } from '@/components/layout/PageHeader';
import { Panel, AsyncBoundary, KeyValue } from '@/components/common/Panel';
import { ServiceStatusChip } from '@/components/common/Chips';
import { KpiCard } from '@/components/dashboard/KpiCard';
import { useAsync } from '@/hooks/useAsync';
import { systemService } from '@/services/systemService';
import { useLiveEvents } from '@/hooks/useLiveEvents';
import { cn, formatDateTime, formatNumber, formatTime, relativeTime } from '@/lib/utils';
import { config } from '@/lib/config';

const PROCESSING_TONE: Record<string, string> = {
  PROCESSING: 'text-processing',
  IDLE: 'text-ink-muted',
  BACKLOGGED: 'text-degraded',
  STOPPED: 'text-offline',
};

export default function SystemHealth() {
  const health = useAsync(() => systemService.health(), []);
  const { connection, eventsSeen } = useLiveEvents();
  const services = health.data?.services ?? [];
  const degraded = services.filter((s) => s.status !== 'HEALTHY');

  return (
    <div className="flex h-full flex-col">
      <PageHeader
        title="System Status"
        icon={Activity}
        tone="green"
        subtitle={
          health.data
            ? `Checked at ${formatTime(health.data.generatedAt)}. ${degraded.length === 0 ? 'Everything is working normally.' : `${degraded.length} part${degraded.length > 1 ? 's' : ''} of the system need${degraded.length > 1 ? '' : 's'} attention.`}`
            : 'Checking each part of the system…'
        }
        actions={
          <button type="button" className="btn-ghost" onClick={health.refresh}>
            <RefreshCcw size={12} aria-hidden /> Refresh
          </button>
        }
      />

      <div className="min-h-0 flex-1 overflow-auto p-4 sm:p-5">
        <AsyncBoundary loading={health.loading} error={health.error} onRetry={health.refresh} loadingLabel="Checking the system">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 sm:gap-4 xl:grid-cols-5">
            <KpiCard
              label="Parts working normally"
              value={`${services.length - degraded.length}/${services.length}`}
              tone={degraded.length ? 'warn' : 'online'}
              tile={degraded.length ? 'amber' : 'blue'}
              icon={Cpu}
            />
            <KpiCard
              label="Video being processed"
              value={formatNumber(health.data?.ingestFps)}
              sub="camera frames every second"
              tile="green"
              icon={Gauge}
            />
            <KpiCard
              label="Vehicles seen each minute"
              value={formatNumber(health.data?.eventsPerMinute)}
              sub="Found by the AI"
              tone="brand"
              tile="sky"
              icon={Activity}
            />
            <KpiCard
              label="Plates read each minute"
              value={formatNumber(health.data?.anprPerMinute)}
              sub="Read automatically"
              tile="blue"
              icon={Activity}
            />
            <KpiCard
              label="Live updates"
              value={connection === 'SIMULATED' ? 'Demo' : connection === 'LIVE' ? 'On' : connection === 'CONNECTING' ? 'Connecting' : 'Off'}
              sub={`${eventsSeen} update${eventsSeen === 1 ? '' : 's'} received`}
              tone={connection === 'OFFLINE' ? 'critical' : 'brand'}
              tile="purple"
              icon={Plug}
            />
          </div>

          {degraded.length > 0 && (
            <div className="panel mt-4 border-l-4 border-l-degraded p-3.5 sm:p-4" role="status">
              <p className="flex items-center gap-1.5 text-2xs font-bold uppercase tracking-widest text-degraded">
                <AlertTriangle size={12} aria-hidden /> {degraded.length} part
                {degraded.length > 1 ? 's' : ''} of the system need{degraded.length > 1 ? '' : 's'} attention
              </p>
              <ul className="mt-2 space-y-1">
                {degraded.map((s) => (
                  <li key={s.id} className="text-2xs text-ink-muted">
                    <span className="font-semibold text-ink">{s.name}</span> — {s.latestError ?? 'not working normally'}
                  </li>
                ))}
              </ul>
            </div>
          )}

          <div className="mt-4 grid gap-3 sm:gap-4 lg:grid-cols-2">
            {services.map((s) => (
              <Panel key={s.id} title={s.name} icon={Cpu} actions={<ServiceStatusChip status={s.status} />}>
                <div className="p-4">
                  <p className="text-2xs text-ink-faint">{s.description}</p>
                  <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2.5 sm:grid-cols-3">
                    <KeyValue label="Working time">
                      <span className="font-mono">
                        {s.uptimePct != null ? `${s.uptimePct.toFixed(2)}%` : '—'}
                      </span>
                    </KeyValue>
                    <KeyValue label="Running since">
                      {s.uptimeSince ? relativeTime(s.uptimeSince) : '—'}
                    </KeyValue>
                    <KeyValue label="Last checked">
                      <span className="font-mono">{formatTime(s.lastHeartbeat)}</span>
                    </KeyValue>
                    <KeyValue label="Cameras connected">
                      <span className="font-mono tabular-nums">{s.activeConnections ?? '—'}</span>
                    </KeyValue>
                    <KeyValue label="Currently">
                      <span className={cn('font-semibold', s.processingState ? PROCESSING_TONE[s.processingState] : '')}>
                        {s.processingState === 'PROCESSING'
                          ? 'Working'
                          : s.processingState === 'IDLE'
                            ? 'Waiting'
                            : 'Stopped'}
                      </span>
                    </KeyValue>
                    <KeyValue label="Response time">
                      <span className="font-mono">{s.latencyMs ?? '—'} ms</span>
                    </KeyValue>
                    {s.queueDepth != null && (
                      <KeyValue label="Waiting in queue">
                        <span className="font-mono tabular-nums">{s.queueDepth}</span>
                      </KeyValue>
                    )}
                    <KeyValue label="Version">
                      <span className="font-mono">{s.version ?? '—'}</span>
                    </KeyValue>
                  </dl>
                  <div className="mt-3 border-t border-line/60 pt-2.5">
                    <p className="kv-label">Last problem</p>
                    <p className={cn('mt-1 text-2xs', s.latestError ? 'text-degraded' : 'text-ink-faint')}>
                      {s.latestError ?? 'No problems reported.'}
                    </p>
                  </div>
                </div>
              </Panel>
            ))}
          </div>

          <Panel title="Technical settings" icon={Plug} className="mt-4">
            <dl className="grid grid-cols-2 gap-x-4 gap-y-2.5 p-4 sm:grid-cols-4">
              <KeyValue label="Where the data comes from">
                {config.useMocks ? 'Demo mode (made-up sample data)' : 'Live police backend'}
              </KeyValue>
              <KeyValue label="Backend address">
                <span className="font-mono">{config.apiBaseUrl}</span>
              </KeyValue>
              <KeyValue label="Live updates method">
                <span className="font-mono">{config.useMocks ? 'simulator' : config.realtimeTransport}</span>
              </KeyValue>
              <KeyValue label="Information as of">{formatDateTime(health.data?.generatedAt)}</KeyValue>
            </dl>
            <p className="border-t border-line px-4 py-2.5 text-2xs text-ink-faint">
              No credentials, passwords or private keys are held by this frontend. Stream URLs and evidence
              links are issued as short-lived signed tickets by the backend.
            </p>
          </Panel>
        </AsyncBoundary>
      </div>
    </div>
  );
}
