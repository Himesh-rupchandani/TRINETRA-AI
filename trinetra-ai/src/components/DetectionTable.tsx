import { Link } from 'react-router-dom';
import { Eye, Map } from 'lucide-react';
import type { VehicleEvent } from '@/types';
import { EmptyState } from '@/ui/Feedback';
import { Badge } from '@/ui/Badge';
import { cn } from '@/lib/utils';
import { EVENT_TYPE_LABELS, formatTime } from '@/lib/uiHelpers';
import { VehicleThumb } from './Evidence';

/**
 * Sighting history as a proper table — chronological, row actions on
 * hover, wanted rows tinted. The workhorse of vehicle investigation.
 */
export function DetectionTable({
  events,
  activeEventId,
  onViewEvidence,
  onViewOnMap,
  className,
}: {
  events: VehicleEvent[];
  activeEventId?: string | null;
  onViewEvidence?: (ev: VehicleEvent) => void;
  onViewOnMap?: (ev: VehicleEvent) => void;
  className?: string;
}) {
  if (events.length === 0) {
    return (
      <EmptyState
        title="No sightings recorded"
        detail="When a camera recognises this vehicle, each reading will appear here."
        className={className}
      />
    );
  }

  return (
    <div className={cn('overflow-x-auto', className)}>
      <table className="tbl">
        <thead>
          <tr>
            <th>Time</th>
            <th>Camera</th>
            <th>Type</th>
            <th>Confidence</th>
            <th>Direction</th>
            <th className="text-right">Evidence</th>
          </tr>
        </thead>
        <tbody>
          {events.map((ev) => (
            <tr
              key={ev.id}
              className={cn(
                ev.id === activeEventId && 'bg-accent-weak/60',
                ev.watchlistMatch && 'bg-critical/[0.03]',
                (onViewEvidence || onViewOnMap) && 'row-click',
              )}
              onClick={() => onViewEvidence?.(ev)}
            >
              <td className="mono tabular-nums text-ink">{formatTime(ev.timestamp)}</td>
              <td>
                <div className="flex items-center gap-2.5">
                  <VehicleThumb ev={ev} size={30} />
                  <span className="mono text-xs text-ink-muted">{ev.cameraName ?? ev.cameraId.toUpperCase()}</span>
                </div>
              </td>
              <td>
                {ev.watchlistMatch ? (
                  <Badge tone="danger">Wanted match</Badge>
                ) : (
                  <span className="text-ink-muted">{EVENT_TYPE_LABELS[ev.eventType] ?? ev.eventType}</span>
                )}
              </td>
              <td className="mono tabular-nums text-ink-muted">
                {ev.plateConfidence ? `${(ev.plateConfidence <= 1 ? ev.plateConfidence * 100 : ev.plateConfidence).toFixed(0)}%` : '—'}
              </td>
              <td className="text-ink-muted">{ev.direction ?? '—'}</td>
              <td className="text-right">
                <span className="inline-flex items-center gap-0.5 opacity-0 transition-opacity duration-150 [.tbl tbody tr:hover_&]:opacity-100">
                  {onViewEvidence && (
                    <Link
                      to={`/vehicles/${ev.plate}?evidence=${ev.id}`}
                      className="rounded p-1.5 text-ink-faint transition-colors hover:bg-accent-weak hover:text-accent-strong active:scale-95"
                      title="Open evidence"
                      aria-label={`Open evidence for sighting at ${ev.cameraId}`}
                    >
                      <Eye size={14} aria-hidden />
                    </Link>
                  )}
                  {onViewOnMap && (
                    <button
                      type="button"
                      className="rounded p-1.5 text-ink-faint transition-colors hover:bg-accent-weak hover:text-accent-strong active:scale-95"
                      title="Show on map"
                      aria-label={`Show sighting on map`}
                      onClick={(e) => {
                        e.stopPropagation();
                        onViewOnMap(ev);
                      }}
                    >
                      <Map size={14} aria-hidden />
                    </button>
                  )}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
