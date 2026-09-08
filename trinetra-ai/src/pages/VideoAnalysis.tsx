import { useCallback, useEffect, useRef, useState } from 'react';
import { AlertTriangle, Cctv, Layers, Loader2, Play, RefreshCcw, ScanSearch } from 'lucide-react';
import { PageHeader } from '@/components/layout/PageHeader';
import { Panel, EmptyState, ErrorState } from '@/components/common/Panel';
import { AddVideosPanel } from '@/components/analysis/AddVideosPanel';
import { VideoSourceList } from '@/components/analysis/VideoSourceList';
import { PlateSearchPanel } from '@/components/analysis/PlateSearchPanel';
import { CameraSequence, VehicleJourneyCard } from '@/components/analysis/VehicleJourneyCard';
import {
  videoAnalysisService,
  type AnalysisResults,
  type AnalysisStatus,
} from '@/services/videoAnalysisService';

/**
 * MULTI-VIDEO ANALYSIS — add several CCTV videos (local files or shared
 * Google Drive links), run the existing detection + ANPR pipeline over all of
 * them, and see which number plates appear in more than one video.
 *
 * Everything shown on this page comes from real analysis of the submitted
 * videos. There is no sample/demo path here.
 */
export default function VideoAnalysis() {
  const [status, setStatus] = useState<AnalysisStatus | null>(null);
  const [results, setResults] = useState<AnalysisResults | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [starting, setStarting] = useState(false);
  const [removing, setRemoving] = useState<string | null>(null);
  const [onlyMulti, setOnlyMulti] = useState(false);
  const pollRef = useRef<number | null>(null);

  const refreshStatus = useCallback(async () => {
    const s = await videoAnalysisService.status();
    setStatus(s);
    return s;
  }, []);

  const refreshResults = useCallback(async () => {
    setResults(await videoAnalysisService.results());
  }, []);

  const refreshAll = useCallback(async () => {
    try {
      const s = await refreshStatus();
      if (s.totalVideos > 0) await refreshResults();
      setError(null);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Request failed');
    } finally {
      setLoading(false);
    }
  }, [refreshStatus, refreshResults]);

  useEffect(() => {
    void refreshAll();
  }, [refreshAll]);

  // Poll while any video is being downloaded/queued/processed.
  const busy = status?.status === 'PROCESSING';
  useEffect(() => {
    if (!busy) {
      if (pollRef.current) window.clearInterval(pollRef.current);
      pollRef.current = null;
      return;
    }
    pollRef.current = window.setInterval(() => {
      void (async () => {
        try {
          const s = await refreshStatus();
          if (s.status !== 'PROCESSING') await refreshResults();
        } catch {
          /* transient — the next tick retries */
        }
      })();
    }, 2000);
    return () => {
      if (pollRef.current) window.clearInterval(pollRef.current);
      pollRef.current = null;
    };
  }, [busy, refreshStatus, refreshResults]);

  const videos = status?.videos ?? [];
  const analysable = videos.filter((v) => v.status !== 'PROCESSING' && v.status !== 'QUEUED');

  const startAnalysis = async () => {
    if (starting || !videos.length) return;
    setStarting(true);
    setError(null);
    try {
      await videoAnalysisService.run();
      await refreshStatus();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Could not start the analysis');
    } finally {
      setStarting(false);
    }
  };

  const remove = async (videoId: string) => {
    setRemoving(videoId);
    try {
      await videoAnalysisService.remove(videoId);
      await refreshAll();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Could not remove the video');
    } finally {
      setRemoving(null);
    }
  };

  const shown = onlyMulti ? (results?.multi_video_vehicles ?? []) : (results?.vehicles ?? []);

  return (
    <div className="animate-page-in flex h-full flex-col">
      <PageHeader
        title="Video Analysis"
        icon={ScanSearch}
        tone="purple"
        subtitle="Analyse several CCTV videos together and find the vehicles that appear in more than one."
        actions={
          <>
            <button type="button" className="btn-ghost" onClick={() => void refreshAll()} disabled={loading}>
              <RefreshCcw size={13} aria-hidden /> Refresh
            </button>
            <button
              type="button"
              className="btn-primary"
              onClick={startAnalysis}
              disabled={starting || busy || analysable.length === 0}
            >
              {starting || busy ? (
                <>
                  <Loader2 size={13} className="animate-spin" aria-hidden /> Analysing…
                </>
              ) : (
                <>
                  <Play size={13} aria-hidden /> Start analysis
                </>
              )}
            </button>
          </>
        }
      />

      <div className="min-h-0 flex-1 overflow-auto">
        <div className="mx-auto max-w-6xl space-y-5 p-5 sm:p-6 xl:p-8">
          {error && (
            <div className="panel">
              <ErrorState message={error} onRetry={() => void refreshAll()} />
            </div>
          )}

          <AddVideosPanel
            onAdded={() => void refreshAll()}
            busy={busy}
            batchId={undefined}
          />

          <VideoSourceList videos={videos} onRemove={(id) => void remove(id)} removing={removing} />

          {busy && (
            <div className="panel flex items-center gap-4 px-5 py-4">
              <Loader2 size={15} className="animate-spin text-brand" aria-hidden />
              <span className="text-xs text-ink">
                Processing {status?.completedVideos ?? 0}/{status?.totalVideos ?? 0} videos —{' '}
                <span className="font-mono">{(status?.progressPct ?? 0).toFixed(0)}%</span>
              </span>
              <span className="ml-auto text-2xs text-ink-faint">
                Vehicle detection → tracking → plate detection → OCR → plate matching
              </span>
            </div>
          )}

          {/* --- Cross-video comparison --- */}
          {results && results.total_videos > 0 && (
            <>
              <section className="grid grid-cols-2 gap-5 sm:grid-cols-4">
                <Kpi label="Videos analysed" value={results.total_videos} />
                <Kpi label="Vehicle sightings" value={results.total_sightings} />
                <Kpi label="Unique plates read" value={results.unique_plates} />
                <Kpi
                  label="Plates in 2+ videos"
                  value={results.plates_in_multiple_videos}
                  tone="brand"
                />
              </section>

              <Panel
                title="Cross-video number-plate matching"
                icon={Layers}
                actions={
                  <>
                    <span className="chip border-line bg-surface-3 text-ink-muted">
                      {results.unreadable_sightings} unreadable
                    </span>
                    <button
                      type="button"
                      className={onlyMulti ? 'btn-tint btn-xs' : 'btn-ghost btn-xs'}
                      onClick={() => setOnlyMulti((v) => !v)}
                    >
                      Multi-video only
                    </button>
                  </>
                }
              >
                {shown.length === 0 ? (
                  <EmptyState
                    icon={Cctv}
                    title={onlyMulti ? 'No plate was seen in more than one video' : 'No number plates were read'}
                    detail={
                      onlyMulti
                        ? 'Every plate read so far appears in a single video only. Nothing is invented to fill this list.'
                        : 'The pipeline detected no readable number plate in these videos. Vehicles without a readable plate are still counted as sightings but cannot be matched across videos.'
                    }
                  />
                ) : (
                  <div className="space-y-2 p-3">
                    {shown.map((v) => (
                      <VehicleJourneyCard key={v.plate} record={v} defaultOpen={shown.length === 1} />
                    ))}
                  </div>
                )}
              </Panel>

              {results.possible_matches.length > 0 && (
                <Panel title="Possible matches (uncertain OCR)" icon={AlertTriangle}>
                  <ul className="divide-y divide-line/60">
                    {results.possible_matches.map((m) => (
                      <li key={`${m.plate_a}-${m.plate_b}`} className="px-4 py-3">
                        <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
                          <span className="plate text-xs text-ink">{m.plate_a}</span>
                          <span className="text-2xs text-ink-faint">vs</span>
                          <span className="plate text-xs text-ink">{m.plate_b}</span>
                          <span className="chip border-degraded/40 bg-degraded/10 text-degraded">
                            {m.differing_characters} character{m.differing_characters === 1 ? '' : 's'} differ
                          </span>
                          <CameraSequence cameras={m.combined_cameras} />
                        </div>
                        <p className="mt-1.5 text-2xs leading-relaxed text-ink-faint">{m.note}</p>
                      </li>
                    ))}
                  </ul>
                </Panel>
              )}
            </>
          )}

          <PlateSearchPanel disabled={(results?.unique_plates ?? 0) === 0} />
        </div>
      </div>
    </div>
  );
}

function Kpi({ label, value, tone }: { label: string; value: number; tone?: 'brand' }) {
  return (
    <div className="panel px-4 py-3">
      <p className="kv-label">{label}</p>
      <p
        className={`mt-1 font-mono text-2xl font-bold tabular-nums ${
          tone === 'brand' ? 'text-brand' : 'text-ink'
        }`}
      >
        {value}
      </p>
    </div>
  );
}
