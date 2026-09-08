import { useMemo, useState } from 'react';
import { BellOff } from 'lucide-react';
import { useAlerts } from '@/hooks/useAlerts';
import { useOfficer } from '@/features/officer/OfficerProvider';
import type { AlertStatus, Severity } from '@/types';
import { AlertItem } from '@/components/AlertItem';
import { Boundary, EmptyState, KeyVal } from '@/ui/Feedback';
import { Badge } from '@/ui/Badge';
import { Button } from '@/ui/Button';
import { Card, CardBody, CardHeader } from '@/ui/Card';
import { Tabs } from '@/ui/Tabs';
import { useToast } from '@/features/system/ToastProvider';
import { cn } from '@/lib/utils';

type StatusTab = AlertStatus | 'ALL';

/**
 * Alerts desk — two queues (open work / closed history), filters,
 * bulk acknowledge and a compact officer summary. Triage, not theatre.
 */
export default function Alerts() {
  const { active, history, counts, acknowledge, resolve, refreshAlerts } = useAlerts();
  const { current: officer } = useOfficer();
  const toast = useToast();

  const [tab, setTab] = useState<StatusTab>('ALL');
  const [severity, setSeverity] = useState<Severity | 'ALL'>('ALL');
  const [busyBulk, setBusyBulk] = useState(false);

  const source = tab === 'RESOLVED' ? history : active;
  const filtered = useMemo(
    () =>
      [...source]
        .filter((a) => (severity === 'ALL' ? true : a.severity === severity))
        .sort((a, b) => Date.parse(b.createdAt) - Date.parse(a.createdAt)),
    [source, severity],
  );

  const ackAllVisible = async () => {
    const targets = filtered.filter((a) => a.status === 'NEW');
    if (targets.length === 0) return;
    setBusyBulk(true);
    try {
      await Promise.all(targets.map((a) => acknowledge(a.id)));
      toast.success(`${targets.length} alert${targets.length > 1 ? 's' : ''} acknowledged`, 'They remain in the open list until resolved.');
    } catch {
      toast.error('Could not acknowledge all alerts');
    } finally {
      setBusyBulk(false);
    }
  };

  const tabs: { value: StatusTab; label: string; count?: number }[] = [
    { value: 'ALL', label: 'All open', count: counts.ACTIVE },
    { value: 'NEW', label: 'New', count: counts.NEW },
    { value: 'ACKNOWLEDGED', label: 'Seen', count: counts.ACKNOWLEDGED },
    { value: 'RESOLVED', label: 'Closed', count: counts.RESOLVED },
  ];

  return (
    <div className="p-4 sm:p-6">
      <div className="grid gap-6 xl:grid-cols-[1fr_300px]">
        {/* Queue */}
        <div className="min-w-0">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <Tabs value={tab} onChange={setTab} items={tabs} className="w-full overflow-x-auto sm:w-auto" />
            <div className="flex items-center gap-2.5">
              <label htmlFor="alert-severity" className="sr-only">Filter by severity</label>
              <select
                id="alert-severity"
                className="select h-8 w-36 text-xs"
                value={severity}
                onChange={(e) => setSeverity(e.target.value as Severity | 'ALL')}
              >
                <option value="ALL">All priorities</option>
                <option value="CRITICAL">Critical</option>
                <option value="HIGH">High</option>
                <option value="MEDIUM">Medium</option>
                <option value="LOW">Low</option>
                <option value="INFO">Info</option>
              </select>
              {tab !== 'RESOLVED' && counts.NEW > 0 && (
                <Button variant="secondary" size="sm" onClick={ackAllVisible} loading={busyBulk}>
                  Acknowledge new ({counts.NEW})
                </Button>
              )}
            </div>
          </div>

          <Boundary
            loading={false}
            isEmpty={filtered.length === 0}
            onRetry={refreshAlerts}
            emptyTitle={tab === 'RESOLVED' ? 'No closed alerts yet' : 'Queue is clear'}
            emptyDetail={
              tab === 'RESOLVED'
                ? 'Resolved alerts are kept here for the record.'
                : 'Nothing needs a decision right now. New matches will appear instantly.'
            }
            className="mt-4"
          >
            <div className="mt-4 space-y-3">
              {filtered.map((a) => (
                <AlertItem
                  key={a.id}
                  alert={a}
                  onAcknowledge={acknowledge}
                  onResolve={resolve}
                />
              ))}
            </div>
          </Boundary>
        </div>

        {/* Officer summary rail */}
        <aside className="min-w-0">
          <Card>
            <CardHeader title="On this desk" subtitle="Operator on duty" />
            <CardBody className="p-5">
              {officer ? (
                <dl className="grid grid-cols-2 gap-x-4 gap-y-4">
                  <KeyVal label="Officer">{officer.name}</KeyVal>
                  <KeyVal label="Designation">{officer.designation}</KeyVal>
                  <KeyVal label="Vehicles caught">{officer.vehiclesCaught}</KeyVal>
                  <KeyVal label="Challans issued">{officer.totalChallans}</KeyVal>
                  <KeyVal label="Revenue collected">
                    ₹{officer.totalAmountCollected.toLocaleString('en-IN')}
                  </KeyVal>
                  <KeyVal label="Outstanding">
                    ₹{(officer.totalChallanAmount - officer.totalAmountCollected).toLocaleString('en-IN')}
                  </KeyVal>
                </dl>
              ) : (
                <EmptyState icon={BellOff} title="Officer record unavailable" />
              )}
            </CardBody>
            <CardBody className="border-t border-line px-5 py-3.5">
              <p className="flex items-center gap-2 text-[11px] text-ink-faint">
                <span className={cn('h-1.5 w-1.5 rounded-full', counts.ACTIVE > 0 ? 'live-dot bg-critical' : 'bg-online')} aria-hidden />
                {counts.ACTIVE > 0
                  ? `${counts.ACTIVE} open alert${counts.ACTIVE > 1 ? 's' : ''} on the board`
                  : 'All clear — no open alerts'}
              </p>
            </CardBody>
          </Card>

          <Card className="mt-6">
            <CardHeader title="Queue by priority" />
            <CardBody className="space-y-2.5 p-5">
              {(['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO'] as Severity[]).map((s) => {
                const n = active.filter((a) => a.severity === s).length;
                const total = Math.max(1, active.length);
                return (
                  <div key={s} className="flex items-center gap-3">
                    <Badge
                      tone={s === 'CRITICAL' ? 'danger' : s === 'HIGH' || s === 'MEDIUM' ? 'warn' : 'info'}
                      className="w-20 justify-center"
                    >
                      {s[0] + s.slice(1).toLowerCase()}
                    </Badge>
                    <div className="h-1.5 min-w-0 flex-1 overflow-hidden rounded-full bg-surface-3" aria-hidden>
                      <div
                        className={cn(
                          'h-full rounded-full transition-[width] duration-500',
                          s === 'CRITICAL' ? 'bg-critical' : s === 'HIGH' || s === 'MEDIUM' ? 'bg-warn' : 'bg-info',
                        )}
                        style={{ width: `${(n / total) * 100}%` }}
                      />
                    </div>
                    <span className="mono w-6 text-right text-xs tabular-nums text-ink-muted">{n}</span>
                  </div>
                );
              })}
            </CardBody>
          </Card>
        </aside>
      </div>
    </div>
  );
}
