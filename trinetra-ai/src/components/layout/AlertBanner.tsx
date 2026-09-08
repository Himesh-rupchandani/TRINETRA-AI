import { useNavigate } from 'react-router-dom';
import { Siren, X } from 'lucide-react';
import { useAlerts } from '@/hooks/useAlerts';
import { useToast } from '@/features/system/ToastProvider';
import { cn, formatTime, severityBar } from '@/lib/utils';

/**
 * Global real-time alert banner. Appears the moment a watchlist match is
 * raised on any camera and links straight into the investigation workspace.
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
      className="animate-slide-in border-b border-critical/30 bg-critical/10"
    >
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 px-5 py-2.5 sm:px-6">
        <span className={cn('h-6 w-0.5 shrink-0 rounded-full', severityBar[a.severity])} aria-hidden />
        <Siren size={14} className="shrink-0 text-critical" aria-hidden />
        <span className="text-2xs font-semibold uppercase tracking-widest text-critical">
          {a.severity} · {a.category}
        </span>
        <span className="plate text-sm text-ink">{a.plate}</span>
        <span className="text-2xs text-ink-muted">
          {a.cameraName ?? a.cameraId.toUpperCase()} · {a.location} · {formatTime(a.createdAt)}
          {a.confidence != null && ` · ${a.confidence.toFixed(1)}% match`}
        </span>

        <div className="ml-auto flex items-center gap-2">
          <button
            type="button"
            className="btn-danger btn-xs"
            onClick={() => navigate(`/vehicles/${a.plate}`)}
          >
            Look up vehicle
          </button>
          <button
            type="button"
            className="btn-ghost btn-xs"
            onClick={() => navigate(`/cameras/${a.cameraId}`)}
          >
            Open camera
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
            className="btn-ghost btn-xs"
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
