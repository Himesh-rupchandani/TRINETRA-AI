import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Camera, CheckCircle2, FileImage, Map, Siren } from 'lucide-react';
import type { Alert } from '@/types';
import { AlertStatusChip, SeverityChip } from '@/components/common/Chips';
import { IconTile, type TileTone } from '@/components/common/IconTile';
import { PlateLink } from '@/components/common/Links';
import { ConfirmDialog } from '@/components/common/Modal';
import { useToast } from '@/features/system/ToastProvider';
import { cn, formatTime, relativeTime, severityBar } from '@/lib/utils';

const SEVERITY_TONE: Record<Alert['severity'], TileTone> = {
  CRITICAL: 'red',
  HIGH: 'orange',
  MEDIUM: 'amber',
  LOW: 'sky',
  INFO: 'slate',
};

export function AlertCard({
  alert,
  onAcknowledge,
  onResolve,
  onViewEvidence,
  compact = false,
  highlighted = false,
}: {
  alert: Alert;
  onAcknowledge: (id: string) => Promise<void>;
  onResolve?: (id: string) => Promise<void>;
  onViewEvidence?: (alert: Alert) => void;
  compact?: boolean;
  highlighted?: boolean;
}) {
  const navigate = useNavigate();
  const toast = useToast();
  const [confirmResolve, setConfirmResolve] = useState(false);
  const [busy, setBusy] = useState(false);

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
      id={`alert-${alert.id}`}
      className={cn(
        'panel relative scroll-mt-52 overflow-hidden transition-shadow hover:shadow-cardHover',
        highlighted && 'ring-2 ring-brand',
        alert.status === 'NEW' && alert.severity === 'CRITICAL'
          ? 'alert-enter-pulse'
          : 'enter-up',
      )}
      aria-label={`${alert.severity} alert for ${alert.plate}`}
    >
      <span className={cn('absolute inset-y-0 left-0 w-1', severityBar[alert.severity])} aria-hidden />

      <div className="flex flex-wrap items-start justify-between gap-3 py-3 pl-4 pr-4">
        <div className="flex min-w-0 items-center gap-2.5">
          <IconTile tone={SEVERITY_TONE[alert.severity]} size="md">
            <Siren size={15} className={alert.status === 'NEW' ? '' : 'opacity-60'} aria-hidden />
          </IconTile>
          <div className="min-w-0">
            <p className="text-xs font-bold uppercase tracking-wide text-ink">{alert.category}</p>
            <p className="mt-0.5 text-2xs text-ink-faint">
              {formatTime(alert.createdAt)} · {relativeTime(alert.createdAt)}
            </p>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          <SeverityChip severity={alert.severity} />
          <AlertStatusChip status={alert.status} />
        </div>
      </div>

      <dl className="grid grid-cols-2 gap-x-4 gap-y-2 px-4 pb-3 sm:grid-cols-4">
        <div>
          <dt className="kv-label">Vehicle</dt>
          <dd>
            <PlateLink plate={alert.plate} size="sm" />
          </dd>
        </div>
        <div>
          <dt className="kv-label">Camera</dt>
          <dd className="kv-value font-mono">{alert.cameraName ?? alert.cameraId.toUpperCase()}</dd>
        </div>
        <div className="col-span-2 sm:col-span-1">
          <dt className="kv-label">Place</dt>
          <dd className="kv-value truncate">{alert.location}</dd>
        </div>
        <div>
          <dt className="kv-label">Plate match</dt>
          <dd className="kv-value font-mono tabular-nums">
            {alert.confidence != null ? `${alert.confidence.toFixed(1)}%` : '—'}
          </dd>
        </div>
      </dl>

      {!compact && (alert.acknowledgedBy || alert.note) && (
        <p className="border-t border-line/60 py-2 pl-4 pr-4 text-2xs text-ink-faint">
          {alert.acknowledgedBy && <>Seen by {alert.acknowledgedBy}. </>}
          {alert.note}
        </p>
      )}

      <div className="flex flex-wrap items-center gap-2 border-t border-line px-4 py-3">
        <button type="button" className="btn-tint btn-xs" onClick={() => navigate(`/vehicles/${alert.plate}`)}>
          Look up this vehicle
        </button>
        <button type="button" className="btn-ghost btn-xs" onClick={() => navigate(`/cameras/${alert.cameraId}`)}>
          <Camera size={12} aria-hidden /> Open camera
        </button>
        <button
          type="button"
          className="btn-ghost btn-xs"
          onClick={() => navigate(`/gis?plate=${alert.plate}&focus=${alert.cameraId}`)}
        >
          <Map size={12} aria-hidden /> Show on map
        </button>
        {onViewEvidence && (
          <button type="button" className="btn-ghost btn-xs" onClick={() => onViewEvidence(alert)}>
            <FileImage size={12} aria-hidden /> See photo
          </button>
        )}
        <div className="ml-auto flex gap-2">
          {alert.status === 'NEW' && (
            <button type="button" className="btn-danger btn-xs" onClick={ack} disabled={busy}>
              <CheckCircle2 size={12} aria-hidden /> Mark as seen
            </button>
          )}
          {alert.status === 'ACKNOWLEDGED' && onResolve && (
            <button type="button" className="btn-ghost btn-xs" onClick={() => setConfirmResolve(true)} disabled={busy}>
              Close alert
            </button>
          )}
        </div>
      </div>

      <ConfirmDialog
        open={confirmResolve}
        title="Close this alert?"
        message={`This closes the ${alert.category.toLowerCase()} alert for ${alert.plate} at ${alert.cameraName ?? alert.cameraId}. It stays in the alert history, but stops asking for your attention.`}
        confirmLabel="Yes, close it"
        onConfirm={resolve}
        onCancel={() => setConfirmResolve(false)}
      />
    </article>
  );
}
