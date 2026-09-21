import { useRef, useState } from 'react';
import { FileVideo, Link2, Loader2, Plus, Trash2, Upload } from 'lucide-react';
import { Panel } from '@/components/common/Panel';
import { videoAnalysisService, type AnalysisVideo } from '@/services/videoAnalysisService';

/**
 * Add videos to a multi-video analysis run — local files and/or shared
 * Google Drive links. Uses the existing TRINETRA form/button styles only.
 */
export function AddVideosPanel({
  batchId,
  onAdded,
  busy,
}: {
  batchId?: string;
  onAdded: (videos: AnalysisVideo[], batchId: string) => void;
  busy: boolean;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [fileErrors, setFileErrors] = useState<Array<{ source_name: string; error: string }>>([]);
  const [progress, setProgress] = useState<{
    fileName: string;
    percentage: number;
    overall: number;
  } | null>(null);

  const [driveUrl, setDriveUrl] = useState('');
  const [driveCameraId, setDriveCameraId] = useState('');
  const [driveBusy, setDriveBusy] = useState(false);
  const [driveMsg, setDriveMsg] = useState<{ tone: 'ok' | 'warn' | 'err'; text: string } | null>(null);

  const pickFiles = (list: FileList | null) => {
    if (!list) return;
    setFiles((prev) => {
      const seen = new Set(prev.map((f) => `${f.name}:${f.size}`));
      const next = [...prev];
      Array.from(list).forEach((f) => {
        if (!seen.has(`${f.name}:${f.size}`)) next.push(f);
      });
      return next;
    });
    setUploadError(null);
  };

  const submitFiles = async () => {
    if (!files.length || uploading) return;
    setUploading(true);
    setUploadError(null);
    setFileErrors([]);
    setProgress({ fileName: files[0]?.name ?? '', percentage: 0, overall: 0 });
    try {
      const res = await videoAnalysisService.uploadFiles(files, {
        batchId,
        onProgress: (p) => {
          setProgress({ fileName: p.fileName, percentage: p.percentage, overall: p.overallPercentage });
        },
      });
      setFiles([]);
      setFileErrors(res.errors);
      onAdded(res.added, res.batchId);
    } catch (e: unknown) {
      setUploadError(e instanceof Error ? e.message : 'Upload failed');
    } finally {
      setUploading(false);
      setProgress(null);
    }
  };

  const checkDrive = async () => {
    if (!driveUrl.trim() || driveBusy) return;
    setDriveBusy(true);
    setDriveMsg(null);
    try {
      const v = await videoAnalysisService.validateDriveLink(driveUrl.trim());
      if (!v.valid) setDriveMsg({ tone: 'err', text: v.reason ?? 'Invalid Google Drive link.' });
      else if (!v.accessible)
        setDriveMsg({ tone: 'warn', text: v.reason ?? 'The file could not be accessed.' });
      else {
        if (!driveCameraId && v.suggestedCameraId) setDriveCameraId(v.suggestedCameraId);
        setDriveMsg({
          tone: 'ok',
          text: `Reachable${v.fileName ? `: ${v.fileName}` : ''}. Ready to add.`,
        });
      }
    } catch (e: unknown) {
      setDriveMsg({ tone: 'err', text: e instanceof Error ? e.message : 'Validation failed' });
    } finally {
      setDriveBusy(false);
    }
  };

  const addDrive = async () => {
    if (!driveUrl.trim() || driveBusy) return;
    setDriveBusy(true);
    setDriveMsg(null);
    try {
      const video = await videoAnalysisService.addDriveVideo(
        driveUrl.trim(),
        driveCameraId.trim() || undefined,
        batchId,
      );
      setDriveUrl('');
      setDriveCameraId('');
      setDriveMsg({ tone: 'ok', text: `Added ${video.sourceName} as ${video.cameraId}.` });
      onAdded([video], video.batchId ?? batchId ?? '');
    } catch (e: unknown) {
      setDriveMsg({ tone: 'err', text: e instanceof Error ? e.message : 'Could not add the link' });
    } finally {
      setDriveBusy(false);
    }
  };

  const msgClass =
    driveMsg?.tone === 'ok'
      ? 'border-online/35 bg-online/10 text-online'
      : driveMsg?.tone === 'warn'
        ? 'border-degraded/40 bg-degraded/10 text-degraded'
        : 'border-critical/30 bg-critical/10 text-critical';

  return (
    <Panel title="Add videos" icon={FileVideo}>
      <div className="grid gap-5 p-4 lg:grid-cols-2">
        {/* --- Local upload --- */}
        <div>
          <p className="label">Option A — Local video files</p>
          <input
            ref={inputRef}
            type="file"
            multiple
            accept="video/*,.mkv,.avi,.mov,.mp4,.webm"
            className="sr-only"
            onChange={(e) => pickFiles(e.target.files)}
          />
          <button
            type="button"
            className="flex w-full items-center gap-3 rounded-xl border border-dashed border-line-strong bg-surface-2/50 px-4 py-5 text-left transition-colors hover:bg-surface-2"
            onClick={() => inputRef.current?.click()}
            disabled={uploading || busy}
          >
            <span className="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-brand/10 text-brand">
              <Upload size={18} aria-hidden />
            </span>
            <span className="min-w-0">
              <span className="block text-sm font-semibold text-ink">
                Choose one or more video files
              </span>
              <span className="block text-2xs text-ink-faint">
                MP4 · AVI · MOV · MKV · WEBM — the filename becomes the camera id (CAM1.mp4 → CAM1)
              </span>
            </span>
          </button>

          {files.length > 0 && (
            <ul className="mt-3 space-y-1.5">
              {files.map((f, i) => (
                <li
                  key={`${f.name}-${i}`}
                  className="flex items-center gap-2 rounded-lg border border-line bg-surface-2/60 px-2.5 py-1.5"
                >
                  <FileVideo size={13} className="shrink-0 text-ink-faint" aria-hidden />
                  <span className="min-w-0 flex-1 truncate text-xs text-ink">{f.name}</span>
                  <span className="shrink-0 font-mono text-2xs text-ink-faint">
                    {(f.size / 1024 / 1024).toFixed(1)} MB
                  </span>
                  <button
                    type="button"
                    className="btn-ghost btn-xs"
                    onClick={() => setFiles((p) => p.filter((_, j) => j !== i))}
                    aria-label={`Remove ${f.name}`}
                  >
                    <Trash2 size={11} aria-hidden />
                  </button>
                </li>
              ))}
            </ul>
          )}

          <button
            type="button"
            className="btn-primary mt-3"
            onClick={submitFiles}
            disabled={!files.length || uploading || busy}
          >
            {uploading ? (
              <>
                <Loader2 size={13} className="animate-spin" aria-hidden /> Uploading…
              </>
            ) : (
              <>
                <Plus size={13} aria-hidden /> Add {files.length || ''} video
                {files.length === 1 ? '' : 's'}
              </>
            )}
          </button>

          {uploading && progress && (
            <div className="mt-3 space-y-2">
              <div className="flex items-center justify-between text-2xs text-ink-muted">
                <span className="truncate pr-2">Uploading {progress.fileName}…</span>
                <span className="font-mono">{progress.overall}%</span>
              </div>
              <div className="h-2 w-full overflow-hidden rounded-full bg-surface-3">
                <div
                  className="h-full bg-brand transition-all duration-200"
                  style={{ width: `${progress.overall}%` }}
                  role="progressbar"
                  aria-valuenow={progress.overall}
                  aria-valuemin={0}
                  aria-valuemax={100}
                />
              </div>
              <p className="text-2xs text-ink-faint">
                Large videos are uploaded in small chunks to bypass hosting limits, so please leave
                this tab open. Processing starts automatically after upload.
              </p>
            </div>
          )}
          {uploadError && (
            <p className="mt-2 rounded-lg border border-critical/30 bg-critical/10 px-3 py-2 text-2xs text-critical" role="alert">
              {uploadError}
            </p>
          )}
          {fileErrors.map((e) => (
            <p key={e.source_name} className="mt-2 rounded-lg border border-degraded/30 bg-degraded/10 px-3 py-2 text-2xs text-degraded">
              {e.source_name}: {e.error}
            </p>
          ))}
        </div>

        {/* --- Google Drive --- */}
        <div>
          <p className="label">Option B — Google Drive link</p>
          <div className="flex gap-2">
            <input
              className="input flex-1"
              placeholder="https://drive.google.com/file/d/FILE_ID/view?usp=sharing"
              value={driveUrl}
              onChange={(e) => {
                setDriveUrl(e.target.value);
                setDriveMsg(null);
              }}
              spellCheck={false}
              autoComplete="off"
            />
            <button
              type="button"
              className="btn-ghost shrink-0"
              onClick={checkDrive}
              disabled={!driveUrl.trim() || driveBusy || busy}
            >
              {driveBusy ? <Loader2 size={13} className="animate-spin" aria-hidden /> : <Link2 size={13} aria-hidden />}
              Check
            </button>
          </div>

          <div className="mt-3 flex gap-2">
            <input
              className="input font-mono uppercase"
              placeholder="Camera id (optional)"
              value={driveCameraId}
              onChange={(e) => setDriveCameraId(e.target.value.toUpperCase().replace(/[^A-Z0-9_-]/g, ''))}
              spellCheck={false}
              autoComplete="off"
            />
            <button
              type="button"
              className="btn-primary shrink-0"
              onClick={addDrive}
              disabled={!driveUrl.trim() || driveBusy || busy}
            >
              <Plus size={13} aria-hidden /> Add link
            </button>
          </div>

          <p className="mt-2 text-2xs leading-relaxed text-ink-faint">
            The file must be shared as <span className="font-semibold text-ink-muted">“Anyone with the
            link — Viewer”</span>. TRINETRA never asks for your Google account or password. Private,
            deleted or non-video links are rejected with the reason shown here.
          </p>

          {driveMsg && (
            <p className={`mt-2 rounded-lg border px-3 py-2 text-2xs ${msgClass}`} role="status">
              {driveMsg.text}
            </p>
          )}
        </div>
      </div>
    </Panel>
  );
}
