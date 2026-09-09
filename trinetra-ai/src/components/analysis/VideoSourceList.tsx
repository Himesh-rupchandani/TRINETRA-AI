import { useState } from 'react';
import { Cctv, Clapperboard, FileVideo, HardDriveDownload, Trash2 } from 'lucide-react';
import { Panel, EmptyState } from '@/components/common/Panel';
import { Modal } from '@/components/common/Modal';
import { cn } from '@/lib/utils';
import {
  analysisAnnotatedVideoUrl,
  type AnalysisVideo,
  type VideoStatus,
} from '@/services/videoAnalysisService';

const TONE: Record<VideoStatus, string> = {
  PENDING: 'border-line bg-surface-3 text-ink-muted',
  DOWNLOADING: 'border-brand/40 bg-brand/10 text-brand',
  READY: 'border-line bg-surface-3 text-ink-muted',
  QUEUED: 'border-degraded/45 bg-degraded/10 text-degraded',
  PROCESSING: 'border-brand/40 bg-brand/10 text-brand',
  DONE: 'border-online/45 bg-online/10 text-online',
  FAILED: 'border-critical/45 bg-critical/10 text-critical',
};

const LABEL: Record<VideoStatus, string> = {
  PENDING: 'Pending',
  DOWNLOADING: 'Downloading',
  READY: 'Ready to analyse',
  QUEUED: 'Queued',
  PROCESSING: 'Analysing',
  DONE: 'Analysed',
  FAILED: 'Failed',
};

function StatusCell({ v }: { v: AnalysisVideo }) {
  const busy =
    v.status === 'PROCESSING' || v.status === 'QUEUED' || v.status === 'DOWNLOADING';
  return (
    <div className="min-w-[132px]">
      <span className={cn('chip border', TONE[v.status])}>
        {LABEL[v.status]}
        {busy && v.progressPct > 0 ? ` ${v.progressPct.toFixed(0)}%` : busy ? '…' : ''}
      </span>
      {busy && (
        <span className="mt-1.5 flex items-center gap-1.5">
          <span className="h-1 flex-1 overflow-hidden rounded-full bg-surface-3" aria-hidden>
            <span
              className="block h-full rounded-full bg-brand transition-[width]"
              style={{ width: `${Math.min(100, Math.max(2, v.progressPct))}%` }}
            />
          </span>
          <span className="font-mono text-2xs tabular-nums text-ink-faint">
            {v.progressPct.toFixed(0)}%
          </span>
        </span>
      )}
      {v.error && (
        <span className="mt-1 block max-w-[260px] whitespace-normal text-2xs leading-snug text-critical/90">
          {v.error}
        </span>
      )}
    </div>
  );
}

/** The list of videos added to this analysis run + their live processing state. */
export function VideoSourceList({
  videos,
  onRemove,
  removing,
}: {
  videos: AnalysisVideo[];
  onRemove: (videoId: string) => void;
  removing: string | null;
}) {
  const [playing, setPlaying] = useState<AnalysisVideo | null>(null);
  const done = videos.filter((v) => v.status === 'DONE').length;

  return (
    <Panel
      title={`Videos in this analysis — ${videos.length}`}
      icon={Cctv}
      actions={
        <span className="chip border-line bg-surface-3 text-ink-muted">
          {done} / {videos.length} analysed
        </span>
      }
    >
      {videos.length === 0 ? (
        <EmptyState
          icon={FileVideo}
          title="No videos added yet"
          detail="Upload local CCTV videos or paste a shared Google Drive link above, then start the analysis."
        />
      ) : (
        <ul className="divide-y divide-line/60">
          {videos.map((v) => {
            const busy =
              v.status === 'PROCESSING' || v.status === 'QUEUED' || v.status === 'DOWNLOADING';
            return (
              <li
                key={v.videoId}
                className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-2 px-4 py-3 transition-colors hover:bg-surface-2/60 sm:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)_auto]"
              >
                {/* Camera + source */}
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="plate truncate text-xs text-ink">{v.cameraId}</span>
                    <span className="inline-flex shrink-0 items-center gap-1 text-2xs text-ink-faint">
                      {v.sourceType === 'GDRIVE' ? (
                        <HardDriveDownload size={11} aria-hidden />
                      ) : (
                        <FileVideo size={11} aria-hidden />
                      )}
                      {v.sourceType === 'GDRIVE' ? 'Drive' : 'Upload'}
                    </span>
                  </div>
                  <span className="mt-0.5 block truncate text-2xs text-ink-muted" title={v.sourceName}>
                    {v.sourceName}
                  </span>
                  <span className="block text-2xs text-ink-faint">
                    {v.width && v.height ? `${v.width}×${v.height}` : '—'}
                    {v.fps ? ` · ${Math.round(v.fps)} fps` : ''}
                    {v.durationLabel ? ` · ${v.durationLabel}` : ''}
                  </span>
                </div>

                {/* Status + progress */}
                <div className="order-3 sm:order-none">
                  <StatusCell v={v} />
                </div>

                {/* Actions */}
                <div className="order-2 flex items-center gap-1.5 self-start sm:self-center">
                  {v.annotatedAvailable && (
                    <button
                      type="button"
                      className="btn-ghost btn-xs text-brand"
                      onClick={() => setPlaying(v)}
                      title="Play the AI-annotated output video"
                    >
                      <Clapperboard size={11} aria-hidden /> AI video
                    </button>
                  )}
                  <button
                    type="button"
                    className="btn-ghost btn-xs"
                    onClick={() => onRemove(v.videoId)}
                    disabled={busy || removing === v.videoId}
                    aria-label={`Remove ${v.cameraId}`}
                  >
                    <Trash2 size={11} aria-hidden /> Remove
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
      )}

      <Modal
        open={playing !== null}
        onClose={() => setPlaying(null)}
        title={`AI-annotated video — ${playing?.cameraId ?? ''}`}
        subtitle={playing?.sourceName}
        size="lg"
      >
        {playing && (
          <video
            key={playing.videoId}
            src={analysisAnnotatedVideoUrl(playing.videoId)}
            controls
            autoPlay
            className="max-h-[70vh] w-full rounded-md border border-line bg-black"
          />
        )}
      </Modal>
    </Panel>
  );
}
