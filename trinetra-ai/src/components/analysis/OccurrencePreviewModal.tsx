import { useRef, useState } from 'react';
import { Clock, Film, ImageOff, Play, ScanLine } from 'lucide-react';
import { Modal } from '@/components/common/Modal';
import { KeyValue } from '@/components/common/Panel';
import { cn, formatDateTime, formatPct, prettyPlate, prettyVehicleClass } from '@/lib/utils';
import { analysisVideoUrl, evidenceUrl } from '@/services/videoAnalysisService';
import type { PlateOccurrence } from '@/services/videoAnalysisService';

/**
 * Large preview of one matching frame: the stored annotated screenshot, the
 * full detection metadata, and — because the analysed video is streamed by
 * the backend — a player that jumps straight to the moment of the detection.
 */
export function OccurrencePreviewModal({
  occurrence,
  onClose,
}: {
  occurrence: PlateOccurrence | null;
  onClose: () => void;
}) {
  // Transient view state is keyed by the opened occurrence, so switching
  // frames resets it during render — no effect cascade needed.
  const [view, setView] = useState({ id: -1, playing: false, frameFailed: false, videoFailed: false });
  const videoRef = useRef<HTMLVideoElement>(null);

  if (!occurrence) return null;
  const occ = occurrence;
  const v = view.id === occ.event_id
    ? view
    : { id: occ.event_id, playing: false, frameFailed: false, videoFailed: false };
  const patch = (p: Partial<typeof v>) => setView({ ...v, ...p });

  const frameSrc = evidenceUrl(occ.frame_ref) ?? evidenceUrl(occ.evidence_ref);
  const canPlay = Boolean(occ.video_id) && !v.videoFailed;

  return (
    <Modal
      open
      onClose={onClose}
      size="lg"
      title={prettyPlate(occ.plate)}
      subtitle={`${occ.video_name} — detection at ${occ.timestamp}`}
      footer={
        canPlay && !v.playing ? (
          <button type="button" className="btn-primary" onClick={() => patch({ playing: true })}>
            <Play size={13} aria-hidden /> Open video at this time
          </button>
        ) : canPlay && v.playing ? (
          <button type="button" className="btn-ghost" onClick={() => patch({ playing: false })}>
            <ScanLine size={13} aria-hidden /> Back to frame
          </button>
        ) : undefined
      }
    >
      <div className="space-y-4">
        <figure className="overflow-hidden rounded-lg border border-line bg-black">
          {v.playing && occ.video_id ? (
            <video
              ref={videoRef}
              src={analysisVideoUrl(occ.video_id)}
              controls
              autoPlay
              className="aspect-video w-full bg-black"
              onLoadedMetadata={(e) => {
                // Jump straight to the stored moment of the detection.
                const t = occ.timestamp_sec;
                if (t != null && Number.isFinite(e.currentTarget.duration)) {
                  e.currentTarget.currentTime = Math.min(Math.max(0, t), Math.max(0, e.currentTarget.duration - 0.1));
                }
              }}
              onError={() => patch({ videoFailed: true })}
            >
              Your browser cannot play this video.
            </video>
          ) : frameSrc && !v.frameFailed ? (
            <img
              src={frameSrc}
              alt={`Annotated detection frame — ${occ.plate} at ${occ.timestamp} in ${occ.video_name}`}
              className="max-h-[52vh] w-full bg-black object-contain"
              onError={() => patch({ frameFailed: true })}
            />
          ) : (
            <div className="grid aspect-video w-full place-items-center bg-surface-2 text-2xs text-ink-faint">
              <span className="flex items-center gap-1.5">
                <ImageOff size={14} aria-hidden />
                {v.videoFailed && v.playing ? 'The source video could not be loaded' : 'Frame image not available'}
              </span>
            </div>
          )}
          <figcaption className="flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-line bg-surface-1 px-3 py-1.5 text-[10px] text-ink-faint">
            <span className="flex items-center gap-1">
              <Film size={10} aria-hidden /> {occ.video_name}
            </span>
            <span className="flex items-center gap-1 font-mono tabular-nums">
              <Clock size={10} aria-hidden /> {occ.timestamp}
            </span>
            {occ.frame_number != null && <span className="font-mono">frame #{occ.frame_number}</span>}
            {occ.bbox && (
              <span className="font-mono">box [{occ.bbox.map((v) => Math.round(v)).join(', ')}]</span>
            )}
          </figcaption>
        </figure>

        <dl className="grid grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-4">
          <KeyValue label="Number plate">
            <span className="plate text-xs text-ink">{occ.plate}</span>
          </KeyValue>
          <KeyValue label="Timestamp in video">
            <span className="font-mono">{occ.timestamp}</span>
          </KeyValue>
          <KeyValue label="OCR confidence">
            <span className={cn('font-mono', occ.confidence >= 0.8 ? 'text-online' : 'text-degraded')}>
              {formatPct(occ.confidence, 1)}
            </span>
          </KeyValue>
          <KeyValue label="Read status">
            {occ.plate_status === 'HIGH' ? 'Confirmed read' : 'Low confidence — verify'}
          </KeyValue>
          <KeyValue label="Video">{occ.video_name}</KeyValue>
          <KeyValue label="Camera">{occ.camera_label || occ.camera_id}</KeyValue>
          <KeyValue label="Vehicle">{prettyVehicleClass(occ.vehicle_class)}</KeyValue>
          <KeyValue label="Raw OCR">{occ.raw_ocr ?? '—'}</KeyValue>
          <KeyValue label="Frame number">{occ.frame_number ?? '—'}</KeyValue>
          <KeyValue label="Detected at">{formatDateTime(occ.detected_at ?? undefined)}</KeyValue>
        </dl>
      </div>
    </Modal>
  );
}
