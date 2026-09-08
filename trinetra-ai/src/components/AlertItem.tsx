import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Camera, CheckCircle2, Map, Siren } from 'lucide-react';
import type { Alert } from '@/types';
import { AlertStateBadge, SeverityBadge } from '@/ui/Badge';
import { Button } from '@/ui/Button';
import { Modal } from '@/ui/Modal';
import { PlateLink } from '@/ui/Links';
import { useToast } from '@/features/system/ToastProvider';
import { cn, formatDateTime, formatTime, relativeTime } from '@/lib/utils';
import { severityTone } from '@/lib/uiHelpers';

/**
 * One alert as a clean row: severity rule, plate, context, lifecycle action.
 * Used in the dashboard attention list and the alerts page.
 */
export function AlertItem({
  alert,
  onAcknowledge,
  onResolve,
  compact = false,
}: {
  alert: Alert;
  onAcknowledge: (id: string) => Promise<void>;
  onResolve?: (id: string) => Promise<void>;
  compact?: boolean;
}) {
  const navigate = useNavigate();
  const toast = useToast();
  const [confirmResolve, setConfirmResolve] = useState(false);
  const [busy, setBusy] = useState(false);
  const tone = severityTone[alert.severity];

  const ack = async () => {
    setBusy(true);
    try {
      await onAcknowledge(alert.id);
      toast.success('Alert acknowledged', `${alert.plate} · ${alert.cameraName ?? alert.cameraId}`);
    } catch {
      toast.error('Could not acknowledge alert');
    } finally {
      setBusy(false);
    }
  };

  const resolve = async () => {
    setConfirmResolve(false);
    setBusy(true);
    try {
      await onResolve?.(alert.id);
      toast.success('Alert resolved', `${alert.plate} closed by operator`);
    } catch {
      toast.error('Could not resolve alert');
    } finally {
      setBusy(false);
    }
  };

  return (
    <article
      className={cn(
        'relative rounded-xl border border-line bg-surface-1 shadow-xs transition-all duration-200',
        'hover:-translate-y-0.5 hover:shadow-md active:translate-y-0 active:scale-[0.995]',
        alert.status === 'NEW' && alert.severity === 'CRITICAL' && 'border-critical/30',
      )}
      aria-label={`${alert.severity} alert for ${alert.plate}`}
    >
      <span className={cn('absolute inset-y-3 left-0 w-[3px] rounded-r', tone.bar)} aria-hidden />

      <div className="flex flex-wrap items-start justify-between gap-3 py-3.5 pl-5 pr-4">
        <div className="flex min-w-0 items-start gap-3">
          <Siren
            size={15}
            className={cn('mt-0.5 shrink-0', alert.status === 'NEW' ? tone.text : 'text-ink-faint')}
            aria-hidden
          />
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1">
              <span className="text-[13px] font-semibold uppercase tracking-wide text-ink">
                {alert.category}
              </span>
              <SeverityBadge severity={alert.severity} />
              <AlertStateBadge status={alert.status} />
            </div>
            <p className="mt-1 text-xs text-ink-faint">
              {formatTime(alert.createdAt)} · {relativeTime(alert.createdAt)}
              {alert.acknowledgedBy && ` · seen by ${alert.acknowledgedBy}`}
            </p>
          </div>
        </div>
        <PlateLink plate={alert.plate} size="md" className="shrink-0" />
      </div>

      <dl className="grid grid-cols-2 gap-x-5 gap-y-2.5 px-5 pb-3.5 sm:grid-cols-3">
        <div>
          <dt className="text-[11px] font-medium text-ink-faint">Camera</dt>
          <dd className="mono mt-0.5 text-[13px] text-ink">{alert.cameraName ?? alert.cameraId.toUpperCase()}</dd>
        </div>
        <div>
          <dt className="text-[11px] font-medium text-ink-faint">Place</dt>
          <dd className="mt-0.5 truncate text-[13px] text-ink">{alert.location}</dd>
        </div>
        <div>
          <dt className="text-[11px] font-medium text-ink-faint">Plate match</dt>
          <dd className="mono mt-0.5 text-[13px] tabular-nums text-ink">
            {alert.confidence != null ? `${(alert.confidence * 100).toFixed(1)}%` : '—'}
          </dd>
        </div>
      </dl>

      {!compact && alert.note && (
        <p className="border-t border-line/70 px-5 py-2.5 text-xs text-ink-muted">{alert.note}</p>
      )}

      <div className="flex flex-wrap items-center gap-2 border-t border-line px-4 py-2.5">
        <Button variant="secondary" size="xs" onClick={() => navigate(`/vehicles/${alert.plate}`)}>
          Investigate
        </Button>
        <Button variant="ghost" size="xs" onClick={() => navigate(`/cameras/${alert.cameraId}`)}>
          <Camera size={11} aria-hidden /> Camera
        </Button>
        <Button variant="ghost" size="xs" onClick={() => navigate(`/gis?plate=${alert.plate}&focus=${alert.cameraId}`)}>
          <Map size={11} aria-hidden /> Map
        </Button>
        <span className="ml-auto flex items-center gap-2">
          {alert.status === 'NEW' && (
            <Button variant="primary" size="xs" onClick={ack} disabled={busy}>
              <CheckCircle2 size={11} aria-hidden /> Mark seen
            </Button>
          )}
          {alert.status === 'ACKNOWLEDGED' && onResolve && (
            <Button variant="ghost" size="xs" onClick={() => setConfirmResolve(true)} disabled={busy}>
              Close alert
            </Button>
          )}
        </span>
      </div>

      <Modal
        open={confirmResolve}
        onClose={() => setConfirmResolve(false)}
        title="Close this alert?"
        size="sm"
        footer={
          <>
            <Button variant="ghost" onClick={() => setConfirmResolve(false)}>
              Cancel
            </Button>
            <Button variant="primary" onClick={resolve} disabled={busy}>
              Yes, close it
            </Button>
          </>
        }
      >
        <p className="text-[13px] leading-relaxed text-ink-muted">
          This closes the {alert.category.toLowerCase()} alert for{' '}
          <span className="plate">{alert.plate}</span> at {alert.cameraName ?? alert.cameraId} —{' '}
          {formatDateTime(alert.createdAt)}. It stays in the alert history but stops asking for
          your attention.
        </p>
      </Modal>
    </article>
  );
}
