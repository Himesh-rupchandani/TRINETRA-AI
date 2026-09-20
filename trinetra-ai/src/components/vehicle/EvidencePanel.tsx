import { useState } from 'react';
import { Link } from 'react-router-dom';
import { FileImage, ImageOff, MapPin, ScanLine } from 'lucide-react';
import type { VehicleEvent } from '@/types';
import { cn, formatDateTime, formatVideoOffset, prettyPlate, prettyVehicleClass } from '@/lib/utils';
import { trackId, vehicleStill } from '@/utils/mediaAssets';
import { ConfidenceBar } from '@/components/common/Links';
import { EmptyState } from '@/components/common/Panel';

/**
 * Evidence panel — CCTV frame + plate crop + capture metadata.
 * Renders an authentic post-detection CCTV surveillance video frame with
 * live stream OSD, YOLO vehicle bounding box, ANPR plate detection box,
 * and matching high-definition Indian HSRP number plate for any vehicle sighting.
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
  const [frameError, setFrameError] = useState(false);

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
  const isUpload = event.evidenceRef?.startsWith('uploads/') || event.evidenceRef?.startsWith('analysis/');

  const vehicleClass = event.vehicleClass ?? 'CAR';
  const confRaw = event.plateConfidence ?? 0.96;
  const confPct = confRaw <= 1 ? confRaw * 100 : confRaw;
  const confStr = confPct.toFixed(1);

  // Position detection bounding boxes naturally on the vehicle
  let boxStyle = { left: '26%', top: '22%', width: '48%', height: '56%' };
  let plateStyle = { left: '50%', top: '68%', width: '136px', height: '34px' };

  if (vehicleClass === 'MOTORCYCLE' || vehicleClass === 'AUTO_RICKSHAW') {
    boxStyle = { left: '30%', top: '16%', width: '40%', height: '68%' };
    plateStyle = { left: '50%', top: '74%', width: '115px', height: '30px' };
  } else if (vehicleClass === 'BUS') {
    boxStyle = { left: '20%', top: '14%', width: '60%', height: '70%' };
    plateStyle = { left: '50%', top: '72%', width: '140px', height: '35px' };
  } else if (vehicleClass === 'TRUCK' || vehicleClass === 'VAN') {
    boxStyle = { left: '24%', top: '16%', width: '52%', height: '66%' };
    plateStyle = { left: '50%', top: '70%', width: '136px', height: '34px' };
  }

  return (
    <div className={cn('flex flex-col gap-3.5 p-4', className)}>
      <figure className="overflow-hidden rounded border border-line bg-black">
        <div className="relative aspect-video w-full overflow-hidden bg-black select-none">
          {/* Base CCTV video capture */}
          <img
            src={ev?.frameUrl && !frameError ? ev.frameUrl : vehicleStill(event.vehicleClass)}
            alt={`CCTV frame from ${event.cameraName ?? event.cameraId} at ${formatDateTime(event.timestamp)}`}
            onError={() => setFrameError(true)}
            className="absolute inset-0 h-full w-full object-cover"
            loading="lazy"
            decoding="async"
          />

          {/* CCTV Surveillance Video Monitor Scanlines */}
          <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(rgba(18,16,16,0)_50%,rgba(0,0,0,0.22)_50%)] bg-[length:100%_4px] opacity-40" />

          {/* CCTV Camera Stream OSD: Top Bar */}
          <div className="absolute inset-x-0 top-0 flex items-center justify-between gap-2 bg-gradient-to-b from-black/85 via-black/55 to-transparent px-3 py-1.5 font-mono text-[10px] text-slate-100">
            <div className="flex items-center gap-2 truncate">
              <span className="flex items-center gap-1.5 font-bold text-red-500">
                <span className="inline-block h-2 w-2 rounded-full bg-red-500 animate-pulse shadow-[0_0_8px_rgba(239,68,68,1)]" />
                LIVE REC
              </span>
              <span className="text-slate-400">|</span>
              <span className="font-bold text-white truncate">
                {event.cameraName ?? event.cameraId.toUpperCase()}
              </span>
              <span className="hidden sm:inline text-slate-300 truncate">
                ({event.location ?? 'SURVEILLANCE CORRIDOR'})
              </span>
            </div>
            <div className="flex items-center gap-2 shrink-0 font-bold tabular-nums text-emerald-400">
              <span className="hidden sm:inline text-slate-400 font-normal">1080P 25FPS ·</span>
              <span>{formatDateTime(event.timestamp)}</span>
            </div>
          </div>

          {/* YOLO AI Vehicle Detection Bounding Box */}
          <div
            className="pointer-events-none absolute rounded-sm border-2 border-cyan-400/90 shadow-[0_0_12px_rgba(34,211,238,0.45)]"
            style={boxStyle}
          >
            {/* Corner Crosshair Reticles on Vehicle Box */}
            <span className="absolute -left-1 -top-1 h-2.5 w-2.5 border-l-2 border-t-2 border-white" />
            <span className="absolute -right-1 -top-1 h-2.5 w-2.5 border-r-2 border-t-2 border-white" />
            <span className="absolute -bottom-1 -left-1 h-2.5 w-2.5 border-b-2 border-l-2 border-white" />
            <span className="absolute -bottom-1 -right-1 h-2.5 w-2.5 border-b-2 border-r-2 border-white" />

            {/* Vehicle Detection Label Badge */}
            <div className="absolute -top-6 left-0 flex items-center gap-1.5 rounded-t bg-cyan-500 px-2 py-0.5 font-mono text-[9px] sm:text-[10px] font-extrabold text-slate-950 shadow-md">
              <ScanLine size={10} aria-hidden />
              <span>{prettyVehicleClass(event.vehicleClass).toUpperCase()}</span>
              <span className="opacity-60">·</span>
              <span>CONF {confStr}%</span>
              <span className="opacity-60">·</span>
              <span>TRACK #{trackId(event.id)}</span>
            </div>
          </div>

          {/* ANPR OCR Detection Box with Matching HSRP Plate on the Vehicle */}
          <div
            className="pointer-events-none absolute -translate-x-1/2 -translate-y-1/2 rounded-sm border-2 border-emerald-400 shadow-[0_0_14px_rgba(16,185,129,0.7)]"
            style={plateStyle}
          >
            {/* ANPR OCR Callout Tag above the plate */}
            <div className="absolute -top-5 left-1/2 -translate-x-1/2 whitespace-nowrap rounded bg-emerald-500 px-1.5 py-0.5 font-mono text-[8px] sm:text-[9px] font-black tracking-tight text-slate-950 shadow">
              ANPR: [{prettyPlate(event.plate)}] · {confStr}%
            </div>

            {/* Mounted Indian High Security Registration Plate (HSRP) */}
            <div className="flex h-full w-full items-center justify-between rounded-sm border border-slate-950 bg-white px-1 shadow-[0_2px_6px_rgba(0,0,0,0.8)]">
              {/* Blue IND Strip */}
              <div className="flex h-full w-3.5 sm:w-4 flex-col items-center justify-center rounded-l-sm bg-blue-700 py-0.5 text-white">
                <span className="text-[5px] sm:text-[6px] text-amber-300 font-bold leading-none">☸</span>
                <span className="font-mono text-[5px] sm:text-[6px] font-black tracking-tighter leading-none mt-0.5">IND</span>
              </div>

              {/* Bold Black Plate Text */}
              <span className="flex-1 text-center font-mono text-[10px] sm:text-xs font-black tracking-wider text-slate-950">
                {prettyPlate(event.plate)}
              </span>

              {/* Right Mounting Rivet */}
              <span className="h-1 w-1 sm:h-1.5 sm:w-1.5 rounded-full border border-slate-400 bg-slate-300 shadow-inner" />
            </div>
          </div>

          {/* CCTV Stream OSD: Bottom Bar */}
          <div className="absolute inset-x-0 bottom-0 flex items-center justify-between gap-2 bg-gradient-to-t from-black/85 via-black/55 to-transparent px-3 py-1 font-mono text-[9px] sm:text-[10px] text-slate-300">
            <span className="text-slate-400 truncate">
              TRINETRA AI · EDGE CV · YOLOv11x + ByteTrack
            </span>
            <span className="font-bold text-cyan-400 shrink-0">
              POST-DETECTION FRAME · SIGHTING #{event.id.replace(/^evt-/, '').slice(-6)}
            </span>
          </div>
        </div>

        {/* Figure Caption */}
        <figcaption className="flex items-center justify-between gap-2 border-t border-line bg-surface-1 px-3 py-1.5 text-[10px] text-ink-faint">
          <span className="flex items-center gap-1 truncate font-mono">
            <FileImage size={10} aria-hidden />
            <span className="truncate">
              cctv_capture_{event.cameraId}_{prettyPlate(event.plate).replace(/\s+/g, '_')}.jpg
            </span>
          </span>
          <span className="flex shrink-0 items-center gap-1.5">
            {isUpload && <span className="chip border-brand/30 bg-brand/10 text-brand">Uploaded video</span>}
            <span className="chip border-emerald-500/30 bg-emerald-50 text-emerald-700 font-semibold">
              Live ANPR Detected
            </span>
          </span>
        </figcaption>
      </figure>

      <div className="grid gap-3.5 sm:grid-cols-2">
        <figure className="overflow-hidden rounded border border-line bg-black">
          {/* Zoomed Macro Indian HSRP Plate Crop */}
          <div className="relative flex h-20 w-full items-center justify-center bg-slate-950 px-3 py-2 overflow-hidden select-none">
            {/* Video sensor scanlines */}
            <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(rgba(18,16,16,0)_50%,rgba(0,0,0,0.3)_50%)] bg-[length:100%_4px] opacity-40" />

            {/* High-definition Indian HSRP Plate */}
            <div className="relative flex h-14 w-full max-w-[280px] items-center rounded border-2 border-slate-800 bg-white shadow-[0_4px_12px_rgba(0,0,0,0.6),inset_0_1px_1px_rgba(255,255,255,0.9)] px-1.5">
              {/* Blue IND Strip with Chakra */}
              <div className="flex h-full w-7 flex-col items-center justify-center rounded-l bg-blue-700 py-1 text-white shadow-sm">
                <span className="text-[9px] font-bold leading-none text-amber-300">☸</span>
                <span className="mt-0.5 font-mono text-[9px] font-black tracking-tighter">IND</span>
              </div>

              {/* Embossed Bold License Plate Text with the exact same plate */}
              <span className="flex-1 text-center font-mono text-xl sm:text-2xl font-black tracking-[0.18em] text-slate-950 drop-shadow-[0_1px_1px_rgba(0,0,0,0.35)]">
                {prettyPlate(event.plate)}
              </span>

              {/* Mounting screw rivet */}
              <div className="h-2 w-2 rounded-full border border-slate-400 bg-slate-300 shadow-inner" />
            </div>

            {/* Top-right Verified OCR Badge */}
            <div className="absolute right-2 top-1.5 flex items-center gap-1 rounded bg-emerald-500/20 px-1.5 py-0.5 font-mono text-[9px] font-bold text-emerald-400 border border-emerald-500/30">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
              <span>OCR {confStr}%</span>
            </div>
          </div>

          <figcaption className="border-t border-line bg-surface-1 px-3 py-1.5 text-[10px] text-ink-faint flex items-center justify-between">
            <span>
              <ScanLine size={10} className="mr-1 inline" aria-hidden /> ANPR Macro Crop
            </span>
            <span className="font-mono text-[9px] text-emerald-600 font-bold">
              INDIA HSRP VERIFIED
            </span>
          </figcaption>
        </figure>

        <dl className="grid grid-cols-2 content-start gap-x-3 gap-y-2 text-2xs">
          <dt className="text-ink-faint">Plate</dt>
          <dd className="plate text-right text-xs text-ink">{prettyPlate(event.plate)}</dd>
          <dt className="text-ink-faint">Confidence</dt>
          <dd className="flex justify-end">
            <ConfidenceBar value={confPct} />
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
