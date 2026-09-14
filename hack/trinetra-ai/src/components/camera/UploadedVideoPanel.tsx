import { useEffect, useState } from 'react';
import { FileVideo, RefreshCcw, ScanLine } from 'lucide-react';
import { Panel, EmptyState } from '@/components/common/Panel';
import { PlateLink, ConfidenceBar } from '@/components/common/Links';
import { uploadService, type UploadedVideoDetail } from '@/services/uploadService';
import { cn, formatVideoOffset, prettyVehicleClass } from '@/lib/utils';

const JOB_TONE: Record<string, string> = {
  IDLE: 'border-line bg-surface-3 text-ink-muted',
  QUEUED: 'border-degraded/45 bg-degraded/10 text-degraded',
  PROCESSING: 'border-brand/40 bg-brand/10 text-brand',
  DONE: 'border-online/45 bg-online/10 text-online',
  FAILED: 'border-critical/45 bg-critical/10 text-critical',
};

const JOB_LABEL: Record<string, string> = {
  IDLE: 'Not processed',
  QUEUED: 'Queued',
  PROCESSING: 'Detecting vehicles…',
  DONE: 'Detection complete',
  FAILED: 'Detection failed',
};

/**
 * Detection status + number-plate results for a manually-uploaded CCTV video.
 * Renders nothing when the camera is not an uploaded video.
 */
export function UploadedVideoPanel({ cameraId }: { cameraId: string }) {
  const [detail, setDetail] = useState<UploadedVideoDetail | null>(null);
  const [missing, setMissing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);

  useEffect(() => {
    let cancelled = false;
    uploadService
      .detail(cameraId)
      .then((d) => {
        if (!cancelled) {
          setDetail(d);
          setError(null);
        }
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        const msg = e instanceof Error ? e.message : 'Request failed';
        // Not an uploaded video (e.g. a live/demo file camera): stay hidden.
        if (/not found/i.test(msg)) setMissing(true);
        else setError(msg);
      });
    return () => {
      cancelled = true;
    };
  }, [cameraId]);

  // Poll while a detection job is running (upload auto-starts one).
  const jobStatus = detail?.jobStatus;
  useEffect(() => {
    if (jobStatus !== 'QUEUED' && jobStatus !== 'PROCESSING') return;
    let cancelled = false;
    const timer = setInterval(() => {
      uploadService
        .detail(cameraId)
        .then((d) => {
          if (!cancelled) setDetail(d);
        })
        .catch(() => undefined);
    }, 2000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [cameraId, jobStatus]);

  if (missing) return null;

  const run = async () => {
    setRunning(true);
    setError(null);
    try {
      await uploadService.process(cameraId);
      const next = await uploadService.detail(cameraId);
      setDetail(next);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Could not start detection');
    } finally {
      setRunning(false);
    }
  };

  const busy = detail?.jobStatus === 'QUEUED' || detail?.jobStatus === 'PROCESSING';

  return (
    <Panel
      title="Uploaded video analysis"
      icon={FileVideo}
      actions={
        <>
          {detail && (
            <span className={cn('chip border', JOB_TONE[detail.jobStatus] ?? JOB_TONE.IDLE)}>
              {JOB_LABEL[detail.jobStatus] ?? detail.jobStatus}
            </span>
          )}
          <button type="button" className="btn-ghost btn-xs" onClick={run} disabled={running || busy}>
            <RefreshCcw size={11} aria-hidden /> {running || busy ? 'Detecting…' : 'Run detection'}
          </button>
        </>
      }
    >
      {error && !detail ? (
        <p className="px-4 py-6 text-2xs text-critical" role="alert">
          {error}
        </p>
      ) : !detail ? (
        <p className="px-4 py-6 text-2xs text-ink-faint">Loading video analysis…</p>
      ) : (
        <div>
          <div className="flex flex-wrap items-center gap-x-6 gap-y-2 border-b border-line/60 px-4 py-3">
            <span className="font-mono text-xs text-ink-muted">{detail.videoFile}</span>
            <span className="text-2xs text-ink-faint">
              <span className="font-mono text-ink-muted">{detail.framesProcessed}</span>
              {' / '}
              <span className="font-mono text-ink-muted">{detail.framesTotal || '—'}</span> frames
            </span>
            <span className="text-2xs text-ink-faint">
              <span className="font-mono text-ink-muted">{detail.vehiclesSeen}</span> vehicles
            </span>
            <span className="text-2xs text-ink-faint">
              <span className="font-mono text-ink-muted">{detail.platesRead}</span> plates read
            </span>
            {busy && (
              <span className="flex min-w-[140px] flex-1 items-center gap-2">
                <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-surface-3" aria-hidden>
                  <span
                    className="block h-full rounded-full bg-brand transition-[width]"
                    style={{ width: `${Math.min(100, Math.max(0, detail.progressPct))}%` }}
                  />
                </span>
                <span className="font-mono text-2xs tabular-nums text-ink-muted">
                  {detail.progressPct.toFixed(0)}%
                </span>
              </span>
            )}
          </div>

          {detail.note && (
            <p className="border-b border-line/60 px-4 py-2.5 text-2xs leading-relaxed text-ink-muted">
              {detail.note}
            </p>
          )}
          {detail.jobError && (
            <p className="border-b border-line/60 px-4 py-2.5 text-2xs text-critical" role="alert">
              {detail.jobError}
            </p>
          )}

          {detail.recentPlates.length === 0 ? (
            <EmptyState
              icon={ScanLine}
              title={busy ? 'Detection running' : 'No number plates yet'}
              detail={
                busy
                  ? 'Vehicles and plates appear here as the video is analysed.'
                  : 'No plates were read from this video. Vehicles without a readable plate still appear in the log below as detections.'
              }
            />
          ) : (
            <div className="max-h-[320px] overflow-auto">
              <table className="data-table">
                <thead>
                  <tr>
                    <th scope="col">Video time</th>
                    <th scope="col">Plate</th>
                    <th scope="col">Vehicle type</th>
                    <th scope="col">Plate match</th>
                    <th scope="col">Track</th>
                  </tr>
                </thead>
                <tbody>
                  {detail.recentPlates.map((e) => (
                    <tr key={e.id}>
                      <td className="font-mono tabular-nums text-ink">
                        {e.videoOffsetSec != null ? formatVideoOffset(e.videoOffsetSec) : '—'}
                      </td>
                      <td>
                        {e.plate ? (
                          <PlateLink plate={e.plate} size="xs" />
                        ) : (
                          <span className="text-2xs text-ink-faint">Unknown</span>
                        )}
                      </td>
                      <td className="text-ink-muted">{prettyVehicleClass(e.vehicleClass)}</td>
                      <td>
                        <ConfidenceBar value={e.plateConfidence} />
                      </td>
                      <td className="font-mono text-2xs text-ink-faint">
                        {e.vehicleId != null ? `V-${String(e.vehicleId).padStart(3, '0')}` : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </Panel>
  );
}
