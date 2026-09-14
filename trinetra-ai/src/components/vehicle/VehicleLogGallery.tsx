import { useState } from 'react';
import { FileImage, ScanLine, Maximize2, BadgeCheck } from 'lucide-react';
import type { VehicleEvent } from '@/types';
import { cn, formatDateTime, prettyVehicleClass } from '@/lib/utils';
import { Modal } from '@/components/common/Modal';
import { EvidencePanel } from './EvidencePanel';
import { isProvidedPlate } from '@/utils/providedPlates';
import { hideBrokenImage } from '@/utils/mediaAssets';

/**
 * VehicleLogGallery — shows ALL provided images for a traced plate in the
 * Vehicle Log / Investigation workspace. When a user searches a number plate,
 * every captured frame + plate crop for that plate is visible here at once,
 * so the operator never has to click row-by-row to verify the evidence.
 *
 * Designed for speed:
 *  - grid of small thumbnails (lazy + async decode)
 *  - full EvidencePanel opens in a modal on click
 *  - synthetic frames render instantly (data-URI, no network)
 *  - real backend URLs use native lazy-loading + caching
 */
export function VehicleLogGallery({
  events,
  title = 'All captured images',
  className,
}: {
  events: VehicleEvent[];
  title?: string;
  className?: string;
}) {
  const [selected, setSelected] = useState<VehicleEvent | null>(null);

  if (!events.length) return null;

  return (
    <>
      <div className={cn('rounded-xl border border-line bg-white', className)}>
        <div className="flex items-center justify-between border-b border-line px-3.5 py-2.5">
          <h4 className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-widest text-ink">
            <FileImage size={13} className="text-brand" aria-hidden />
            {title}
            <span className="chip border-line bg-surface-3 text-ink-muted font-mono text-2xs">
              {events.length} {events.length === 1 ? 'image' : 'images'}
            </span>
          </h4>
          <span className="hidden items-center gap-1 text-2xs text-ink-faint sm:flex">
            <ScanLine size={10} aria-hidden /> Click any image to inspect evidence
          </span>
        </div>

        {/* Grid: fast, no layout shift because every thumb has fixed aspect */}
        <div className="grid gap-3 p-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {events.map((e) => {
            const frame = e.evidence?.frameUrl;
            const crop = e.evidence?.plateCropUrl;
            const hasFrame = Boolean(frame);
            return (
              <button
                key={e.id}
                type="button"
                onClick={() => setSelected(e)}
                className="group relative overflow-hidden rounded-lg border border-line bg-surface-1 text-left transition hover:border-brand/40 hover:shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/40"
                aria-label={`View evidence for ${e.plate} at ${formatDateTime(e.timestamp)}`}
              >
                {/* Frame thumbnail — fixed 16:9 so grid never jumps */}
                <div className="relative aspect-video overflow-hidden bg-black">
                  {hasFrame ? (
                    <img
                      src={frame}
                      alt={`CCTV frame ${e.cameraName ?? e.cameraId} ${formatDateTime(e.timestamp)}`}
                      className="h-full w-full object-cover transition duration-200 group-hover:scale-[1.02]"
                      loading="lazy"
                      decoding="async"
                      onError={hideBrokenImage}
                    />
                  ) : (
                    <div className="grid h-full place-items-center bg-surface-2 text-2xs text-ink-faint">
                      Frame not retained
                    </div>
                  )}
                  {/* Top OSD */}
                  <div className="pointer-events-none absolute inset-x-0 top-0 flex items-center justify-between gap-1 bg-black/55 px-1.5 py-1 font-mono text-[10px] text-slate-200">
                    <span className="truncate">{e.cameraName ?? e.cameraId.toUpperCase()}</span>
                    <span className="shrink-0 tabular-nums">{formatDateTime(e.timestamp).slice(11, 19)}</span>
                  </div>
                  <div className="pointer-events-none absolute bottom-1 right-1 grid h-6 w-6 place-items-center rounded bg-black/60 text-white opacity-0 transition group-hover:opacity-100 group-focus-visible:opacity-100">
                    <Maximize2 size={12} aria-hidden />
                  </div>
                  {isProvidedPlate(e.plate) && !e.evidence?.synthetic ? (
                    <span className="pointer-events-none absolute bottom-1 left-1 flex items-center gap-0.5 rounded bg-emerald-500 px-1 py-0.5 font-mono text-[9px] font-bold text-white">
                      <BadgeCheck size={9} aria-hidden /> PROVIDED
                    </span>
                  ) : e.evidence?.synthetic ? (
                    <span className="pointer-events-none absolute bottom-1 left-1 rounded bg-amber-400 px-1 py-0.5 font-mono text-[9px] font-bold text-slate-900">
                      DEMO
                    </span>
                  ) : null}
                </div>

                {/* Plate crop strip */}
                <div className="flex items-center gap-2 border-t border-line bg-white px-2 py-1.5">
                  <div className="h-9 w-[72px] shrink-0 overflow-hidden rounded border border-line bg-black">
                    {crop ? (
                      <img
                        src={crop}
                        alt={`Plate ${e.plate}`}
                        className="h-full w-full object-contain"
                        loading="lazy"
                        decoding="async"
                        onError={hideBrokenImage}
                      />
                    ) : (
                      <div className="grid h-full place-items-center text-[9px] text-ink-faint">No crop</div>
                    )}
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="plate truncate text-xs leading-none text-ink">{e.plate}</p>
                    <p className="mt-0.5 truncate text-2xs text-ink-faint">
                      {prettyVehicleClass(e.vehicleClass)} · {e.plateConfidence.toFixed(1)}% · {e.location?.slice(0, 28)}
                    </p>
                  </div>
                </div>
              </button>
            );
          })}
        </div>

        <p className="border-t border-line px-3.5 py-2 text-2xs leading-relaxed text-ink-faint">
          All evidence frames for <span className="plate text-ink">{events[0]?.plate}</span> — captured across{' '}
          {new Set(events.map((e) => e.cameraId)).size} cameras. Click any card to open the full-resolution evidence panel with
          frame, plate crop, and chain-of-custody details.
        </p>
      </div>

      <Modal
        open={Boolean(selected)}
        onClose={() => setSelected(null)}
        title={selected ? `Evidence — ${selected.plate}` : ''}
        subtitle={selected ? `${selected.cameraName} · ${selected.location}` : undefined}
      >
        {/* Full evidence view — reuses existing EvidencePanel (no duplication) */}
        {selected && <EvidencePanel event={selected} />}
      </Modal>
    </>
  );
}

