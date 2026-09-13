import { Fragment, useCallback, useEffect, useMemo, useState } from 'react';
import { Boxes, Loader2, RefreshCcw } from 'lucide-react';
import { Panel, EmptyState, ErrorState } from '@/components/common/Panel';
import { prettyVehicleClass } from '@/lib/utils';
import {
  videoAnalysisService,
  type AnalysisVideo,
  type VideoDetectionRow,
} from '@/services/videoAnalysisService';

/** One vehicle, followed across the frames it was confirmed in. */
interface TrackRow {
  trackId: number | null;
  frames: VideoDetectionRow[];
  first: VideoDetectionRow;
  last: VideoDetectionRow;
  best: VideoDetectionRow;
  /** Widest box this track ever produced, as a share of the frame. */
  worstAreaPct: number;
}

function fmtPct(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return '—';
  return `${(v <= 1 ? v * 100 : v).toFixed(0)}%`;
}

function areaPct(bbox: [number, number, number, number] | null, w: number, h: number): number {
  if (!bbox || w <= 0 || h <= 0) return 0;
  const [x1, y1, x2, y2] = bbox;
  return (Math.max(0, x2 - x1) * Math.max(0, y2 - y1)) / (w * h) * 100;
}

/**
 * PER-VEHICLE LEDGER for one analysed recording.
 *
 * Rows are grouped by the tracker id the analysis assigned, so one vehicle that
 * the detector confirmed on eight frames is one row, not eight - and every box
 * shown is the model's own rectangle, clipped to the frame and nothing else.
 * The area column is deliberately there: it is how an operator (and a reviewer)
 * can see that boxes are tight instead of taking the drawing on trust.
 */
