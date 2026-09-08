import { useNavigate } from 'react-router-dom';
import { Siren, X } from 'lucide-react';
import { useAlerts } from '@/hooks/useAlerts';
import { useToast } from '@/features/system/ToastProvider';
import { cn, formatTime, severityBar } from '@/lib/utils';

/**
 * Global real-time alert banner. Appears the moment a watchlist match is
 * raised on any camera and links straight into the investigation workspace.
 * Severity language: 3px rail, chip, mono plate, mono confidence, one-line
 * reason, one primary action.
 */
export function AlertBanner() {
  const { latestAlert, dismissLatest, acknowledge } = useAlerts();
  const navigate = useNavigate();
  const toast = useToast();

  if (!latestAlert) return null;
  const a = latestAlert;

  return (
    <div
      role="alert"
      aria-live="assertive"
      className="animate-slide-in relative border-b border-critical/40 bg-critical/[0.08]"
    >
      <span className={cn('absolute inset-y-0 left-0 w-[3px]', severityBar[a.severity])} aria-hidden />
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2 py-2 pl-4 pr-4">
        <Siren size={15} className="shrink-0 animate-pulse text-critical" aria-hidden />
        <span className="text-2xs font-bold uppercase tracking-[0.12em] text-critical">
          {a.severity} · {a.category}
        </span>
        <span className="plate text-sm text-ink">{a.plate}</span>
        <span className="min-w-0 flex-1 truncate text-2xs text-ink-muted">
          {a.note?.trim() || `Watchlist match — ${a.category.toLowerCase()}`} · {a.cameraName ?? a.cameraId.toUpperCase()} ·{' '}
          {a.location} · <span className="font-mono tabular-nums">{formatTime(a.createdAt)}</span>
          {a.confidence != null && (
            <span className="font-mono tabular-nums text-ink"> · {a.confidence.toFixed(1)}% match</span>
          )}
        </span>

        <div className="flex shrink-0 items-center gap-1.5">
          <button type="button" className="btn-tint btn-xs" onClick={() => navigate(`/vehicles/${a.plate}`)}>
            Trace
          </button>
          <button
            type="button"
            className="btn-ghost btn-xs"
            onClick={async () => {
              await acknowledge(a.id);
              toast.success('Alert acknowledged', `${a.plate} · ${a.cameraName ?? a.cameraId}`);
            }}
          >
            Mark as seen
          </button>
          <button
            type="button"
            className="btn-ghost btn-xs h-7 w-7 px-0"
            onClick={dismissLatest}
            aria-label="Dismiss alert banner"
          >
            <X size={12} aria-hidden />
          </button>
        </div>
      </div>
    </div>
  );
}
