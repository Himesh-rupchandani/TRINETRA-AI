import { useEffect, useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { CameraOff, FileImage, ImageOff, MapPin, RefreshCw, ScanLine } from 'lucide-react';
import type { VehicleEvent } from '@/types';
import { cn, formatDateTime, prettyPlate, prettyVehicleClass, relativeTime } from '@/lib/utils';
import { realCrops, withCacheBust } from '@/utils/evidence';
import { ConfidenceBar } from '@/components/common/Links';
import { EmptyState } from '@/components/common/Panel';

/**
 * Evidence panel — the REAL captured crops for one sighting.
 *
 * Imagery rule (non-negotiable for investigative material): this panel renders
 * only crops the CV engine actually stored and the backend serves from its
 * evidence route (`GET /api/evidence/{ref}`). Demo/synthetic frames are
 * filtered out by `realCrops()`, so a generated picture can never be shown to
 * an operator as if a camera had captured it. When a sighting has no genuine
 * crop the panel says so plainly instead of substituting a stock image.
 */

type CropState = 'none' | 'loading' | 'ready' | 'error';

/**
 * One captured crop, with honest load states: a missing or pruned evidence file
 * degrades to a placeholder, never to a broken-image icon.
 */
function CropImage({
  src,
  alt,
  className,
  nonce,
  placeholder,
}: {
  src?: string;
  alt: string;
  className?: string;
  nonce: number;
  placeholder: (reason: 'missing' | 'error') => ReactNode;
}) {
  // Load state is keyed on (src, nonce) so a new sighting or a manual reload
  // starts over at "loading" — derived during render, no effect needed.
  const key = `${src ?? ''}|${nonce}`;
  const [loaded, setLoaded] = useState<{ key: string; state: CropState }>(() => ({
    key,
    state: src ? 'loading' : 'none',
  }));
  const state: CropState = loaded.key === key ? loaded.state : src ? 'loading' : 'none';

  if (!src) return <>{placeholder('missing')}</>;

  return (
    <>
      {state === 'loading' && (
        <div className="absolute inset-0 grid place-items-center bg-surface-2 text-2xs text-ink-faint">
          <span className="flex items-center gap-1.5">
            <RefreshCw size={12} className="animate-spin" aria-hidden />
            Fetching captured crop…
          </span>
        </div>
      )}
      {state === 'error' && placeholder('error')}
      <img
        src={withCacheBust(src, nonce)}
        alt={alt}
        onLoad={() => setLoaded({ key, state: 'ready' })}
        onError={() => setLoaded({ key, state: 'error' })}
        className={cn('relative', className, state === 'ready' ? 'opacity-100' : 'opacity-0')}
        decoding="async"
      />
    </>
  );
}

/** Explains exactly why no real image is on screen — never a stand-in photo. */
function NoCrop({
  reason,
  cropOnly,
  synthetic,
  ref,
}: {
  reason: 'missing' | 'error';
  cropOnly?: boolean;
  synthetic?: boolean;
  ref?: string;
}) {
  const title =
    reason === 'error'
      ? 'Captured crop unavailable'
      : cropOnly
        ? 'Full frame not captured'
        : 'No captured image for this sighting';
  const detail =
    reason === 'error'
      ? 'The evidence file is not in the store — it was pruned by retention or never written for this event.'
      : cropOnly
        ? 'This sighting was stored as an ANPR crop only. The plate crop is shown below.'
        : synthetic
          ? 'This sighting comes from the demo dataset. The evidence panel shows real captured crops only — run the CV engine against the backend to see the frame and plate crop it stored.'
          : 'The CV engine stored no frame for this event, so there is nothing real to show. No synthetic stand-in is rendered in its place.';

  return (
    <div className="grid aspect-video w-full place-items-center gap-1.5 bg-surface-2 px-6 text-center">
      <ImageOff size={20} className="text-ink-faint" aria-hidden />
      <p className="text-2xs font-semibold text-ink-muted">{title}</p>
      <p className="max-w-md text-[10px] leading-relaxed text-ink-faint">{detail}</p>
      {ref && <p className="font-mono text-[10px] text-ink-faint">{ref}</p>}
    </div>
  );
}

export function EvidencePanel({
  event,
  className,
  dense = false,
}: {
  event?: VehicleEvent | null;
  className?: string;
  dense?: boolean;
}) {
  const [now, setNow] = useState(() => Date.now());

  const crops = realCrops(event?.evidence);
  const eventId = event?.id;

  // Cache-bust token, keyed per sighting: switching sightings starts clean,
  // "Reload crop" bumps it so the browser re-fetches the file from the store.
  const [reload, setReload] = useState<{ id?: string; n: number }>({ n: 0 });
  const nonce = reload.id === eventId ? reload.n : 0;
  const reloadCrop = () => setReload({ id: eventId, n: nonce + 1 });

  // Keep the capture age live so an operator can see how fresh the crop is.
  const hasCrop = crops != null;
  useEffect(() => {
    if (!hasCrop) return;
    const t = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(t);
  }, [hasCrop]);

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

  const cropAgeMs = crops?.capturedAt ? now - new Date(crops.capturedAt).getTime() : Infinity;
  const isFresh = crops != null && Number.isFinite(cropAgeMs) && cropAgeMs < 60_000;
  const frameAlt = `Captured CCTV frame from ${event.cameraName ?? event.cameraId} at ${formatDateTime(event.timestamp)}`;

  return (
    <div className={cn('flex flex-col gap-3.5 p-4', className)}>
      <figure className="overflow-hidden rounded border border-line bg-black">
        {/* OSD — camera + how fresh this capture is */}
        <div className="flex items-center justify-between gap-2 border-b border-line bg-surface-1 px-3 py-1.5 font-mono text-[10px]">
          <span className="truncate text-ink-muted">
            {event.cameraName ?? event.cameraId.toUpperCase()} · {event.location ?? '—'}
          </span>
          <span className="flex shrink-0 items-center gap-1.5 text-ink-faint">
            {isFresh && (
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-online" aria-hidden />
            )}
            <span className="tabular-nums">{formatDateTime(event.timestamp)}</span>
            {crops && <span className="tabular-nums text-online">{relativeTime(crops.capturedAt, now)}</span>}
          </span>
        </div>

        <div className="relative aspect-video w-full bg-black">
          <CropImage
            src={crops?.frameUrl}
            alt={frameAlt}
            nonce={nonce}
            className="h-full w-full object-contain"
            placeholder={(reason) => (
              <NoCrop
                reason={reason}
                cropOnly={!crops?.frameUrl && !!crops?.plateCropUrl}
                synthetic={event.evidence?.synthetic}
                ref={event.evidenceRef}
              />
            )}
          />
          {crops?.frameUrl && (
            <button
              type="button"
              onClick={reloadCrop}
              className="btn-ghost btn-xs absolute right-2 top-2 bg-black/60 text-slate-200 hover:text-white"
              title="Re-fetch this crop from the evidence store"
            >
              <RefreshCw size={12} aria-hidden /> Reload crop
            </button>
          )}
        </div>

        <figcaption className="flex items-center justify-between gap-2 border-t border-line bg-surface-1 px-3 py-1.5 text-[10px] text-ink-faint">
          <span className="flex min-w-0 items-center gap-1">
            <FileImage size={10} aria-hidden />
            <span className="truncate font-mono">{event.evidenceRef ?? 'no evidence reference'}</span>
          </span>
          {crops?.frameUrl ? (
            <span className="chip shrink-0 border-online/45 bg-online/10 text-online">
              <ScanLine size={10} aria-hidden /> Captured crop
            </span>
          ) : (
            <span className="chip shrink-0 border-line bg-surface-3 text-ink-faint">
              <CameraOff size={10} aria-hidden /> No captured frame
            </span>
          )}
        </figcaption>
      </figure>

      <div className="grid gap-3.5 sm:grid-cols-2">
        <figure className="overflow-hidden rounded border border-line bg-black">
          <div className="relative grid min-h-[96px] w-full place-items-center bg-black">
            <CropImage
              src={crops?.plateCropUrl}
              alt={`ANPR plate crop reading ${event.plate}`}
              nonce={nonce}
              className="max-h-44 w-full object-contain"
              placeholder={() => (
                <div className="grid h-24 w-full place-items-center bg-surface-2 px-4 text-center text-2xs text-ink-faint">
                  No plate crop captured
                </div>
              )}
            />
          </div>
          <figcaption className="border-t border-line bg-surface-1 px-3 py-1.5 text-[10px] text-ink-faint">
            <ScanLine size={10} className="mr-1 inline" aria-hidden /> ANPR crop
            {crops?.plateCropUrl ? ' · stored by the CV engine' : ''}
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
