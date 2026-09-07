import { ArrowRight, Clock, Route, ShieldQuestion } from 'lucide-react';
import { PlateLink } from '@/components/common/Links';
import { cn, prettyVehicleClass } from '@/lib/utils';
import type { VehicleRecord } from '@/services/videoAnalysisService';

function pct(v?: number | null): string {
  if (v == null || Number.isNaN(v)) return '—';
  return `${(v <= 1 ? v * 100 : v).toFixed(0)}%`;
}

/** CAM1 → CAM2 → CAM3, built only from cameras the vehicle was actually seen on. */
export function CameraSequence({ cameras, className }: { cameras: string[]; className?: string }) {
  return (
    <span className={cn('flex flex-wrap items-center gap-1', className)} aria-label="Observed camera sequence">
      {cameras.map((c, i) => (
        <span key={`${c}-${i}`} className="flex items-center gap-1">
          <span className="plate rounded-md border border-brand/30 bg-brand/10 px-1.5 py-0.5 text-2xs text-brand">
            {c}
          </span>
          {i < cameras.length - 1 && <ArrowRight size={12} className="text-ink-faint" aria-hidden />}
        </span>
      ))}
    </span>
  );
}

export function LowConfidenceChip() {
  return (
    <span className="chip border-degraded/45 bg-degraded/10 text-degraded" title="OCR confidence below the trust threshold — verify the evidence crop before acting on it.">
      <ShieldQuestion size={10} aria-hidden /> Low confidence
    </span>
  );
}

/**
 * One vehicle identified across the analysed videos: which videos it appeared
 * in, the observed camera sequence, and its full timestamped history.
 */
export function VehicleJourneyCard({
  record,
  defaultOpen = false,
}: {
  record: VehicleRecord;
  defaultOpen?: boolean;
}) {
  const multi = record.video_count > 1;
  return (
    <details
      className={cn('panel overflow-hidden border-l-4', multi ? 'border-l-brand' : 'border-l-line-strong')}
      open={defaultOpen}
    >
      <summary className="flex cursor-pointer list-none flex-wrap items-center gap-x-5 gap-y-2 px-4 py-3 hover:bg-surface-2">
        <PlateLink plate={record.plate} size="md" />
        <span className="chip border-line bg-surface-3 text-ink-muted">
          Seen in {record.video_count} video{record.video_count === 1 ? '' : 's'}
        </span>
        {record.plate_status !== 'HIGH' && <LowConfidenceChip />}
        <CameraSequence cameras={record.sequence} />
        <span className="ml-auto flex items-center gap-4 text-2xs text-ink-faint">
          <span>
            OCR <span className="font-mono text-ink-muted">{pct(record.best_ocr_confidence)}</span>
          </span>
          <span>
            Detection{' '}
            <span className="font-mono text-ink-muted">{pct(record.best_detection_confidence)}</span>
          </span>
          <span>
            <span className="font-mono text-ink-muted">{record.total_detections}</span> detections
          </span>
        </span>
      </summary>

      <div className="border-t border-line">
        <dl className="grid grid-cols-2 gap-x-6 gap-y-3 px-4 py-3 sm:grid-cols-4">
          <div>
            <dt className="kv-label">Vehicle type</dt>
            <dd className="kv-value">{prettyVehicleClass(record.vehicle_class)}</dd>
          </div>
          <div>
            <dt className="kv-label">First seen</dt>
            <dd className="kv-value font-mono">
              {record.first_seen.camera_id} — {record.first_seen.timestamp}
            </dd>
          </div>
          <div>
            <dt className="kv-label">Last seen</dt>
            <dd className="kv-value font-mono">
              {record.last_seen.camera_id} — {record.last_seen.timestamp}
            </dd>
          </div>
          <div>
            <dt className="kv-label">Raw OCR (best read)</dt>
            <dd className="kv-value font-mono">{record.best_raw_ocr ?? '—'}</dd>
          </div>
        </dl>

        <div className="border-t border-line/60 px-4 py-2">
          <p className="flex items-center gap-1.5 text-2xs font-semibold uppercase tracking-wide text-ink-faint">
            <Route size={11} aria-hidden /> Vehicle history
          </p>
        </div>
        <ol className="divide-y divide-line/60">
          {record.history.map((h) => (
            <li key={`${h.camera_id}-${h.step}`} className="flex flex-wrap items-center gap-x-4 gap-y-1 px-4 py-2.5">
              <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full border border-line bg-surface-3 font-mono text-2xs font-bold text-ink-muted">
                {h.step}
              </span>
              <span className="plate w-[80px] shrink-0 text-xs text-ink">{h.camera_id}</span>
              <span className="flex shrink-0 items-center gap-1 font-mono text-xs tabular-nums text-ink">
                <Clock size={11} className="text-ink-faint" aria-hidden />
                {h.timestamp}
              </span>
              <span className="min-w-0 flex-1 truncate text-2xs text-ink-muted">
                {h.source_name ?? h.camera_label}
              </span>
              <span className="text-2xs text-ink-muted">{prettyVehicleClass(h.vehicle_class)}</span>
              <span className="font-mono text-2xs tabular-nums text-ink-faint">
                OCR {pct(h.ocr_confidence)}
              </span>
              <span className="font-mono text-2xs tabular-nums text-ink-faint">
                {h.detections} det.
              </span>
              {h.plate_status !== 'HIGH' && <LowConfidenceChip />}
            </li>
          ))}
        </ol>
      </div>
    </details>
  );
}
