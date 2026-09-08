import { useEffect, useState } from 'react';
import { AlertCircle, CheckCircle2, Film, Loader2, RefreshCw, Trash2 } from 'lucide-react';
import type { AnalysisVideo } from '@/services/videoAnalysisService';
import { videoAnalysisService } from '@/services/videoAnalysisService';
import { Badge } from '@/ui/Badge';
import { Button } from '@/ui/Button';
import { LoadingRows } from '@/ui/Feedback';
import { useToast } from '@/features/system/ToastProvider';
import { cn } from '@/lib/utils';
import { formatDateTime } from '@/lib/uiHelpers';

/** Poll a loader on an interval while `active` is true. */
function usePoll(fn: () => Promise<void>, ms: number, active: boolean) {
  useEffect(() => {
    if (!active) return;
    const t = setInterval(() => void fn(), ms);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, ms]);
}

const STATUS_TONE: Record<AnalysisVideo['status'], { tone: 'neutral' | 'accent' | 'success' | 'warn' | 'danger'; label: string }> = {
  PENDING: { tone: 'neutral', label: 'Queued' },
  QUEUED: { tone: 'neutral', label: 'Queued' },
  DOWNLOADING: { tone: 'accent', label: 'Fetching' },
  READY: { tone: 'accent', label: 'Ready' },
  PROCESSING: { tone: 'accent', label: 'Processing' },
  DONE: { tone: 'success', label: 'Completed' },
  FAILED: { tone: 'danger', label: 'Failed' },
};

function progressOf(v: AnalysisVideo): number {
  return typeof v.progressPct === 'number' ? v.progressPct : v.status === 'DONE' ? 100 : 0;
}

/**
 * Source list with live processing progress. Polls only while something
 * is still moving; completed sources stay quiet.
 */
export function UploadAnalysisPanel({
  refreshKey,
  className,
}: {
  refreshKey?: number;
  className?: string;
}) {
  const toast = useToast();
  const [videos, setVideos] = useState<AnalysisVideo[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [removing, setRemoving] = useState<string | null>(null);

  const load = async () => {
    try {
      setError(null);
      const status = await videoAnalysisService.status();
      setVideos(status.videos ?? []);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not load the analysis queue.');
    }
  };

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshKey]);

  const moving = (videos ?? []).some(
    (v) => v.status !== 'DONE' && v.status !== 'FAILED' && v.status !== 'PENDING',
  );
  usePoll(load, 3000, moving);

  const remove = async (v: AnalysisVideo) => {
    setRemoving(v.videoId);
    try {
      await videoAnalysisService.remove(v.videoId);
      toast.success('Video removed', v.sourceName);
      void load();
    } catch (e) {
      toast.error('Could not remove video', e instanceof Error ? e.message : undefined);
    } finally {
      setRemoving(null);
    }
  };

  if (videos === null && !error) return <LoadingRows label="Loading analysis queue" rows={3} className={className} />;
  if (error)
    return (
      <div className={cn('flex items-center gap-2.5 px-5 py-6', className)}>
        <AlertCircle size={15} className="shrink-0 text-critical" aria-hidden />
        <p className="text-[13px] text-ink-muted">{error}</p>
        <Button variant="ghost" size="xs" onClick={load} className="ml-auto">
          Retry
        </Button>
      </div>
    );
  if (!videos || videos.length === 0) return null;

  return (
    <ul className={cn('divide-y divide-line/70', className)} aria-label="Videos in the analysis queue">
      {videos.map((v) => {
        const st = STATUS_TONE[v.status] ?? STATUS_TONE.PENDING;
        const pct = progressOf(v);
        const busy = v.status === 'DOWNLOADING' || v.status === 'PROCESSING' || v.status === 'READY' || v.status === 'QUEUED';
        return (
          <li key={v.videoId} className="px-5 py-3.5">
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
              <Film size={14} className={cn('shrink-0', busy ? 'text-accent' : 'text-ink-faint')} aria-hidden />
              <span className="mono min-w-0 flex-1 truncate text-[13px] font-medium text-ink" title={v.sourceName}>
                {v.sourceName}
              </span>
              <Badge tone={st.tone} dot={busy} pulse={busy}>
                {st.label}
              </Badge>
              <span className="mono shrink-0 text-[11px] text-ink-faint">
                {v.durationLabel ?? '—'} · {v.width && v.height ? `${v.width}×${v.height}` : '—'}
              </span>
              <Button
                variant="ghost"
                size="xs"
                onClick={() => remove(v)}
                loading={removing === v.videoId}
                aria-label={`Remove ${v.sourceName}`}
                className="px-1.5"
              >
                <Trash2 size={12} aria-hidden />
              </Button>
            </div>

            {(busy || v.status === 'DONE' || v.status === 'FAILED') && (
              <div className="mt-2.5 flex items-center gap-3">
                <div className="h-1 min-w-0 flex-1 overflow-hidden rounded-full bg-surface-3" aria-hidden>
                  <div
                    className={cn(
                      'h-full rounded-full transition-[width] duration-500',
                      v.status === 'FAILED' ? 'bg-critical' : v.status === 'DONE' ? 'bg-online' : 'bg-accent',
                    )}
                    style={{ width: `${v.status === 'FAILED' ? 100 : pct}%` }}
                  />
                </div>
                <span className="mono shrink-0 text-[11px] tabular-nums text-ink-faint">
                  {busy && (
                    <Loader2 size={10} className="mr-1 inline animate-spin" aria-hidden />
                  )}
                  {v.status === 'FAILED' ? (
                    <span className="text-critical">{v.error ?? 'Processing failed'}</span>
                  ) : (
                    `${pct}%`
                  )}
                </span>
              </div>
            )}

            <p className="mono mt-1.5 text-[11px] text-ink-faint">
              {v.vehiclesDetected} vehicles · {v.platesRead} plates read
              {v.unknownPlates > 0 && ` · ${v.unknownPlates} unreadable`}
              {v.createdAt && ` · added ${formatDateTime(v.createdAt)}`}
            </p>
          </li>
        );
      })}
      {moving && (
        <li className="flex items-center gap-2 px-5 py-2 text-[11px] text-ink-faint">
          <RefreshCw size={10} className="animate-spin" aria-hidden /> Refreshing automatically while jobs run
        </li>
      )}
      {(videos ?? []).every((v) => v.status === 'DONE') && (videos?.length ?? 0) > 0 && (
        <li className="flex items-center gap-2 px-5 py-2 text-[11px] text-ink-faint">
          <CheckCircle2 size={12} className="text-online" aria-hidden /> All queued videos processed
        </li>
      )}
    </ul>
  );
}
