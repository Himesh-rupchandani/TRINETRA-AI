import { useNavigate } from 'react-router-dom';
import { Siren, X } from 'lucide-react';
import { useAlerts } from '@/hooks/useAlerts';
import { useToast } from '@/features/system/ToastProvider';
import { Button } from '@/ui/Button';
import { formatTime, severityTone } from '@/lib/uiHelpers';

/**
 * Real-time alert ticker — appears under the top bar the moment a
 * watchlist match is raised. Slides in, stays calm, links to action.
 */
export function AlertTicker() {
  const { latestAlert, dismissLatest, acknowledge } = useAlerts();
  const navigate = useNavigate();
  const toast = useToast();

  if (!latestAlert) return null;
  const a = latestAlert;

  return (
    <div role="alert" aria-live="assertive" className="row-in border-b border-critical/20 bg-critical/[0.06]">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-2 sm:px-5">
        <span className={`h-5 w-[3px] shrink-0 rounded-full ${severityTone[a.severity].bar}`} aria-hidden />
        <Siren size={14} className="shrink-0 text-critical" aria-hidden />
        <span className="text-[11px] font-bold uppercase tracking-[0.1em] text-critical">
          {a.severity} · {a.category}
        </span>
        <span className="plate text-[13px] text-ink">{a.plate}</span>
        <span className="hidden text-xs text-ink-muted sm:inline">
          {a.cameraName ?? a.cameraId.toUpperCase()} · {a.location} · {formatTime(a.createdAt)}
          {a.confidence != null && ` · ${(a.confidence * 100).toFixed(0)}% match`}
        </span>

        <div className="ml-auto flex items-center gap-2">
          <Button variant="danger" size="xs" onClick={() => navigate(`/vehicles/${a.plate}`)}>
            Investigate
          </Button>
          <Button variant="ghost" size="xs" onClick={() => navigate(`/cameras/${a.cameraId}`)}>
            Camera
          </Button>
          <Button
            variant="ghost"
            size="xs"
            onClick={async () => {
              await acknowledge(a.id);
              toast.success('Alert acknowledged', `${a.plate} · ${a.cameraName ?? a.cameraId}`);
            }}
          >
            Mark seen
          </Button>
          <button
            type="button"
            className="grid h-6 w-6 place-items-center rounded text-ink-faint transition-colors hover:bg-surface-2 hover:text-ink active:scale-95"
            onClick={dismissLatest}
            aria-label="Dismiss alert banner"
          >
            <X size={13} aria-hidden />
          </button>
        </div>
      </div>
    </div>
  );
}
