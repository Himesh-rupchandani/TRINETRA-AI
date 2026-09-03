import { memo } from 'react';
import { Car, Pause, Play, ShieldAlert } from 'lucide-react';
import type { VehicleEvent } from '@/types';
import { PlateLink } from '@/components/common/Links';
import { EmptyState } from '@/components/common/Panel';
import { cn, relativeTime, confidenceClass } from '@/lib/utils';
import { hideBrokenImage, vehicleStill } from '@/utils/mediaAssets';
import { useLiveEvents } from '@/hooks/useLiveEvents';

export const EventRow = memo(function EventRow({ event }: { event: VehicleEvent }) {
  const watch = event.watchlistMatch;
  return (
    <li
      className={cn(
        'flex items-center gap-3 border-b border-line/60 px-4 py-2.5 text-xs transition-colors hover:bg-surface-2',
        watch && 'bg-critical/[0.05]',
      )}
    >
      <span
        className={cn(
          'relative grid h-9 w-14 shrink-0 place-items-center overflow-hidden rounded-md border border-line bg-surface-2 text-ink-faint',
          watch && 'ring-1 ring-critical/70',
        )}
      >
        <Car size={14} aria-hidden />
        <img
          src={vehicleStill(event.vehicleClass)}
          alt=""
          onError={hideBrokenImage}
          loading="lazy"
          className="absolute inset-0 h-full w-full object-cover"
        />
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5">
          <PlateLink plate={event.plate} size="sm" className="shrink-0" />
          {watch && <ShieldAlert size={13} className="shrink-0 text-critical" aria-hidden />}
        </div>
        <p className="mt-0.5 truncate text-2xs text-ink-faint">
          {event.cameraName ?? event.cameraId.toUpperCase()} · {relativeTime(event.timestamp)}
        </p>
      </div>
      <span
        className={cn(
          'shrink-0 font-mono text-sm font-bold tabular-nums',
          confidenceClass(event.plateConfidence),
        )}
      >
        {event.plateConfidence ? `${event.plateConfidence.toFixed(0)}%` : '—'}
      </span>
    </li>
  );
});

/** Rolling detection feed fed by the realtime channel (simulated in mock mode). */
export function LiveEventFeed({
  seed = [],
  max = 40,
  className,
}: {
  seed?: VehicleEvent[];
  max?: number;
  className?: string;
}) {
  const { events, paused, setPaused } = useLiveEvents();
  const combined = [...events, ...seed]
    .filter((e, i, arr) => arr.findIndex((x) => x.id === e.id) === i)
    .sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime())
    .slice(0, max);

  return (
    <div className={cn('flex h-full min-h-0 flex-col', className)}>
      <div className="flex items-center justify-between gap-2 border-b border-line px-4 py-2.5 text-[11px] uppercase tracking-wide text-ink-faint">
        <span className="flex items-center gap-1.5">
          <span className={cn('h-1.5 w-1.5 rounded-full', paused ? 'bg-ink-faint' : 'bg-online animate-pulse')} aria-hidden />
          {paused ? 'Paused' : 'Live now'}
        </span>
        <button
          type="button"
          className="btn-ghost btn-xs"
          onClick={() => setPaused(!paused)}
          aria-label={paused ? 'Resume live feed' : 'Pause live feed'}
        >
          {paused ? <Play size={11} aria-hidden /> : <Pause size={11} aria-hidden />}
          {paused ? 'Resume' : 'Pause'}
        </button>
      </div>
      {combined.length === 0 ? (
        <EmptyState title="Awaiting detections" detail="Live vehicle events will appear here as cameras report." />
      ) : (
        <ul className="min-h-0 flex-1 overflow-y-auto overflow-x-hidden" aria-label="Live event feed">
          {combined.map((e) => (
            <EventRow key={e.id} event={e} />
          ))}
        </ul>
      )}
    </div>
  );
}
