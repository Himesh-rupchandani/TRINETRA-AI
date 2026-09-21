import { useState } from 'react';
import { ExternalLink, ImageOff, ScanLine } from 'lucide-react';
import { plateProgressLabel } from '@/lib/liveDetections';
import { apiAssetUrl } from '@/services/api';
import type { LiveAnprSnapshot, LivePhoto } from '@/services/liveAnprService';
import type { Camera, VehicleEvent } from '@/types';
import { formatTime, formatVideoOffset, prettyVehicleClass } from '@/lib/utils';
import { EvidencePanel } from '@/components/vehicle/EvidencePanel';
import { EmptyState } from '@/components/common/Panel';

/** Actual detection crops, available even when OCR is pending/unreadable. */
export function LivePhotoEvidence({ camera, snapshot, selected, latestSaved }: {
  camera: Camera;
  snapshot: LiveAnprSnapshot | null;
  selected: VehicleEvent | null;
  latestSaved: VehicleEvent | null;
}) {
  if (selected) return <EvidencePanel event={selected} dense />;
  const current = snapshot?.camera_id.toLowerCase() === camera.id.toLowerCase() ? snapshot : null;
  const photos = current?.photos ?? [];
  if (!photos.length) {
    return latestSaved ? (
      <>
        <p className="border-b border-line px-4 py-2 text-2xs text-ink-muted">Last saved capture · new detection photos will appear here automatically.</p>
        <EvidencePanel event={latestSaved} dense />
      </>
    ) : (
      <EmptyState icon={ScanLine} title="Waiting for a vehicle"
        detail={current?.reason ?? 'Play the camera with plate detection on. The actual vehicle photo appears automatically — even before its plate is readable.'} />
    );
  }
  return (
    <div className="space-y-3 p-3" data-testid="live-photo-evidence">
      <p className="text-2xs leading-relaxed text-ink-muted">
        Latest captured vehicles · auto-updating. These are camera crops, not stock photos.
      </p>
      {(current?.status === 'UNAVAILABLE' || current?.status === 'ERROR') && current.reason && (
        <p role="status" className="rounded border border-degraded/30 bg-degraded/10 p-2 text-2xs text-degraded">{current.reason}</p>
      )}
      <div className="grid gap-2 sm:grid-cols-3 xl:grid-cols-1">
        {photos.map((photo) => <DetectionPhoto key={photo.track_id} photo={photo} status={current?.status} recorded={camera.streamType === 'FILE'} />)}
      </div>
      <p className="text-[10px] leading-relaxed text-ink-faint">
        Temporary detection previews. Confirmed plate sightings and their saved evidence remain in the Vehicle Log.
      </p>
    </div>
  );
}

function DetectionPhoto({ photo, recorded, status }: { photo: LivePhoto; recorded: boolean; status?: LiveAnprSnapshot['status'] }) {
  const imageUrl = apiAssetUrl(photo.image_path);
  const [failedUrl, setFailedUrl] = useState<string | null>(null);
  const [failedCrop, setFailedCrop] = useState<string | null>(null);
  const cropUrl = photo.plate_image_path ? apiAssetUrl(photo.plate_image_path) : null;
  const failed = failedUrl === imageUrl;
  const plate = photo.plate_number;
  return (
    <article className="overflow-hidden rounded border border-line bg-surface-1" data-capture-id={photo.id}>
      <div className="flex flex-col sm:flex-row sm:items-center">
        <a href={imageUrl} target="_blank" rel="noreferrer" className="relative block min-w-0 bg-black sm:w-[48%] sm:shrink-0" aria-label={`Open captured ${prettyVehicleClass(photo.class_name)} photo`}>
          {failed ? (
            <div className="grid h-32 place-items-center p-2 text-center text-2xs text-white/70">
              <ImageOff size={18} aria-hidden /> Capture expired · waiting for the next photo
            </div>
          ) : (
            <img key={imageUrl} src={imageUrl} alt={`Detected ${prettyVehicleClass(photo.class_name)}${plate ? ` · ${plate}` : ' · plate not read'}`}
              className="h-36 w-full object-contain sm:h-32" decoding="async" onError={() => setFailedUrl(imageUrl)} />
          )}
          <ExternalLink size={11} className="absolute bottom-1 right-1 text-white" aria-hidden />
        </a>
        <div className="min-w-0 space-y-1.5 p-2.5">
          <p className="text-2xs font-semibold text-ink">{prettyVehicleClass(photo.class_name)} · Track {photo.track_id}</p>
          <p className={plate ? 'break-all font-mono text-xs font-bold text-ink' : 'text-2xs text-ink-muted'}>{plate || plateProgressLabel(photo, status)}</p>
          {photo.plate_status === 'LOW_CONFIDENCE' && <p className="text-2xs font-semibold text-degraded">Verify read</p>}
          {photo.plate_confidence != null && <p className="text-[10px] text-ink-muted">{Math.round(photo.plate_confidence * 100)}% OCR</p>}
          <p className="font-mono text-[10px] text-ink-faint">Captured {formatTime(photo.captured_at)}</p>
          <p className="text-[10px] font-medium text-ink-muted">
            {recorded ? 'Recorded video' : 'Camera capture'}
            {recorded && photo.media_time != null ? ` · ${formatVideoOffset(photo.media_time)}` : ''}
          </p>
          {cropUrl && <details className="text-[10px] text-ink-muted">
            <summary className="cursor-pointer">Show area scanned for text</summary>
            {failedCrop === cropUrl ? <p>Scan crop unavailable or expired</p> : <a href={cropUrl} target="_blank" rel="noreferrer">
              <img key={cropUrl} src={cropUrl} alt="Actual area scanned by OCR" className="mt-1 h-14 w-full rounded bg-black object-contain" loading="lazy" decoding="async" onError={() => setFailedCrop(cropUrl)} />
            </a>}
            <p>{photo.ocr_region_source === 'heuristic' ? 'Fallback search area · verify any read' : 'Detector-proposed crop · not proof of a correct read'}</p>
          </details>}
          {photo.event_id != null && <p className="text-[10px] text-online">Plate linked to Vehicle Log</p>}
        </div>
      </div>
    </article>
  );
}
