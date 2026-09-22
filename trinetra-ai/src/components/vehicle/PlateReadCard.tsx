import { useCallback, useEffect, useRef, useState } from 'react';
import { AlertCircle, ArrowRight, Play, ScanLine, ShieldCheck, ShieldQuestion, X } from 'lucide-react';
import type { VehicleEvent } from '@/types';
import { cn, formatVideoOffset, prettyPlate } from '@/lib/utils';
import { sourceVideoUrl } from '@/lib/sourceVideo';
import { ConfidenceBar } from '@/components/common/Links';

/**
 * What the ANPR pipeline actually did with this plate — raw OCR string, the
 * normalised read it became, the reliability label, and the two separate
 * confidences (OCR vs vehicle detector).
 *
 * It replaces the old "ANPR crop" slot, which was a dead black box for every
 * uploaded / analysed video: those flows store one vehicle crop per track and
 * never write a plate sidecar (see `evidencePaths`), so `plateCropUrl` only
 * exists for live-camera evidence and demo frames — which is still shown here
 * when present.
 */

/** Wording for the OCR reliability label; an absent status renders nothing. */
const READ_STATUS: Record<string, { label: string; className: string; note: string }> = {
  HIGH: {
    label: 'Trusted read',
    className: 'border-online/45 bg-online/10 text-online',
    note: 'Above the trust threshold — usable as-is.',
  },
  LOW_CONFIDENCE: {
    label: 'Needs verification',
    className: 'border-degraded/45 bg-degraded/10 text-degraded',
    note: 'Below the trust threshold — verify the digits before acting on them.',
  },
  UNKNOWN: {
    label: 'No plate read',
    className: 'border-line bg-surface-3 text-ink-faint',
    note: 'Vehicle was detected, the plate was never resolved from it.',
  },
  SIMULATED: {
    label: 'Demo read',
    className: 'border-brand/45 bg-brand/10 text-brand',
    note: 'Synthetic demo data, not a real sighting.',
  },
};

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-2">
      <dt className="kv-label shrink-0">{label}</dt>
      <dd className="min-w-0 text-right">{children}</dd>
    </div>
  );
}

export function PlateReadCard({ event, className }: { event: VehicleEvent; className?: string }) {
  const crop = event.evidence?.plateCropUrl;
  const [cropFailed, setCropFailed] = useState(false);
  const raw = event.plateRaw?.trim() ?? '';
  const read = prettyPlate(event.plate || '');
  const status = event.plateStatus ? READ_STATUS[event.plateStatus] : undefined;
  const provenance = [
    event.vehicleId != null ? `track ${event.vehicleId}` : '',
    event.frameNumber != null ? `frame ${event.frameNumber}` : '',
    event.videoOffsetSec != null ? formatVideoOffset(event.videoOffsetSec) : '',
  ].filter(Boolean);

  return (
    <figure className={cn('overflow-hidden rounded border border-line bg-surface-1', className)}>
      {crop && !cropFailed ? (
        <img
          key={crop}
          src={crop}
          alt={`Plate crop for ${read || 'unidentified vehicle'}`}
          className="h-20 w-full bg-black object-contain"
          loading="lazy"
          decoding="async"
          onError={() => setCropFailed(true)}
        />
      ) : crop ? (
        <div className="grid h-20 place-items-center gap-1 bg-surface-2 p-2 text-center">
          <p className="plate px-1 text-xs font-bold tracking-widest text-ink">{read}</p>
          <p className="text-[10px] text-ink-faint">Plate crop file is gone from the evidence folder.</p>
          <button type="button" className="text-[10px] underline" onClick={() => setCropFailed(false)}>
            Retry crop
          </button>
        </div>
      ) : null}

      <dl className="flex flex-col gap-1.5 px-3 py-2 text-2xs">
        <Row label="Raw OCR">
          {raw ? (
            <span className="flex items-center justify-end gap-1.5" title="Exactly what the OCR engine returned">
              <span className="truncate font-mono text-ink-muted">{raw}</span>
              {raw !== read && (
                <>
                  <ArrowRight size={10} className="shrink-0 text-ink-faint" aria-hidden />
                  <span className="plate shrink-0 px-1 text-[11px] font-bold tracking-widest text-ink">{read}</span>
                </>
              )}
            </span>
          ) : (
            <span className="text-ink-faint">not stored</span>
          )}
        </Row>

        <Row label="OCR confidence">
          <span className="flex justify-end">
            <ConfidenceBar value={event.plateConfidence} />
          </span>
        </Row>

        {event.vehicleConfidence != null && (
          <Row label="Detector confidence">
            <span className="flex justify-end">
              <ConfidenceBar value={event.vehicleConfidence} />
            </span>
          </Row>
        )}

        {status && (
          <Row label="Read status">
            <span className={cn('chip', status.className)} title={status.note}>
              {status.label}
            </span>
          </Row>
        )}
      </dl>

      <figcaption className="flex items-center justify-between gap-2 border-t border-line bg-surface-1 px-3 py-1.5 text-[10px] text-ink-faint">
        <span className="flex items-center gap-1 truncate">
          <ScanLine size={10} aria-hidden /> {crop ? 'Plate crop + read provenance' : 'Read provenance'}
        </span>
        {provenance.length > 0 && <span className="shrink-0 font-mono">{provenance.join(' · ')}</span>}
      </figcaption>
    </figure>
  );
}

