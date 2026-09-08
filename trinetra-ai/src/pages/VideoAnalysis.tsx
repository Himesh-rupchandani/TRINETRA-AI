import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { CheckCircle2, ChevronRight, CircleAlert, Play, Radar } from 'lucide-react';
import { videoAnalysisService } from '@/services/videoAnalysisService';
import type { AnalysisStatus, AnalysisResults, VehicleRecord } from '@/services/videoAnalysisService';
import { AddVideos } from '@/components/AddVideos';
import { JourneyCard } from '@/components/JourneyCard';
import { PlateSearch } from '@/components/PlateSearch';
import { UploadAnalysisPanel } from '@/components/UploadAnalysisPanel';
import { UploadDialog } from '@/components/UploadDialog';
import { Badge } from '@/ui/Badge';
import { Button, buttonClass } from '@/ui/Button';
import { Card, CardBody, CardHeader, SectionLabel } from '@/ui/Card';
import { EmptyState, KeyVal, LoadingRows } from '@/ui/Feedback';
import { PlateLink } from '@/ui/Links';
import { Tabs } from '@/ui/Tabs';
import { useToast } from '@/features/system/ToastProvider';
import { cn } from '@/lib/utils';

type Tab = 'vehicles' | 'multi' | 'matches';

function confidenceBadge(v: VehicleRecord) {
  const n = (v.best_ocr_confidence ?? 0) * 100;
  if (n >= 92) return <Badge tone="success">{n.toFixed(0)}%</Badge>;
  if (n >= 80) return <Badge tone="warn">{n.toFixed(0)}%</Badge>;
  return <Badge tone="danger">{n.toFixed(0)}%</Badge>;
}

/**
 * Video Analysis studio — offline ANPR runs over uploaded or Drive
 * footage: the processing queue with live progress, then correlated
 * results per vehicle, multi-video journeys and probable OCR matches.
 */
