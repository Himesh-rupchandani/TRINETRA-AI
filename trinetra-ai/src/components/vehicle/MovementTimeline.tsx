import { ArrowDown, Clock, Gauge, MapPin, Route } from 'lucide-react';
import type { RoutePoint } from '@/types';
import { cn, formatDuration, formatTime, formatVideoOffset } from '@/lib/utils';
import { EmptyState } from '@/components/common/Panel';

/**
 * Chronological cross-camera movement timeline:
 * CAM04 → CAM08 → CAM12 → CAM17, with dwell gaps and derived speed.
 */
export function MovementTimeline({
  points,
  activeSequence,
  onSelect,
  className,
}: {
  points: RoutePoint[];
  activeSequence?: number | null;
  onSelect?: (point: RoutePoint) => void;
  className?: string;
}) {
  if (!points.length) {
    return (
      <EmptyState
        icon={Route}
        title="No movement recorded"
        detail="This vehicle has no cross-camera sightings in the retained window."
      />
    );
  }

  return (
    <ol className={cn('relative p-2.5', className)} aria-label="Chronological movement timeline">
      {points.map((p, i) => {
        const active = p.sequence === activeSequence;
        const last = i === points.length - 1;
        return (
          <li key={`${p.eventId}-${p.sequence}`} className="relative pl-8">
            {!last && <span className="absolute left-[13px] top-6 h-[calc(100%-8px)] w-px bg-brand/25" aria-hidden />}
            <span
              className={cn(
                'absolute left-0 top-1 grid h-[26px] w-[26px] place-items-center rounded-full border-2 font-mono text-2xs font-bold',
                active
                  ? 'border-brand bg-brand text-on-brand shadow-glow'
                  : 'border-brand/30 bg-brand/10 text-brand',
              )}
              aria-hidden
            >
              {p.sequence}
            </span>

            <button
              type="button"
              onClick={() => onSelect?.(p)}
              className={cn(
                'mb-3 w-full rounded-xl border px-3 py-2.5 text-left transition-colors',
                active
                  ? 'border-brand/50 bg-brand/10'
                  : 'border-line bg-surface-2/60 hover:border-line-strong hover:bg-surface-2',
              )}
              aria-current={active ? 'step' : undefined}
            >
              <div className="flex items-baseline justify-between gap-2">
                <span className="font-mono text-xs font-bold text-ink">{p.cameraName}</span>
                <time className="font-mono text-2xs tabular-nums text-ink" dateTime={p.timestamp}>
                  {formatTime(p.timestamp)}
                  {p.videoOffsetSec != null && (
                    <span className="ml-1.5 font-normal text-ink-faint">
                      · {formatVideoOffset(p.videoOffsetSec)}
                    </span>
                  )}
                </time>
              </div>
              <p className="mt-1 flex items-center gap-1 truncate text-2xs text-ink-muted">
                <MapPin size={9} className="shrink-0" aria-hidden />
                {p.location}
              </p>
              <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[10px] text-ink-faint">
                <span>Plate match {p.plateConfidence.toFixed(1)}%</span>
                {p.distanceKm != null && <span>{p.distanceKm.toFixed(2)} km from the last camera</span>}
                {p.speedKmph != null && (
                  <span className="inline-flex items-center gap-0.5">
                    <Gauge size={9} aria-hidden /> {p.speedKmph} km/h average
                  </span>
                )}
              </div>
            </button>

            {!last && (
              <div className="mb-3 flex items-center gap-1 pl-0.5 text-[10px] text-ink-faint">
                <ArrowDown size={10} aria-hidden />
                <Clock size={9} aria-hidden />
                {formatDuration(points[i + 1].gapMinutes ?? 0)} later
              </div>
            )}
          </li>
        );
      })}
    </ol>
  );
}