/**
 * Compact inline thumb cluster for tables (DetectionTable / Vehicle Log).
 * Shows frame + crop side-by-side in ~48px height, lazy and cached.
 */
export function EvidenceThumbs({
  event,
  size = 'sm',
  onClick,
}: {
  event: VehicleEvent;
  size?: 'sm' | 'md';
  onClick?: () => void;
}) {
  const frame = event.evidence?.frameUrl;
  const crop = event.evidence?.plateCropUrl;
  const cls = size === 'md' ? 'h-[52px] w-[84px]' : 'h-10 w-[68px]';
  const cropCls = size === 'md' ? 'h-[52px] w-[78px]' : 'h-10 w-[64px]';

  if (!frame && !crop) {
    return <span className="font-mono text-2xs text-ink-faint">{event.evidenceRef ?? '—'}</span>;
  }

  return (
    <button
      type="button"
      onClick={onClick}
      className="flex items-center gap-1.5 rounded border border-transparent p-0.5 hover:border-brand/30 hover:bg-surface-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/30"
      aria-label={`View evidence for ${event.plate}`}
    >
      {frame ? (
        <span className={cn('relative shrink-0 overflow-hidden rounded border border-line bg-black', cls)}>
          <img
            src={frame}
            alt=""
            className="h-full w-full object-cover"
            loading="lazy"
            decoding="async"
            onError={hideBrokenImage}
          />
          {event.evidence?.synthetic ? (
            <span className="pointer-events-none absolute bottom-0 left-0 bg-amber-400 px-0.5 py-0.5 font-mono text-[7px] font-bold leading-none text-slate-900">
              DEMO
            </span>
          ) : null}
          {!event.evidence?.synthetic && isProvidedPlate(event.plate) ? (
            <span className="pointer-events-none absolute bottom-0 left-0 bg-emerald-500 px-0.5 py-0.5 font-mono text-[7px] font-bold leading-none text-white">
              PROVIDED
            </span>
          ) : null}
        </span>
      ) : null}
      {crop ? (
        <span className={cn('shrink-0 overflow-hidden rounded border border-line bg-black', cropCls)}>
          <img
            src={crop}
            alt={`Plate ${event.plate}`}
            className="h-full w-full object-contain bg-white"
            loading="lazy"
            decoding="async"
            onError={hideBrokenImage}
          />
        </span>
      ) : null}
    </button>
  );
}
