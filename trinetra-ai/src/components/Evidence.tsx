import { Camera, Images, MapPin, ScanLine, ShieldCheck } from 'lucide-react';
import type { VehicleEvent } from '@/types';
import { KeyVal } from '@/ui/Feedback';
import { Badge } from '@/ui/Badge';
import { ConfidenceMeter } from '@/ui/Links';
import { cn, formatDateTime, prettyVehicleClass } from '@/lib/utils';
import { EVENT_TYPE_LABELS } from '@/lib/uiHelpers';
import { hideBrokenImage, trackId, vehicleStill } from '@/utils/mediaAssets';

/**
 * Evidence viewer for one detection: the captured frame (with the
 * drawn detection box when the frame itself is not archived), the
 * plate crop and the structured fact block. Demo-generated imagery is
 * always labelled — never presented as a real capture.
 */
export function Evidence({
  ev,
  className,
  dense = false,
}: {
  ev: VehicleEvent;
  className?: string;
  dense?: boolean;
}) {
  const evd = ev.evidence;
  const synthetic = Boolean(evd?.synthetic);

  return (
    <div className={cn('flex flex-col gap-4', className)}>
      <figure className="overflow-hidden rounded-xl border border-line bg-surface-1 shadow-xs">
        <div className="relative aspect-video bg-black">
          {evd?.frameUrl ? (
            <img
              src={evd.frameUrl}
              alt={`Captured frame of ${ev.plate} at ${ev.cameraName ?? ev.cameraId}`}
              onError={hideBrokenImage}
              loading="lazy"
              decoding="async"
              className="h-full w-full object-cover"
            />
          ) : (
            <>
              {/* No archived frame — show the class reference image with the
                  detection geometry drawn on top, clearly labelled. */}
              <div className="absolute inset-0 grid place-items-center bg-surface-2 text-2xs text-ink-faint">
                <span className="flex items-center gap-1.5">
                  <ScanLine size={12} aria-hidden /> CCTV frame · image not archived
                </span>
              </div>
              <img
                src={vehicleStill(ev.vehicleClass)}
                alt={`Reference view of ${ev.plate}`}
                onError={hideBrokenImage}
                loading="lazy"
                decoding="async"
                className="absolute inset-0 h-full w-full object-cover"
              />
              <div
                className="pointer-events-none absolute left-1/2 top-1/2 h-[54%] w-[46%] -translate-x-1/2 -translate-y-[53%] border-2 border-emerald-400/90"
                aria-hidden
              />
              <div className="pointer-events-none absolute left-1/2 top-[24%] -translate-x-1/2 whitespace-nowrap bg-emerald-400 px-1.5 py-0.5 font-mono text-[10px] font-bold text-slate-900" aria-hidden>
                {prettyVehicleClass(ev.vehicleClass)} · TRACK {trackId(ev.id)}
              </div>
            </>
          )}
          <span className="mono absolute left-2.5 top-2.5 rounded bg-black/65 px-2 py-0.5 text-[10px] tabular-nums text-white/90">
            {formatDateTime(ev.timestamp)}
          </span>
          {synthetic && (
            <span className="absolute right-2.5 top-2.5 rounded bg-black/65 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-amber-200">
              Demo · synthetic
            </span>
          )}
        </div>
        <figcaption className="flex items-center justify-between gap-3 border-t border-line px-3.5 py-2">
          <span className="mono text-[11px] text-ink-faint">
            {ev.cameraName ?? ev.cameraId.toUpperCase()} · {ev.location ?? '—'}
          </span>
          <span className="mono text-[11px] tabular-nums text-ink-faint">track {trackId(ev.id)}</span>
        </figcaption>
      </figure>

      <div className="grid gap-4 md:grid-cols-2">
        <div className="overflow-hidden rounded-xl border border-line bg-surface-1 shadow-xs">
          <div className="grid aspect-video place-items-center bg-surface-3">
            {evd?.plateCropUrl ? (
              <img
                src={evd.plateCropUrl}
                alt={`Plate crop of ${ev.plate}`}
                onError={hideBrokenImage}
                loading="lazy"
                className="h-full w-full object-cover"
              />
            ) : (
              <span className="plate rounded border border-line bg-surface-2 px-3 py-1.5 text-lg font-semibold tracking-[0.18em] text-ink">
                {ev.plate}
              </span>
            )}
          </div>
          <p className="border-t border-line px-3.5 py-2 text-center">
            <span className="plate text-sm font-semibold tracking-[0.14em] text-ink">{ev.plate}</span>
          </p>
        </div>

        <dl className={cn('grid content-start gap-x-4', dense ? 'grid-cols-2' : 'grid-cols-1 sm:grid-cols-2')}>
          <KeyVal label="Event type">{EVENT_TYPE_LABELS[ev.eventType] ?? ev.eventType}</KeyVal>
          <KeyVal label="Recorded at">{formatDateTime(ev.timestamp)}</KeyVal>
          <KeyVal label="Vehicle class">{ev.vehicleClass ? prettyVehicleClass(ev.vehicleClass) : '—'}</KeyVal>
          <KeyVal label="ANPR confidence">
            <ConfidenceMeter value={ev.plateConfidence} />
          </KeyVal>
          <KeyVal label="Camera">
            <span className="mono flex items-center gap-1.5">
              <Camera size={12} className="text-ink-faint" aria-hidden />
              {ev.cameraName ?? ev.cameraId.toUpperCase()}
            </span>
          </KeyVal>
          <KeyVal label="Place">
            <span className="flex items-center gap-1.5">
              <MapPin size={12} className="text-ink-faint" aria-hidden />
              {ev.location ?? '—'}
            </span>
          </KeyVal>
          <KeyVal label="Direction">{ev.direction ?? '—'}</KeyVal>
          <KeyVal label="Speed">{ev.speedKmph ? `${ev.speedKmph.toFixed(0)} km/h` : '—'}</KeyVal>
          {ev.videoFile && (
            <KeyVal label="Source footage">
              <span className="mono">{ev.videoFile}</span>
            </KeyVal>
          )}
          {ev.watchlistMatch && (
            <div className="col-span-full">
              <span className="inline-flex items-center gap-1.5 rounded-lg border border-critical/25 bg-critical/[0.06] px-3 py-1.5 text-xs font-semibold text-critical">
                <ShieldCheck size={13} aria-hidden /> This plate is on the wanted list
              </span>
            </div>
          )}
        </dl>
      </div>
    </div>
  );
}

/** Small marker used in tables and lists. */
export function VehicleThumb({ ev, size = 38 }: { ev: VehicleEvent; size?: number }) {
  return (
    <span
      className="relative shrink-0 overflow-hidden rounded-md border border-line bg-surface-3"
      style={{ height: size, width: Math.round(size * 1.45) }}
      aria-hidden
    >
      <img
        src={vehicleStill(ev.vehicleClass)}
        alt=""
        onError={hideBrokenImage}
        loading="lazy"
        className="absolute inset-0 h-full w-full object-cover"
      />
      {ev.watchlistMatch && (
        <Badge tone="danger" className="absolute bottom-0.5 right-0.5 px-1 py-0 text-[9px]">
          W
        </Badge>
      )}
    </span>
  );
}

export { Images };
