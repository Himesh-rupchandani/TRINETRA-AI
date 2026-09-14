import { Cctv, FileVideo, HardDriveDownload, Trash2 } from 'lucide-react';
import { Panel, EmptyState } from '@/components/common/Panel';
import { cn } from '@/lib/utils';
import type { AnalysisVideo, VideoStatus } from '@/services/videoAnalysisService';

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
  PROCESSING: 'Analysing…',
  DONE: 'Analysed',
  FAILED: 'Failed',
};

/** The list of videos added to this analysis run + their live processing state. */
export function VideoSourceList({
  videos,
  onRemove,
  removing,
  rejected = [],
}: {
  videos: AnalysisVideo[];
  onRemove: (videoId: string) => void;
  removing: string | null;
  /**
   * Files from the last upload that could not be registered, with the reason.
   * They are listed here rather than dropped: an operator who picked five
   * clips must be able to account for all five.
   */
  rejected?: Array<{ source_name: string; error: string }>;
}) {
  return (
    <Panel
      title={`Videos in this analysis — ${videos.length}${
        rejected.length ? ` (+${rejected.length} not added)` : ''
      }`}
      icon={Cctv}
      actions={
        <>
          {rejected.length > 0 && (
            <span className="chip border-critical/45 bg-critical/10 text-critical">
              {rejected.length} not added
            </span>
          )}
          <span className="chip border-line bg-surface-3 text-ink-muted">
            {videos.filter((v) => v.status === 'DONE').length} analysed
          </span>
        </>
      }
    >
      {videos.length === 0 && rejected.length === 0 ? (
        <EmptyState
          icon={FileVideo}
          title="No videos added yet"
          detail="Upload local CCTV videos or paste a shared Google Drive link above, then start the analysis."
        />
      ) : (
        <div className="overflow-x-auto">
          {/* No `data-table-page` here: that variant pins the header for
              window-scrolled pages, but Video Analysis scrolls inside its own
              container, where the pinned header landed *below* the rows. The
              plain table keeps Camera/Source/... directly above the data. */}
          <table className="data-table">
            <thead>
              <tr>
                <th scope="col">Camera</th>
                <th scope="col">Source</th>
                <th scope="col">Video</th>
                <th scope="col">Status</th>
                <th scope="col">Vehicles</th>
                <th scope="col">Plates</th>
                <th scope="col" className="text-right">Action</th>
              </tr>
            </thead>
            <tbody>
              {videos.map((v) => {
                const busy = v.status === 'PROCESSING' || v.status === 'QUEUED' || v.status === 'DOWNLOADING';
                return (
                  <tr key={v.videoId}>
                    <td className="plate text-xs text-ink">{v.cameraId}</td>
                    <td>
                      <span className="inline-flex items-center gap-1.5 text-2xs text-ink-muted">
                        {v.sourceType === 'GDRIVE' ? (
                          <HardDriveDownload size={12} aria-hidden />
                        ) : (
                          <FileVideo size={12} aria-hidden />
                        )}
                        {v.sourceType === 'GDRIVE' ? 'Google Drive' : 'Upload'}
                      </span>
                    </td>
                    <td className="max-w-[220px]">
                      <span className="block truncate text-xs text-ink">{v.sourceName}</span>
                      <span className="block text-2xs text-ink-faint">
                        {v.width && v.height ? `${v.width}×${v.height}` : '—'}
                        {v.fps ? ` · ${Math.round(v.fps)} fps` : ''}
                        {v.durationLabel ? ` · ${v.durationLabel}` : ''}
                      </span>
                    </td>
                    <td>
                      <span className={cn('chip border', TONE[v.status])}>{LABEL[v.status]}</span>
                      {busy && (
                        <span className="mt-1 flex items-center gap-1.5">
                          <span className="h-1 w-16 overflow-hidden rounded-full bg-surface-3" aria-hidden>
                            <span
                              className="block h-full rounded-full bg-brand transition-[width]"
                              style={{ width: `${Math.min(100, Math.max(0, v.progressPct))}%` }}
                            />
                          </span>
                          <span className="font-mono text-2xs tabular-nums text-ink-faint">
                            {v.progressPct.toFixed(0)}%
                          </span>
                        </span>
                      )}
                      {v.error && (
                        <span className="mt-1 block max-w-[240px] whitespace-normal text-2xs text-ink-faint">
                          {v.error}
                        </span>
                      )}
                    </td>
                    <td className="font-mono tabular-nums text-ink-muted">{v.vehiclesDetected}</td>
                    <td className="font-mono tabular-nums text-ink-muted">
                      {v.platesRead}
                      {v.unknownPlates > 0 && (
                        <span className="ml-1 text-2xs text-ink-faint">(+{v.unknownPlates} unknown)</span>
                      )}
                    </td>
                    <td className="text-right">
                      <button
                        type="button"
                        className="btn-ghost btn-xs"
                        onClick={() => onRemove(v.videoId)}
                        disabled={busy || removing === v.videoId}
                        aria-label={`Remove ${v.cameraId}`}
                      >
                        <Trash2 size={11} aria-hidden /> Remove
                      </button>
                    </td>
                  </tr>
                );
              })}
              {rejected.map((r) => (
                <tr key={`rejected-${r.source_name}`} className="opacity-90">
                  <td className="plate text-xs text-ink-faint">—</td>
                  <td>
                    <span className="inline-flex items-center gap-1.5 text-2xs text-ink-muted">
                      <FileVideo size={12} aria-hidden />
                      Upload
                    </span>
                  </td>
                  <td className="max-w-[220px]">
                    <span className="block truncate text-xs text-ink">{r.source_name}</span>
                    <span className="block text-2xs text-ink-faint">never registered</span>
                  </td>
                  <td>
                    <span className="chip border border-critical/45 bg-critical/10 text-critical">
                      Not added
                    </span>
                    <span className="mt-1 block max-w-[320px] whitespace-normal text-2xs text-ink-faint">
                      {r.error}
                    </span>
                  </td>
                  <td className="font-mono tabular-nums text-ink-faint">—</td>
                  <td className="font-mono tabular-nums text-ink-faint">—</td>
                  <td />
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}
