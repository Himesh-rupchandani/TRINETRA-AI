import { memo } from 'react';
import { Pause, Play, ShieldAlert } from 'lucide-react';
import type { VehicleEvent } from '@/types';
import { PlateLink } from '@/ui/Links';
import { Button } from '@/ui/Button';
import { EmptyState } from '@/ui/Feedback';
import { cn, relativeTime } from '@/lib/utils';
import { confidenceTone } from '@/lib/uiHelpers';
import { hideBrokenImage, vehicleStill } from '@/utils/mediaAssets';
import { useLiveEvents } from '@/hooks/useLiveEvents';

const Row = memo(function Row({ event }: { event: VehicleEvent }) {
  const watch = event.watchlistMatch;
  return (
    <li
      className={cn(
        'row-in flex items-center gap-3 border-b border-line/60 px-5 py-2.5 transition-colors last:border-b-0 hover:bg-surface-2/70',
        watch && 'bg-critical/[0.04]',
      )}
    >
      <span
        className={cn(
          'relative grid h-9 w-14 shrink-0 place-items-center overflow-hidden rounded-md border border-line bg-surface-3 text-ink-faint',
          watch && 'border-critical/40',
        )}
      >
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
          {watch && <ShieldAlert size={12} className="shrink-0 text-critical" aria-hidden />}
        </div>
        <p className="mt-0.5 truncate text-[11px] text-ink-faint">
          {event.cameraName ?? event.cameraId.toUpperCase()} · {relativeTime(event.timestamp)}
        </p>
      </div>
      <span className={cn('mono shrink-0 text-[13px] font-semibold tabular-nums', confidenceTone(event.plateConfidence))}>
        {event.plateConfidence ? `${(event.plateConfidence <= 1 ? event.plateConfidence * 100 : event.plateConfidence).toFixed(0)}%` : '—'}
      </span>
    </li>
  );
});

/**
 * Rolling detection feed fed by the realtime channel. New rows slide in;
 * the operator can pause the stream while reading a row.
 */
export function LiveDetections({
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
      <div className="flex items-center justify-between border-b border-line px-5 py-2">
        <span className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.1em] text-ink-faint">
          <span
            className={cn('h-1.5 w-1.5 rounded-full', paused ? 'bg-ink-faint' : 'live-dot bg-online')}
            aria-hidden
          />
          {paused ? 'Paused' : 'Live'}
        </span>
        <Button variant="ghost" size="xs" onClick={() => setPaused(!paused)} aria-label={paused ? 'Resume live feed' : 'Pause live feed'}>
          {paused ? <Play size={11} aria-hidden /> : <Pause size={11} aria-hidden />}
          {paused ? 'Resume' : 'Pause'}
        </Button>
      </div>
      {combined.length === 0 ? (
        <EmptyState title="Awaiting detections" detail="Live vehicle events appear here as cameras report." />
      ) : (
        <ul className="min-h-0 flex-1 overflow-y-auto overflow-x-hidden" aria-label="Live detection feed">
          {combined.map((e) => (
            <Row key={e.id} event={e} />
          ))}
        </ul>
      )}
    </div>
  );
}
