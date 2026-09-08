import { useMemo } from 'react';
import type { VehicleRecord } from '@/services/videoAnalysisService';
import { Link } from 'react-router-dom';
import { ArrowRight } from 'lucide-react';
import { Badge } from '@/ui/Badge';
import { EmptyState } from '@/ui/Feedback';
import { PlateLink } from '@/ui/Links';

/**
 * Vehicles seen across several uploaded videos — the correlation view
 * of the video-analysis tool.
 */
export function JourneyCard({ vehicles }: { vehicles: VehicleRecord[] }) {
  if (!vehicles || vehicles.length === 0) {
    return (
      <EmptyState
        title="No multi-video matches yet"
        detail="When the same plate is recognised in more than one uploaded video, the journey will be assembled here."
      />
    );
  }

  return (
    <ul className="divide-y divide-line/70">
      {vehicles.map((v) => (
        <li key={v.plate} className="px-5 py-3.5 transition-colors hover:bg-surface-2/50">
          <div className="flex flex-wrap items-center gap-2.5">
            <PlateLink plate={v.plate} size="sm" pretty />
            <Badge tone="info">{v.video_count} videos</Badge>
            <span className="mono text-[11px] text-ink-faint">
              {v.total_detections} sightings · {v.sequence_label || v.sequence.length + ' stops'}
            </span>
            <Link
              to={`/vehicles/${v.plate}`}
              className="ml-auto inline-flex items-center gap-1 text-xs font-semibold text-accent transition-all duration-150 hover:gap-1.5 active:scale-[0.98]"
            >
              Open case <ArrowRight size={12} aria-hidden />
            </Link>
          </div>
        </li>
      ))}
    </ul>
  );
}

/** Helper shared by the results panel for possible OCR-mismatch pairs. */
export function PossibleMatchNote({ note }: { note: string }) {
  return <p className="text-xs leading-relaxed text-ink-muted">{note}</p>;
}

export function useJourneySummary(vehicles: VehicleRecord[] | undefined) {
  return useMemo(() => {
    const list = vehicles ?? [];
    return {
      count: list.length,
      sightings: list.reduce((s, v) => s + (v.total_detections ?? 0), 0),
    };
  }, [vehicles]);
}