/**
 * The captured frame's source: the stored video, seeked to the exact second of
 * this detection, with the detector box drawn where the model saw the vehicle.
 * The box is recorded in source-frame pixels and the video is letterboxed
 * inside this slot, so it is measured against the painted video area — not
 * against the element box.
 */
export function SourceMomentPlayer({ event, onClose }: { event: VehicleEvent; onClose: () => void }) {
  const src = sourceVideoUrl(event);
  const wrapRef = useRef<HTMLDivElement>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const [box, setBox] = useState<{ left: number; top: number; width: number; height: number } | null>(null);
  const [failed, setFailed] = useState(false);

  const measure = useCallback(() => {
    const video = videoRef.current;
    const wrap = wrapRef.current;
    const bbox = event.bbox;
    if (!video || !wrap || !bbox || !video.videoWidth || !video.videoHeight) return;
    const scale = Math.min(wrap.clientWidth / video.videoWidth, wrap.clientHeight / video.videoHeight);
    const paintedW = video.videoWidth * scale;
    const paintedH = video.videoHeight * scale;
    const [x1, y1, x2, y2] = bbox;
    setBox({
      left: (wrap.clientWidth - paintedW) / 2 + x1 * scale,
      top: (wrap.clientHeight - paintedH) / 2 + y1 * scale,
      width: Math.max(6, (x2 - x1) * scale),
      height: Math.max(6, (y2 - y1) * scale),
    });
  }, [event.bbox]);

  // The slot resizes with the drawer / modal it sits in.
  useEffect(() => {
    const wrap = wrapRef.current;
    if (!wrap || typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver(measure);
    observer.observe(wrap);
    return () => observer.disconnect();
  }, [measure]);

  return (
    <div ref={wrapRef} className="relative aspect-video w-full bg-black">
      {failed ? (
        <div className="grid h-full place-items-center gap-2 p-4 text-center">
          <AlertCircle size={20} className="text-ink-faint" aria-hidden />
          <div>
            <p className="text-2xs font-semibold text-ink-muted">Source video unavailable</p>
            <p className="mt-1 text-[10px] leading-relaxed text-ink-faint">
              {event.videoFile ?? 'This video'} could not be streamed. It may have been deleted after analysis.
            </p>
          </div>
          <button type="button" className="btn-ghost btn-xs" onClick={() => setFailed(false)}>Retry video</button>
        </div>
      ) : (
        <video
          ref={videoRef}
          src={src}
          className="h-full w-full bg-black object-contain"
          controls
          autoPlay
          muted
          playsInline
          preload="metadata"
          onLoadedMetadata={() => {
            const video = videoRef.current;
            if (video && event.videoOffsetSec != null) video.currentTime = Math.max(0, event.videoOffsetSec);
            measure();
          }}
          onSeeked={measure}
          onError={() => setFailed(true)}
        />
      )}

      {box && !failed && (
        <div className="pointer-events-none absolute border-2 border-sky-400/90" style={box} aria-hidden />
      )}

      {/* One strip only: the browser's own controls own the bottom edge. */}
      <div className="absolute inset-x-0 top-0 flex items-center justify-between gap-2 bg-black/55 px-2 py-1 font-mono text-[10px] text-slate-200">
        <span className="flex min-w-0 items-center gap-1.5">
          <Play size={9} aria-hidden />
          <span className="truncate">
            SOURCE MOMENT · {event.videoFile ?? event.cameraId.toUpperCase()}
            {event.frameNumber != null ? ` · frame ${event.frameNumber}` : ''}
          </span>
        </span>
        <span className="flex shrink-0 items-center gap-1.5">
          {event.plate && <span className="plate px-1 text-[10px] font-bold text-white">{prettyPlate(event.plate)}</span>}
          {event.plateStatus === 'LOW_CONFIDENCE' && (
            <span className="chip border-degraded/45 bg-black/70 text-degraded" title="Below the trust threshold — verify the digits against the moving footage.">
              <ShieldQuestion size={10} className="mr-1 inline" aria-hidden /> Verify
            </span>
          )}
          {event.plateStatus === 'HIGH' && (
            <span className="chip border-online/45 bg-black/70 text-online">
              <ShieldCheck size={10} className="mr-1 inline" aria-hidden /> Trusted
            </span>
          )}
          <button
            type="button"
            className="rounded p-0.5 text-slate-300 hover:bg-white/10 hover:text-white"
            onClick={onClose}
            aria-label="Back to the captured frame"
            title="Back to the captured frame"
          >
            <X size={12} aria-hidden />
          </button>
        </span>
      </div>
    </div>
  );
}
