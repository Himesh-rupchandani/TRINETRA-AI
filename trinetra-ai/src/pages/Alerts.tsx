import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { Bell, Search, X } from 'lucide-react';
import { PageHeader } from '@/components/layout/PageHeader';
import { AlertCard } from '@/components/alerts/AlertCard';
import { EvidencePanel } from '@/components/vehicle/EvidencePanel';
import { Modal } from '@/components/common/Modal';
import { EmptyState } from '@/components/common/Panel';
import { useAlerts } from '@/hooks/useAlerts';
import { useAsync } from '@/hooks/useAsync';
import { eventService } from '@/services/eventService';
import type { Alert, Severity } from '@/types';
import { cn } from '@/lib/utils';

const SEVERITIES: (Severity | 'ALL')[] = ['ALL', 'CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO'];

export default function Alerts() {
  const [tab, setTab] = useState<'ACTIVE' | 'HISTORY'>('ACTIVE');
  const [severity, setSeverity] = useState<Severity | 'ALL'>('ALL');
  const [query, setQuery] = useState('');
  const [evidenceFor, setEvidenceFor] = useState<Alert | null>(null);

  const { active, history, counts, acknowledge, resolve } = useAlerts({ severity, query });
  const list = tab === 'ACTIVE' ? active : history;

  const evidenceEvent = useAsync(
    () => eventService.byId(evidenceFor!.eventId),
    [evidenceFor?.eventId],
    { enabled: Boolean(evidenceFor) },
  );

  const grouped = useMemo(
    () => ({
      NEW: list.filter((a) => a.status === 'NEW'),
      ACKNOWLEDGED: list.filter((a) => a.status === 'ACKNOWLEDGED'),
      RESOLVED: list.filter((a) => a.status === 'RESOLVED'),
    }),
    [list],
  );

  return (
    <div className="flex h-full flex-col">
      <PageHeader
        title="Alerts"
        icon={Bell}
        tone="red"
        subtitle={
          <>
            <span className="text-critical">{counts.NEW} need attention</span> ·{' '}
            <span className="text-processing">{counts.ACKNOWLEDGED} already seen</span> ·{' '}
            <span className="text-online">{counts.RESOLVED} closed</span>
          </>
        }
        actions={
          <div className="flex items-center gap-1.5" role="tablist" aria-label="Alert view">
            {(['ACTIVE', 'HISTORY'] as const).map((t) => (
              <button
                key={t}
                type="button"
                role="tab"
                aria-selected={tab === t}
                onClick={() => setTab(t)}
                className={cn(
                  'h-8 rounded-lg border px-3 text-xs font-semibold transition-colors',
                  tab === t
                    ? 'border-brand/25 bg-brand/10 text-brand'
                    : 'border-transparent text-ink-muted hover:bg-surface-2 hover:text-ink',
                )}
              >
                {t === 'ACTIVE' ? `Needs attention (${active.length})` : `Closed alerts (${history.length})`}
              </button>
            ))}
          </div>
        }
      />

      <div className="flex flex-wrap items-end gap-3 border-b border-line bg-surface-1 px-4 py-3 sm:px-5">
        <div className="min-w-[200px] flex-1">
          <label className="label" htmlFor="alert-search">
            Search alerts
          </label>
          <div className="relative">
            <Search size={13} className="pointer-events-none absolute left-2 top-1/2 -translate-y-1/2 text-ink-faint" aria-hidden />
            <input
              id="alert-search"
              className="input pl-7"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search by number plate, camera or place"
            />
          </div>
        </div>
        <div className="w-[120px]">
          <label className="label" htmlFor="alert-sev">
            Priority
          </label>
          <select
            id="alert-sev"
            className="select"
            value={severity}
            onChange={(e) => setSeverity(e.target.value as Severity | 'ALL')}
          >
            {SEVERITIES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </div>
        {(query || severity !== 'ALL') && (
          <button
            type="button"
            className="btn-ghost"
            onClick={() => {
              setQuery('');
              setSeverity('ALL');
            }}
          >
            <X size={12} aria-hidden /> Clear
          </button>
        )}
      </div>

      <div className="min-h-0 flex-1 overflow-auto p-4 sm:p-5" role="tabpanel">
        {list.length === 0 ? (
          <div className="panel">
            <EmptyState
              title={tab === 'ACTIVE' ? 'Nothing needs your attention' : 'No closed alerts yet'}
              detail={
                tab === 'ACTIVE'
                  ? 'Every wanted vehicle found so far has been dealt with. New ones show up here straight away.'
                  : 'Alerts you close are kept here as a record.'
              }
              action={
                <Link to="/watchlist" className="btn-tint btn-xs mt-1">
                  Review the wanted list
                </Link>
              }
            />
          </div>
        ) : tab === 'ACTIVE' ? (
          <div className="space-y-4">
            {(['NEW', 'ACKNOWLEDGED'] as const).map((status) =>
              grouped[status].length ? (
                <section key={status}>
                  <h2 className="mb-3 text-xs font-semibold text-ink-muted">
                    {status === 'NEW' ? 'Needs your attention' : 'Already seen'} ({grouped[status].length})
                  </h2>
                  <div className="grid gap-3 xl:grid-cols-2 xl:gap-4">
                    {grouped[status].map((a) => (
                      <AlertCard
                        key={a.id}
                        alert={a}
                        onAcknowledge={acknowledge}
                        onResolve={resolve}
                        onViewEvidence={setEvidenceFor}
                      />
                    ))}
                  </div>
                </section>
              ) : null,
            )}
          </div>
        ) : (
          <div className="grid gap-3 xl:grid-cols-2 xl:gap-4">
            {list.map((a) => (
              <AlertCard
                key={a.id}
                alert={a}
                onAcknowledge={acknowledge}
                onResolve={resolve}
                onViewEvidence={setEvidenceFor}
              />
            ))}
          </div>
        )}
      </div>

      <Modal
        open={Boolean(evidenceFor)}
        onClose={() => setEvidenceFor(null)}
        title={evidenceFor ? `Evidence — ${evidenceFor.plate}` : ''}
        subtitle={
          evidenceFor
            ? `${evidenceFor.category} · ${evidenceFor.cameraName ?? evidenceFor.cameraId} · ${evidenceFor.location}`
            : undefined
        }
      >
        <EvidencePanel event={evidenceEvent.data} />
      </Modal>
    </div>
  );
}
