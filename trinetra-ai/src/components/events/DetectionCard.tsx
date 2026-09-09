import { memo } from 'react';
import { useNavigate } from 'react-router-dom';
import { Car, ShieldAlert } from 'lucide-react';
import type { VehicleEvent } from '@/types';
import { cn, relativeTime } from '@/lib/utils';
import { hideBrokenImage, vehicleStill } from '@/utils/mediaAssets';

/**
 * Compact front-view card for the home detections grid. The full live
 * feed lives on the Vehicle Log page; home shows the freshest six.
 */
export const DetectionCard = memo(function DetectionCard({ event }: { event: VehicleEvent }) {
  const navigate = useNavigate();
  const watch = event.watchlistMatch;
  const clickable = Boolean(event.plate);
  return (
    <article
      onClick={clickable ? () => navigate(`/vehicles/${event.plate}`) : undefined}
      className={cn(
        'panel group overflow-hidden transition-shadow hover:shadow-cardHover',
        clickable && 'cursor-pointer',
        watch && 'ring-1 ring-critical/50',
      )}
    >
      <div className="relative h-24 overflow-hidden border-b border-line bg-surface-2">
        <span className="grid h-full w-full place-items-center text-ink-faint" aria-hidden>
          <Car size={20} />
        </span>
        <img
          src={vehicleStill(event.vehicleClass)}
          alt=""
          onError={hideBrokenImage}
          loading="lazy"
          className="absolute inset-0 h-full w-full object-cover"
        />
        {watch && (
          <span className="absolute left-2 top-2 inline-flex items-center gap-1 rounded bg-critical/90 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider text-white">
            <ShieldAlert size={10} aria-hidden /> Wanted
          </span>
        )}
        <span className="absolute bottom-1.5 right-1.5 rounded bg-black/60 px-1.5 py-0.5 font-mono text-[10px] font-bold tabular-nums text-white">
          {event.plateConfidence ? `${event.plateConfidence.toFixed(0)}%` : '—'}
        </span>
      </div>
      <div className="p-3">
        <p className="truncate font-mono text-sm font-bold text-ink group-hover:text-brand">
          {event.plate || 'No plate read'}
        </p>
        <p className="mt-0.5 truncate text-2xs text-ink-muted">
          {event.cameraName ?? event.cameraId.toUpperCase()} · {relativeTime(event.timestamp)}
        </p>
      </div>
    </article>
  );
});
