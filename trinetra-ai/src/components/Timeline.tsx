import { useMemo } from 'react';
import type { RoutePoint } from '@/types';
import { Badge } from '@/ui/Badge';
import { EmptyState } from '@/ui/Feedback';
import { cn } from '@/lib/utils';
import { formatTime } from '@/lib/uiHelpers';

export interface RouteStep {
  point: RoutePoint;
  eventIds: string[];
  counts: { total: number; wanted: number };
}


/**
 * Vertical journey timeline — dots and connecting rail, camera-labelled
 * stops, times on the left rail. Clicking a stop focuses it on the map.
 */
export function MovementTimeline({
  points,
  activeEventId,
  onSelect,
  className,
}: {
  points: RoutePoint[] | undefined;
  activeEventId: string | null;
  onSelect: (eventId: string) => void;
  className?: string;
}) {
  const steps = useMemo(() => points ?? [], [points]);

  if (steps.length === 0) {
    return (
      <EmptyState
        title="No route reconstructed"
        detail="Camera sightings for this vehicle will be joined into a journey here."
        className={className}
      />
    );
  }

  return (
    <ol className={cn('relative', className)} aria-label="Vehicle journey">
      <span
        className="absolute bottom-3 left-[57px] top-3 w-px bg-line"
        aria-hidden
      />
      {steps.map((p, i) => {
        const active = p.eventId === activeEventId;
        return (
          <li key={p.eventId} className="relative">
            <button
              type="button"
              onClick={() => onSelect(p.eventId)}
              aria-current={active ? 'true' : undefined}
              className={cn(
                'group flex w-full items-center gap-3.5 rounded-lg px-2 py-2.5 text-left transition-all duration-150',
                'hover:bg-surface-2/80 active:scale-[0.99]',
                active && 'bg-accent-weak/70',
              )}
            >
              <span className="mono w-11 shrink-0 text-right text-[11px] tabular-nums text-ink-faint">
                {formatTime(p.timestamp)}
              </span>
              <span className="relative z-10 shrink-0">
                <span
                  className={cn(
                    'block h-2.5 w-2.5 rounded-full border-2 bg-surface-1 transition-colors duration-150',
                    active ? 'border-accent' : 'border-line-strong group-hover:border-accent/60',
                  )}
                />
              </span>
              <span className="min-w-0 flex-1">
                <span className="flex items-center gap-2">
                  <span className="mono truncate text-[12.5px] font-semibold text-ink">
                    {p.cameraName}
                  </span>
                  {i === 0 && <Badge tone="info">First seen</Badge>}
                  {i === steps.length - 1 && steps.length > 1 && <Badge tone="accent">Latest</Badge>}
                </span>
                <span className="mt-0.5 block truncate text-[11px] text-ink-faint">{p.location}</span>
              </span>
            </button>
          </li>
        );
      })}
    </ol>
  );
}
