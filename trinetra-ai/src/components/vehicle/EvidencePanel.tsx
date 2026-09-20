import { useState } from 'react';
import { Link } from 'react-router-dom';
import { FileImage, ImageOff, MapPin, ScanLine, AlertCircle } from 'lucide-react';
import type { VehicleEvent } from '@/types';
import { cn, formatDateTime, formatVideoOffset, prettyPlate, prettyVehicleClass } from '@/lib/utils';
import { hideBrokenImage, trackId, vehicleStill } from '@/utils/mediaAssets';
import { ConfidenceBar } from '@/components/common/Links';
import { EmptyState } from '@/components/common/Panel';

/**
 * Evidence panel — CCTV frame + plate crop + capture metadata.
 * Handles real evidence (including uploaded videos), synthetic demo frames,
 * and broken images with proper fallbacks so no broken-image icon ever shows.
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
  // Errors belong to one URL, not to the panel forever. New detections must
  // load automatically after an older photo failed or expired.
  const [failedFrame, setFailedFrame] = useState<string | null>(null);
  const [failedPlate, setFailedPlate] = useState<string | null>(null);

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
  const frameError = Boolean(ev?.frameUrl && failedFrame === ev.frameUrl);
  const plateError = Boolean(ev?.plateCropUrl && failedPlate === ev.plateCropUrl);
  const isUpload = event.evidenceRef?.startsWith('uploads/') || event.evidenceRef?.startsWith('analysis/');

  return (
    <div className={cn('flex flex-col gap-3.5 p-4', className)}>
      <figure className="overflow-hidden rounded border border-line bg-black">
        {ev?.synthetic ? (
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
            <div
              className="pointer-events-none absolute left-1/2 top-1/2 h-[54%] w-[46%] -translate-x-1/2 -translate-y-[53%] border-2 border-sky-400/90"
              aria-hidden
            />
            <div className="pointer-events-none absolute left-1/2 top-[25%] -translate-x-1/2 whitespace-nowrap bg-sky-400 px-1.5 py-0.5 font-mono text-[10px] font-bold text-slate-900">
              {prettyVehicleClass(event.vehicleClass)} · TRACK {trackId(event.id)}
            </div>
            <div className="pointer-events-none absolute left-1/2 top-[62%] -translate-x-1/2 rounded-sm bg-white px-1.5 py-0.5 font-mono text-[10px] font-bold text-slate-900 shadow">
              {event.plate}
            </div>
            <div className="absolute inset-x-0 top-0 flex items-center justify-between gap-2 bg-black/55 px-2 py-1 font-mono text-[10px] text-slate-200">
              <span className="truncate">
                {event.cameraName ?? event.cameraId.toUpperCase()} · {event.location}
              </span>
              <span className="shrink-0 tabular-nums">{formatDateTime(event.timestamp)}</span>
            </div>
            <div className="absolute inset-x-0 bottom-0 flex items-center justify-between gap-2 bg-black/55 px-2 py-1 font-mono text-[10px]">
              <span className="text-slate-400">TRINETRA AI · ANPR PIPELINE</span>
              <span className="font-bold text-amber-400">DEMO / SYNTHETIC FRAME</span>
            </div>
          </div>
        ) : ev?.frameUrl && !frameError ? (
          <img
            key={ev.frameUrl}
            src={ev.frameUrl}
            alt={`CCTV frame from ${event.cameraName ?? event.cameraId} at ${formatDateTime(event.timestamp)}`}
            className="aspect-video w-full object-contain"
            loading="lazy"
            decoding="async"
            onError={() => setFailedFrame(ev.frameUrl!)}
          />
        ) : ev?.frameUrl && frameError ? (
          <div className="grid aspect-video w-full place-items-center gap-2 bg-surface-2 p-4 text-center">
            <AlertCircle size={20} className="text-ink-faint" aria-hidden />
            <div>
              <p className="text-2xs font-semibold text-ink-muted">Evidence image unavailable</p>
              <p className="mt-1 text-[10px] leading-relaxed text-ink-faint">
                The file {event.evidenceRef} could not be loaded. It may have been cleaned up or the evidence folder is not persisted.
                {isUpload ? ' For uploaded videos, evidence is stored under the backend evidence folder.' : ''}
              </p>
            </div>
            <button type="button" className="btn-ghost btn-xs" onClick={() => setFailedFrame(null)}>
              Retry photo
            </button>
          </div>
        ) : (
          <div className="grid aspect-video w-full place-items-center gap-2 bg-surface-2 p-4 text-center">
            <ImageOff size={20} className="text-ink-faint" aria-hidden />
            <p className="text-2xs text-ink-faint">Frame not retained</p>
            {isUpload && (
              <p className="text-[10px] text-ink-faint">Uploaded video — only vehicle crops are saved as evidence.</p>
            )}
          </div>
        )}
        <figcaption className="flex items-center justify-between gap-2 border-t border-line bg-surface-1 px-3 py-1.5 text-[10px] text-ink-faint">
          <span className="flex items-center gap-1 truncate">
            <FileImage size={10} aria-hidden /> <span className="truncate">{event.evidenceRef ?? '—'}</span>
          </span>
          <span className="flex shrink-0 items-center gap-1.5">
            {isUpload && <span className="chip border-brand/30 bg-brand/10 text-brand">Uploaded video</span>}
            {ev?.synthetic && (
              <span className="chip border-degraded/45 bg-degraded/10 text-degraded">Demo / synthetic</span>
            )}
          </span>
        </figcaption>
      </figure>

      <div className="grid gap-3.5 sm:grid-cols-2">
        <figure className="overflow-hidden rounded border border-line bg-black">
          {ev?.plateCropUrl && !plateError ? (
            <img
              key={ev.plateCropUrl}
              src={ev.plateCropUrl}
              alt={event.plate}
              className="flex h-20 w-full items-center justify-center object-contain font-mono text-2xl font-bold tracking-widest text-white"
              loading="lazy"
              decoding="async"
              onError={() => setFailedPlate(ev.plateCropUrl!)}
            />
          ) : ev?.plateCropUrl && plateError ? (
            <div className="grid h-20 place-items-center gap-1 bg-surface-2 p-2 text-center">
              <p className="font-mono text-xs font-bold tracking-widest text-ink">{prettyPlate(event.plate)}</p>
              <p className="text-[10px] text-ink-faint">Plate crop unavailable</p>
              <button type="button" className="text-[10px] underline" onClick={() => setFailedPlate(null)}>Retry plate crop</button>
            </div>
          ) : (
            <div className="grid h-20 place-items-center bg-surface-2 text-2xs text-ink-faint">
              {isUpload ? 'Plate crop not saved for uploads' : 'No plate crop'}
            </div>
          )}
          <figcaption className="border-t border-line bg-surface-1 px-3 py-1.5 text-[10px] text-ink-faint">
            <ScanLine size={10} className="mr-1 inline" aria-hidden /> ANPR crop
            {isUpload && <span className="ml-1 text-ink-faint">(vehicle crop only)</span>}
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
