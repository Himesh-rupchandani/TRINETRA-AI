import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { CheckCircle2, Crosshair, FileImage, Map, Siren } from 'lucide-react';
import type { Alert } from '@/types';
import { AlertStatusChip, SeverityChip } from '@/components/common/Chips';
import { PlateLink } from '@/components/common/Links';
import { ConfirmDialog } from '@/components/common/Modal';
import { useToast } from '@/features/system/ToastProvider';
import { cn, formatTime, relativeTime, severityBar } from '@/lib/utils';

/**
 * Alert triage row. Severity language, top to bottom:
 * 3px severity rail · severity chip · mono plate · mono confidence ·
 * one-line reason · exactly one primary action (Trace). Critical + new
 * alerts pulse so they are impossible to miss from across the room.
 */
export function AlertCard({
  alert,
  onAcknowledge,
  onResolve,
  onViewEvidence,
  compact = false,
}: {
  alert: Alert;
  onAcknowledge: (id: string) => Promise<void>;
  onResolve?: (id: string) => Promise<void>;
  onViewEvidence?: (alert: Alert) => void;
  compact?: boolean;
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

  const critical = alert.status === 'NEW' && alert.severity === 'CRITICAL';

  return (
    <article
      className={cn(
        'panel card-hover relative overflow-hidden',
        critical && 'animate-pulse-ring',
        compact ? 'rounded-lg' : 'rounded-xl',
      )}
      aria-label={`${alert.severity} alert for ${alert.plate}`}
    >
      {/* 3px severity rail */}
      <span className={cn('absolute inset-y-0 left-0 w-[3px]', severityBar[alert.severity])} aria-hidden />

      <div className={cn('flex flex-wrap items-start gap-x-3 gap-y-2 py-2.5 pl-4 pr-3.5', compact && 'py-2')}>
        <div className="flex min-w-0 flex-1 items-start gap-2.5">
          <Siren
            size={15}
            className={cn(
              'mt-0.5 shrink-0',
              critical ? 'animate-pulse text-critical' : 'text-ink-faint',
            )}
            aria-hidden
          />
          <div className="min-w-0 flex-1">
            {/* Line 1: category + chips */}
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
              <p className="text-xs font-bold uppercase tracking-wide text-ink">{alert.category}</p>
              <SeverityChip severity={alert.severity} />
              {!compact && <AlertStatusChip status={alert.status} />}
            </div>

            {/* Line 2: mono plate + one-line reason */}
            <div className="mt-0.5 flex min-w-0 flex-wrap items-baseline gap-x-2.5 gap-y-0.5">
              <PlateLink plate={alert.plate} size="sm" className="shrink-0" />
              <p className="min-w-0 flex-1 truncate text-2xs text-ink-muted">
                {alert.note?.trim() || `Watchlist match — ${alert.category.toLowerCase()}`}
              </p>
            </div>

            {/* Line 3: where, when, how sure — all mono where numeric */}
            <p className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-2xs text-ink-faint">
              <span className="font-mono">{alert.cameraName ?? alert.cameraId.toUpperCase()}</span>
              <span aria-hidden>·</span>
              <span className="max-w-[220px] truncate">{alert.location}</span>
              <span aria-hidden>·</span>
              <time className="font-mono tabular-nums" dateTime={alert.createdAt}>
                {formatTime(alert.createdAt)}
              </time>
              <span className="text-ink-faint/70">({relativeTime(alert.createdAt)})</span>
              {alert.confidence != null && (
                <>
                  <span aria-hidden>·</span>
                  <span className="font-mono font-semibold tabular-nums text-ink-muted">
                    {alert.confidence.toFixed(1)}% match
                  </span>
                </>
              )}
            </p>
          </div>
        </div>

        {/* Actions — one primary, the rest quiet */}
        <div className="flex shrink-0 flex-wrap items-center gap-1.5">
          <button type="button" className="btn-tint btn-xs" onClick={() => navigate(`/vehicles/${alert.plate}`)}>
            <Crosshair size={12} aria-hidden /> Trace
          </button>
          {onViewEvidence && (
            <button
              type="button"
              className="btn-ghost btn-xs"
              onClick={() => onViewEvidence(alert)}
              aria-label={`View evidence for ${alert.plate}`}
            >
              <FileImage size={12} aria-hidden />
            </button>
          )}
          <button
            type="button"
            className="btn-ghost btn-xs"
            onClick={() => navigate(`/gis?plate=${alert.plate}&focus=${alert.cameraId}`)}
            aria-label={`Show ${alert.plate} on the map`}
          >
            <Map size={12} aria-hidden />
          </button>
          {alert.status === 'NEW' ? (
            <button
              type="button"
              className="btn-ghost btn-xs"
              onClick={ack}
              disabled={busy}
              title="Acknowledge this alert"
            >
              <CheckCircle2 size={12} aria-hidden /> Mark as seen
            </button>
          ) : (
            alert.status === 'ACKNOWLEDGED' &&
            onResolve && (
              <button type="button" className="btn-ghost btn-xs" onClick={() => setConfirmResolve(true)} disabled={busy}>
                Close
              </button>
            )
          )}
        </div>
      </div>

      {!compact && (alert.acknowledgedBy || alert.resolvedAt) && (
        <p className="border-t border-line/60 py-1.5 pl-4 pr-3.5 text-2xs text-ink-faint">
          {alert.acknowledgedBy && <>Seen by {alert.acknowledgedBy}. </>}
          {alert.resolvedAt && <>Closed {relativeTime(alert.resolvedAt)}.</>}
        </p>
      )}

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