export function DetectionLedger({ videos }: { videos: AnalysisVideo[] }) {
  const done = useMemo(() => videos.filter((v) => v.status === 'DONE'), [videos]);
  const [videoId, setVideoId] = useState<string>('');
  const [rows, setRows] = useState<VideoDetectionRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState<string | number | null>(null);

  const active = useMemo(
    () => done.find((v) => v.videoId === videoId) ?? done[0],
    [done, videoId],
  );

  const load = useCallback(async () => {
    if (!active) {
      setRows([]);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const page = await videoAnalysisService.detections(active.videoId);
      setRows(page.detections ?? []);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Could not load detections');
      setRows([]);
    } finally {
      setLoading(false);
    }
  }, [active]);

  useEffect(() => {
    void load();
  }, [load]);

  const tracks = useMemo<TrackRow[]>(() => {
    const byKey = new Map<string, VideoDetectionRow[]>();
    for (const r of rows) {
      // Rows without a tracker id are grouped by class only when they are the
      // only row for that frame; otherwise each stays its own row, because
      // inventing a shared identity for two boxes would be exactly the sort of
      // guess this display must not make.
      const key = r.track_id != null ? `t:${r.track_id}` : `f:${r.frame_number}:${r.bbox?.join(',') ?? ''}`;
      const list = byKey.get(key);
      if (list) list.push(r);
      else byKey.set(key, [r]);
    }
    const out: TrackRow[] = [];
    for (const [, frames] of byKey) {
      const sorted = [...frames].sort((a, b) => a.frame_number - b.frame_number);
      const best = sorted.reduce((a, b) =>
        (b.detection_confidence ?? 0) > (a.detection_confidence ?? 0) ? b : a,
      );
      const w = active?.width ?? 0;
      const h = active?.height ?? 0;
      out.push({
        trackId: sorted[0].track_id ?? null,
        frames: sorted,
        first: sorted[0],
        last: sorted[sorted.length - 1],
        best,
        worstAreaPct: Math.max(...sorted.map((f) => areaPct(f.bbox, w, h))),
      });
    }
    return out.sort((a, b) => (b.trackId ?? 1e9) - (a.trackId ?? 1e9));
  }, [rows, active]);

  if (!done.length) return null;

  return (
    <Panel
      title="Detections in this recording"
      icon={Boxes}
      actions={
        <>
          <select
            className="input h-7 max-w-[240px] py-0 text-xs"
            value={active?.videoId ?? ''}
            onChange={(e) => setVideoId(e.target.value)}
            aria-label="Choose an analysed recording"
          >
            {done.map((v) => (
              <option key={v.videoId} value={v.videoId}>
                {v.sourceName || v.cameraId}
              </option>
            ))}
          </select>
          <button type="button" className="btn-ghost btn-xs" onClick={() => void load()} aria-label="Reload">
            {loading ? <Loader2 size={12} className="animate-spin" aria-hidden /> : <RefreshCcw size={12} aria-hidden />}
          </button>
        </>
      }
    >
      {error && (
        <div className="p-4">
          <ErrorState message={error} onRetry={() => void load()} />
        </div>
      )}

      {!error && !loading && !tracks.length && (
        <div className="p-4">
          <EmptyState
            title="No vehicle was detected in this recording"
            detail="The detector confirmed nothing above the confidence threshold on the analysed frames. An empty list here is the honest result — no boxes are drawn that the model did not produce."
          />
        </div>
      )}

      {!error && tracks.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="border-b border-line text-2xs uppercase tracking-wide text-ink-faint">
              <tr>
                <th className="px-4 py-2 font-semibold">Track</th>
                <th className="px-3 py-2 font-semibold">Class</th>
                <th className="px-3 py-2 font-semibold">Confidence</th>
                <th className="px-3 py-2 font-semibold">Frames</th>
                <th className="px-3 py-2 font-semibold">Seen from</th>
                <th className="px-3 py-2 font-semibold">Box size</th>
                <th className="px-3 py-2 font-semibold">Number plate</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line/60">
              {tracks.map((t) => {
                const key = t.trackId ?? `f${t.first.frame_number}`;
                const isOpen = open === key;
                const plate = t.best.plate ?? t.frames.find((f) => f.plate)?.plate ?? null;
                const status = t.best.plate_status
                  ?? t.frames.find((f) => f.plate_status)?.plate_status
                  ?? null;
                return (
                  <Fragment key={key}>
                    <tr
                      className="cursor-pointer hover:bg-surface-2/60"
                      onClick={() => setOpen(isOpen ? null : key)}
                    >
                      <td className="px-4 py-2 font-mono tabular-nums text-ink">
                        {t.trackId != null ? `#${t.trackId}` : <span className="text-ink-faint">untracked</span>}
                      </td>
                      <td className="px-3 py-2 text-ink">{prettyVehicleClass(t.best.vehicle_class)}</td>
                      <td className="px-3 py-2 font-mono tabular-nums text-ink-muted">
                        {fmtPct(t.best.detection_confidence)}
                      </td>
                      <td className="px-3 py-2 font-mono tabular-nums text-ink-muted">{t.frames.length}</td>
                      <td className="px-3 py-2 font-mono tabular-nums text-ink-muted">
                        {t.first.timestamp ?? `f${t.first.frame_number}`}
                        {t.frames.length > 1 ? ` → ${t.last.timestamp ?? `f${t.last.frame_number}`}` : ''}
                      </td>
                      <td className="px-3 py-2 font-mono tabular-nums text-ink-muted">
                        {t.worstAreaPct ? `${t.worstAreaPct.toFixed(1)}% of frame` : '—'}
                      </td>
                      <td className="px-3 py-2">
                        {plate ? (
                          <span className="plate text-xs text-ink">{plate}</span>
                        ) : (
                          <span
                            className="chip border-line bg-surface-3 text-ink-faint"
                            title={
                              status === 'UNKNOWN'
                                ? 'A vehicle was detected here; no plate was legible enough to read. The vehicle is still shown.'
                                : 'The plate stage returned nothing for this vehicle.'
                            }
                          >
                            {status === 'UNKNOWN' ? 'plate unreadable' : 'no plate read'}
                          </span>
                        )}
                      </td>
                    </tr>
                    {isOpen && (
                      <tr className="bg-surface-2/40">
                        <td colSpan={7} className="px-4 py-2">
                          <ul className="space-y-1 font-mono text-2xs text-ink-muted">
                            {t.frames.map((f) => (
                              <li key={f.event_id} className="flex flex-wrap gap-x-4 gap-y-0.5">
                                <span>frame {f.frame_number}</span>
                                <span>{f.timestamp ?? `+${f.video_offset_sec ?? 0}s`}</span>
                                <span>{prettyVehicleClass(f.vehicle_class)} {fmtPct(f.detection_confidence)}</span>
                                <span>
                                  box {f.bbox ? `${Math.round(f.bbox[2] - f.bbox[0])}×${Math.round(f.bbox[3] - f.bbox[1])} px` : '—'}
                                </span>
                                <span>{f.plate ? `plate ${f.plate}` : 'plate —'}</span>
                              </li>
                            ))}
                          </ul>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
          <p className="border-t border-line/60 px-4 py-2 text-2xs text-ink-faint">
            Boxes are the detector&apos;s own coordinates clipped to the frame. {active?.framesAnalyzed ?? 0} frames
            analysed of {active?.framesTotal ?? 0} — a vehicle is listed once per track, not once per frame.
          </p>
        </div>
      )}
    </Panel>
  );
}
