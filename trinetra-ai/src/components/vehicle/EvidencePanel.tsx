import { Link } from 'react-router-dom';
import { FileImage, ImageOff, MapPin, ScanLine } from 'lucide-react';
import type { VehicleEvent } from '@/types';
import { cn, formatDateTime, prettyPlate, prettyVehicleClass } from '@/lib/utils';
import { ConfidenceBar } from '@/components/common/Links';
import { EmptyState } from '@/components/common/Panel';

/**
 * Evidence panel — CCTV frame + plate crop + capture metadata.
 * In mock mode the imagery is generated locally and clearly watermarked
 * "DEMO / SYNTHETIC"; with the backend connected these become signed URLs.
 */
export function EvidencePanel({
  event,
  className,
  dense = false,
}: {
  event?: VehicleEvent | null;
  className?: string;
  dense?: boolean;
}) {
  if (!event) {
    return (
      <div className={className}>
        <EmptyState
          icon={ImageOff}
          title="No evidence selected"
          detail="Select a detection from the timeline, map or table to review its captured frame."
        />
      </div>
    );
  }

  const ev = event.evidence;

  return (
    <div className={cn('flex flex-col gap-3.5 p-4', className)}>
      <figure className="overflow-hidden rounded border border-line bg-black">
        {ev?.frameUrl ? (
          <img
            src={ev.frameUrl}
            alt={`CCTV frame from ${event.cameraName ?? event.cameraId} at ${formatDateTime(event.timestamp)}`}
            className="aspect-video w-full object-cover"
            loading="lazy"
            decoding="async"
          />
        ) : (
          <div className="grid aspect-video w-full place-items-center bg-surface-2 text-2xs text-ink-faint">
            Frame not retained
          </div>
        )}
        <figcaption className="flex items-center justify-between gap-2 border-t border-line bg-surface-1 px-3 py-1.5 text-[10px] text-ink-faint">
          <span className="flex items-center gap-1">
            <FileImage size={10} aria-hidden /> {event.evidenceRef ?? '—'}
          </span>
          {ev?.synthetic && (
            <span className="chip border-degraded/45 bg-degraded/10 text-degraded">Demo / synthetic</span>
          )}
        </figcaption>
      </figure>

      <div className="grid gap-3.5 sm:grid-cols-2">
        <figure className="overflow-hidden rounded border border-line bg-black">
          {ev?.plateCropUrl ? (
            <img
              src={ev.plateCropUrl}
              alt={`Plate crop reading ${event.plate}`}
              className="w-full object-contain"
              loading="lazy"
              decoding="async"
            />
          ) : (
            <div className="grid h-20 place-items-center bg-surface-2 text-2xs text-ink-faint">No plate crop</div>
          )}
        <figcaption className="border-t border-line bg-surface-1 px-3 py-1.5 text-[10px] text-ink-faint">
          <ScanLine size={10} className="mr-1 inline" aria-hidden /> ANPR crop
        </figcaption>
      </figure>

      <dl className="grid grid-cols-2 content-start gap-x-3 gap-y-2 text-2xs">
          <dt className="text-ink-faint">Plate</dt>
          <dd className="plate text-right text-xs text-ink">{prettyPlate(event.plate)}</dd>
          <dt className="text-ink-faint">Confidence</dt>
          <dd className="flex justify-end">
            <ConfidenceBar value={event.plateConfidence} />
          </dd>
          <dt className="text-ink-faint">Camera</dt>
          <dd className="text-right">
            <Link to={`/cameras/${event.cameraId}`} className="font-mono text-ink hover:text-brand">
              {event.cameraName ?? event.cameraId.toUpperCase()}
            </Link>
          </dd>
          <dt className="text-ink-faint">Captured</dt>
          <dd className="text-right font-mono text-ink-muted">{formatDateTime(event.timestamp)}</dd>
          <dt className="text-ink-faint">Location</dt>
          <dd className="text-right text-ink-muted">{event.location ?? '—'}</dd>
          {!dense && (
            <>
              <dt className="text-ink-faint">Class</dt>
              <dd className="text-right text-ink-muted">{prettyVehicleClass(event.vehicleClass)}</dd>
              <dt className="text-ink-faint">Coordinates</dt>
              <dd className="text-right font-mono text-ink-muted">
                <span className="inline-flex items-center gap-1">
                  <MapPin size={9} aria-hidden />
                  {event.latitude.toFixed(4)}, {event.longitude.toFixed(4)}
                </span>
              </dd>
            </>
          )}
        </dl>
      </div>
    </div>
  );
}
