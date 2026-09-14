import { Link } from 'react-router-dom';
import { FileImage, ImageOff, MapPin, ScanLine } from 'lucide-react';
import type { VehicleEvent } from '@/types';
import { cn, formatDateTime, formatVideoOffset, prettyPlate, prettyVehicleClass } from '@/lib/utils';
import { hideBrokenImage, trackId, vehicleStill } from '@/utils/mediaAssets';
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
        {ev?.synthetic ? (
          /* Demo frame: realistic per-class image + drawn ANPR overlay */
          <div className="relative aspect-video w-full overflow-hidden bg-black">
            <div className="absolute inset-0 grid place-items-center bg-surface-2 text-2xs text-ink-faint">
              <span className="flex items-center gap-1.5">
                <ScanLine size={12} aria-hidden />
                CCTV frame · image not available
              </span>
            </div>
            <img
              src={vehicleStill(event.vehicleClass)}
              alt={`CCTV frame from ${event.cameraName ?? event.cameraId} at ${formatDateTime(event.timestamp)}`}
              onError={hideBrokenImage}
              className="absolute inset-0 h-full w-full object-cover"
              loading="lazy"
              decoding="async"
            />
            {/* detection box */}
            <div
              className="pointer-events-none absolute left-1/2 top-1/2 h-[54%] w-[46%] -translate-x-1/2 -translate-y-[53%] border-2 border-sky-400/90"
              aria-hidden
            />
            {/* detection label */}
            <div className="pointer-events-none absolute left-1/2 top-[25%] -translate-x-1/2 whitespace-nowrap bg-sky-400 px-1.5 py-0.5 font-mono text-[10px] font-bold text-slate-900">
              {prettyVehicleClass(event.vehicleClass)} · TRACK {trackId(event.id)}
            </div>
            {/* plate on the vehicle */}
            <div className="pointer-events-none absolute left-1/2 top-[62%] -translate-x-1/2 rounded-sm bg-white px-1.5 py-0.5 font-mono text-[10px] font-bold text-slate-900 shadow">
              {event.plate}
            </div>
            {/* top OSD */}
            <div className="absolute inset-x-0 top-0 flex items-center justify-between gap-2 bg-black/55 px-2 py-1 font-mono text-[10px] text-slate-200">
              <span className="truncate">
                {event.cameraName ?? event.cameraId.toUpperCase()} · {event.location}
              </span>
              <span className="shrink-0 tabular-nums">{formatDateTime(event.timestamp)}</span>
            </div>
            {/* bottom OSD */}
            <div className="absolute inset-x-0 bottom-0 flex items-center justify-between gap-2 bg-black/55 px-2 py-1 font-mono text-[10px]">
              <span className="text-slate-400">TRINETRA AI · ANPR PIPELINE</span>
              <span className="font-bold text-amber-400">DEMO / SYNTHETIC FRAME</span>
            </div>
          </div>
        ) : ev?.frameUrl ? (
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
              alt={event.plate}
              className="flex h-20 w-full items-center justify-center object-contain font-mono text-2xl font-bold tracking-widest text-white"
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
          {event.videoOffsetSec != null && (
            <>
              <dt className="text-ink-faint">Video position</dt>
              <dd className="text-right font-mono text-ink-muted">
                {formatVideoOffset(event.videoOffsetSec)}
                {event.videoFile ? ` · ${event.videoFile}` : ''}
              </dd>
            </>
          )}
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