export default function VideoAnalysis() {
  const toast = useToast();
  const [status, setStatus] = useState<AnalysisStatus | null>(null);
  const [results, setResults] = useState<AnalysisResults | null>(null);
  const [resultsLoading, setResultsLoading] = useState(false);
  const [tab, setTab] = useState<Tab>('vehicles');
  const [uploadOpen, setUploadOpen] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);
  const [expanded, setExpanded] = useState<string | null>(null);

  const loadStatus = useCallback(async () => {
    try {
      const s = await videoAnalysisService.status();
      setStatus(s);
    } catch {
      setStatus({ status: 'FAILED', videos: [], totalVideos: 0, completedVideos: 0, progressPct: 0 });
    }
  }, []);

  const loadResults = useCallback(async () => {
    setResultsLoading(true);
    try {
      setResults(await videoAnalysisService.results());
    } catch {
      setResults(null);
    } finally {
      setResultsLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadStatus();
    void loadResults();
    // Open the upload dialog from anywhere on the page
    const open = () => setUploadOpen(true);
    document.addEventListener('trinetra:open-upload', open);
    return () => document.removeEventListener('trinetra:open-upload', open);
  }, [loadStatus, loadResults]);

  // Poll while any job is in flight.
  const moving = (status?.videos ?? []).some((v) => !['DONE', 'FAILED', 'PENDING'].includes(v.status));
  useEffect(() => {
    if (!moving) return;
    const t = setInterval(() => void loadStatus(), 3000);
    return () => clearInterval(t);
  }, [moving, loadStatus]);

  const runAll = async () => {
    try {
      await videoAnalysisService.run();
      toast.success('Analysis started', 'Queue progress is shown below.');
      void loadStatus();
    } catch (e) {
      toast.error('Could not start analysis', e instanceof Error ? e.message : undefined);
    }
  };

  const onUploaded = () => {
    setRefreshKey((k) => k + 1);
    void loadStatus();
  };

  const done = status?.completedVideos ?? 0;
  const total = status?.totalVideos ?? 0;

  const vehicles = useMemo(() => results?.vehicles ?? [], [results]);

  return (
    <div className="p-4 sm:p-6 lg:p-8">
      {/* Header */}
      <header className="flex flex-wrap items-end justify-between gap-4 border-b border-line pb-5">
        <div>
          <h2 className="text-lg font-bold text-ink">Video Analysis</h2>
          <p className="mt-1 max-w-2xl text-[13px] leading-relaxed text-ink-muted">
            Run the plate-recognition engine over recorded footage — uploaded files or a shared
            Drive folder. Every vehicle found is added to the same evidence base as live cameras.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2.5">
          <AddVideos onAdded={onUploaded} />
          <Button variant="primary" onClick={runAll} disabled={(status?.videos.length ?? 0) === 0 || moving}>
            <Play size={13} aria-hidden /> {moving ? 'Analysis running…' : 'Process queue'}
          </Button>
        </div>
      </header>

      <div className="mt-5 grid gap-5 xl:grid-cols-[420px_1fr]">
        {/* Queue column */}
        <div className="flex min-w-0 flex-col gap-5">
          <Card>
            <CardHeader
              title="Processing queue"
              subtitle={total > 0 ? `${done} of ${total} completed` : 'Nothing queued yet'}
              actions={
                total > 0 && (
                  <Badge tone={moving ? 'accent' : done === total ? 'success' : 'neutral'} dot={moving} pulse={moving}>
                    {moving ? `${status?.progressPct ?? 0}%` : done === total ? 'Complete' : 'Idle'}
                  </Badge>
                )
              }
            />
            {status === null ? (
              <LoadingRows label="Reading the queue" rows={2} />
            ) : status.videos.length === 0 ? (
              <EmptyState
                title="No videos queued"
                detail="Upload recordings or connect a Drive folder to begin."
                action={
                  <Button variant="primary" onClick={() => setUploadOpen(true)}>
                    Upload videos
                  </Button>
                }
              />
            ) : (
              <CardBody>
                <UploadAnalysisPanel refreshKey={refreshKey} />
              </CardBody>
            )}
          </Card>

          <Card>
            <CardHeader title="Find a plate in the footage" subtitle="Search across everything processed so far" />
            <CardBody className="p-5">
              <PlateSearch onResult={(found, plate) => toast[found ? 'success' : 'info'](found ? `Opening ${plate}` : 'Not in analysed videos', undefined)} />
            </CardBody>
          </Card>

          {results && (
            <Card>
              <CardHeader title="Corpus" subtitle="What the engine has processed" />
              <CardBody className="grid grid-cols-2 gap-x-4 gap-y-4 p-5">
                <KeyVal label="Videos processed">{results.total_videos}</KeyVal>
                <KeyVal label="Vehicle sightings">{results.total_sightings.toLocaleString('en-IN')}</KeyVal>
                <KeyVal label="Unique plates">{results.unique_plates}</KeyVal>
                <KeyVal label="Unreadable reads">{results.unreadable_sightings}</KeyVal>
              </CardBody>
            </Card>
          )}
        </div>

        {/* Results column */}
        <div className="min-w-0">
          <Card className="min-h-[480px]">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-5 pt-1">
              <Tabs
                value={tab}
                onChange={setTab}
                items={[
                  { value: 'vehicles', label: 'Vehicles', count: results?.unique_plates },
                  { value: 'multi', label: 'Multi-video journeys', count: results?.multi_video_vehicles?.length },
                  { value: 'matches', label: 'Probable matches', count: results?.possible_matches?.length },
                ]}
                className="border-b-0"
              />
              {resultsLoading && <span className="pb-2 text-xs text-ink-faint">Refreshing…</span>}
            </div>

            {resultsLoading && !results ? (
              <LoadingRows label="Correlating results" rows={6} />
            ) : !results || results.total_sightings === 0 ? (
              <EmptyState
                icon={Radar}
                title="No processed footage yet"
                detail="Queue videos on the left and run the analysis — recognised vehicles will be listed here."
              />
            ) : tab === 'vehicles' ? (
              <ul className="divide-y divide-line/70">
                {vehicles.map((v) => {
                  const open = expanded === v.plate;
                  return (
                    <li key={v.plate}>
                      <button
                        type="button"
                        onClick={() => setExpanded(open ? null : v.plate)}
                        aria-expanded={open}
                        className="flex w-full flex-wrap items-center gap-x-4 gap-y-1.5 px-5 py-3.5 text-left transition-colors hover:bg-surface-2/60"
                      >
                        <ChevronRight
                          size={14}
                          className={cn('shrink-0 text-ink-faint transition-transform duration-200', open && 'rotate-90')}
                          aria-hidden
                        />
                        <PlateLink plate={v.plate} size="sm" pretty className="w-36 shrink-0" />
                        {confidenceBadge(v)}
                        <span className="mono text-xs text-ink-faint">
                          {v.video_count} video{v.video_count > 1 ? 's' : ''} · {v.total_detections} sightings
                        </span>
                        <span className="ml-auto hidden text-[11px] text-ink-faint sm:block">
                          last seen {new Date(v.last_seen.timestamp).toLocaleString('en-IN', { dateStyle: 'short', timeStyle: 'short' })}
                        </span>
                      </button>
                      {open && (
                        <div className="border-t border-line/70 bg-surface-2/40 px-5 py-4">
                          <SectionLabel>Trail through the footage</SectionLabel>
                          <ol className="mt-2.5 space-y-2">
                            {v.history.map((h, i) => (
                              <li key={i} className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5 text-xs">
                                <span className="mono w-14 shrink-0 text-ink-faint">
                                  {new Date(h.timestamp).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                                </span>
                                <span className="mono font-semibold text-ink">
                                  {(h.camera_label ?? h.camera_id).toUpperCase()}
                                </span>
                                <span className="text-ink-muted">
                                  plate {(h.ocr_confidence * 100).toFixed(0)}% · {h.plate_status === 'HIGH' ? 'read cleanly' : h.plate_status === 'LOW_CONFIDENCE' ? 'low confidence' : 'unread'}
                                </span>
                                {h.source_name && <span className="mono text-[10.5px] text-ink-faint">{h.source_name}</span>}
                              </li>
                            ))}
                          </ol>
                          <div className="mt-3.5">
                            <Link to={`/vehicles/${v.plate}`} className={buttonClass('secondary', 'xs')}>
                              Open city-wide case file
                            </Link>
                          </div>
                        </div>
                      )}
                    </li>
                  );
                })}
              </ul>
            ) : tab === 'multi' ? (
              <JourneyCard vehicles={results.multi_video_vehicles ?? []} />
            ) : (
              <div className="divide-y divide-line/70">
                {(results.possible_matches ?? []).length === 0 ? (
                  <EmptyState
                    icon={CheckCircle2}
                    title="No ambiguous reads"
                    detail="Every plate was read with confidence — nothing needs a human second opinion."
                  />
                ) : (
                  (results.possible_matches ?? []).map((m, i) => (
                    <div key={`${m.plate_a}-${m.plate_b}-${i}`} className="px-5 py-4">
                      <div className="flex flex-wrap items-center gap-3">
                        <PlateLink plate={m.plate_a} size="sm" />
                        <span className="text-xs text-ink-faint">vs</span>
                        <PlateLink plate={m.plate_b} size="sm" />
                        <Badge tone="warn">
                          <CircleAlert size={10} aria-hidden /> {m.differing_characters} char difference
                        </Badge>
                      </div>
                      <p className="mt-2 text-xs leading-relaxed text-ink-muted">{m.note}</p>
                      <p className="mono mt-1.5 text-[11px] text-ink-faint">
                        Both appeared in: {(m.combined_cameras ?? []).map((c) => c.toUpperCase()).join(', ')}
                      </p>
                    </div>
                  ))
                )}
              </div>
            )}
          </Card>
        </div>
      </div>

      <UploadDialog open={uploadOpen} onClose={() => setUploadOpen(false)} onUploaded={onUploaded} />
    </div>
  );
}
