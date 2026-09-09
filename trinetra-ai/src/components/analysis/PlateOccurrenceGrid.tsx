import { useState } from 'react';
import { ChevronLeft, ChevronRight, Clock, Film, ImageOff } from 'lucide-react';
import { cn, formatPct } from '@/lib/utils';
import { evidenceUrl } from '@/services/videoAnalysisService';
import type { PlateOccurrence } from '@/services/videoAnalysisService';

/**
 * The frame grid of a plate search: every stored occurrence of the searched
 * plate — the annotated full frame the pipeline saved, its timestamp inside
 * the video, the OCR confidence and the source video. Consecutive frames of
 * the same pass are already collapsed into one occurrence by the tracker, and
 * long result sets are paginated, so the grid stays usable at any scale.
 */

function OccurrenceImage({ occ, className }: { occ: PlateOccurrence; className?: string }) {
  // Full annotated frame first; the vehicle crop is the fallback; a clear
  // placeholder last — a deleted/missing frame must never break the grid.
  const [src, setSrc] = useState<string | null>(evidenceUrl(occ.frame_ref) ?? evidenceUrl(occ.evidence_ref));
  const [failed, setFailed] = useState(false);

  if (failed || !src) {
    return (
      <div className={cn('grid aspect-video w-full place-items-center bg-surface-2', className)}>
        <span className="flex items-center gap-1.5 text-2xs text-ink-faint">
          <ImageOff size={13} aria-hidden /> Frame not available
        </span>
      </div>
    );
  }
  return (
    <img
      src={src}
      alt={`Detection frame — ${occ.plate} at ${occ.timestamp} in ${occ.video_name}`}
      className={cn('aspect-video w-full bg-black object-cover', className)}
      loading="lazy"
      decoding="async"
      onError={() => {
        const crop = evidenceUrl(occ.evidence_ref);
        if (crop && src !== crop) setSrc(crop);
        else setFailed(true);
      }}
    />
  );
}

export function OccurrenceSkeletonGrid({ cards = 6 }: { cards?: number }) {
  return (
    <div className="grid grid-cols-2 gap-3 p-3 sm:grid-cols-3 lg:grid-cols-4" role="status" aria-busy="true">
      {Array.from({ length: cards }).map((_, i) => (
        <div key={i} className="overflow-hidden rounded-lg border border-line" style={{ opacity: 1 - i * 0.1 }}>
          <div className="skeleton aspect-video w-full" />
          <div className="space-y-1.5 p-2">
            <div className="skeleton h-3 w-3/4" />
            <div className="skeleton h-2.5 w-1/2" />
          </div>
        </div>
      ))}
    </div>
  );
}

export function PlateOccurrenceGrid({
  occurrences,
  total,
  page,
  totalPages,
  onPageChange,
  onSelect,
}: {
  occurrences: PlateOccurrence[];
  total: number;
  page: number;
  totalPages: number;
  onPageChange: (page: number) => void;
  onSelect: (occ: PlateOccurrence) => void;
}) {
  const limit = Math.max(1, Math.ceil(total / Math.max(totalPages, 1)));
  const from = total === 0 ? 0 : (page - 1) * limit + 1;
  const to = Math.min(total, page * limit);

  return (
    <div>
      <div className="grid grid-cols-2 gap-3 p-3 sm:grid-cols-3 lg:grid-cols-4">
        {occurrences.map((occ) => (
          <button
            key={occ.event_id}
            type="button"
            onClick={() => onSelect(occ)}
            className="group overflow-hidden rounded-lg border border-line bg-surface-1 text-left transition-colors hover:border-brand/60 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand/50"
            aria-label={`Open detection frame of ${occ.plate} at ${occ.timestamp} in ${occ.video_name}`}
          >
            <div className="relative">
              <OccurrenceImage occ={occ} />
              <span className="pointer-events-none absolute bottom-1.5 left-1.5 flex items-center gap-1 rounded bg-black/70 px-1.5 py-0.5 font-mono text-[10px] tabular-nums text-white">
                <Clock size={9} aria-hidden /> {occ.timestamp}
              </span>
              <span
                className={cn(
                  'pointer-events-none absolute right-1.5 top-1.5 rounded px-1.5 py-0.5 font-mono text-[10px] font-bold tabular-nums',
                  occ.confidence >= 0.8 ? 'bg-online/90 text-slate-950' : 'bg-degraded/90 text-slate-950',
                )}
              >
                {formatPct(occ.confidence)}
              </span>
            </div>
            <div className="space-y-1 p-2">
              <p className="plate truncate text-2xs text-ink">{occ.plate}</p>
              <p className="truncate text-[10px] text-ink-faint" title={occ.video_name}>
                <Film size={9} className="mr-1 inline" aria-hidden />
                {occ.video_name}
                {occ.frame_number != null && <span className="ml-1 font-mono">· f{occ.frame_number}</span>}
              </p>
            </div>
          </button>
        ))}
      </div>

      {totalPages > 1 && (
        <div className="flex flex-wrap items-center justify-between gap-2 border-t border-line px-3 py-2">
          <span className="text-2xs text-ink-faint">
            Showing <span className="font-mono text-ink-muted">{from}–{to}</span> of{' '}
            <span className="font-mono text-ink-muted">{total}</span> occurrences
          </span>
          <span className="flex items-center gap-1.5">
            <button
              type="button"
              className="btn-ghost btn-xs"
              onClick={() => onPageChange(page - 1)}
              disabled={page <= 1}
              aria-label="Previous page"
            >
              <ChevronLeft size={12} aria-hidden /> Prev
            </button>
            <span className="font-mono text-2xs tabular-nums text-ink-muted">
              {page} / {totalPages}
            </span>
            <button
              type="button"
              className="btn-ghost btn-xs"
              onClick={() => onPageChange(page + 1)}
              disabled={page >= totalPages}
              aria-label="Next page"
            >
              Next <ChevronRight size={12} aria-hidden />
            </button>
          </span>
        </div>
      )}
    </div>
  );
}
