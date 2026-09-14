import { useEffect, useRef, useState } from 'react';
import { FileVideo, Upload } from 'lucide-react';
import { Modal } from '@/components/common/Modal';
import { uploadService } from '@/services/uploadService';

/**
 * Upload one CCTV video file as its own camera (CAM1, CAM2, …).
 * Demo/test footage only — this never connects to a live camera.
 */
export function UploadVideoModal({
  open,
  onClose,
  onUploaded,
}: {
  open: boolean;
  onClose: () => void;
  onUploaded: (cameraId: string) => void;
}) {
  const [cameraId, setCameraId] = useState('');
  const [name, setName] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    setCameraId('');
    setName('');
    setFile(null);
    setError(null);
    setUploading(false);
    uploadService
      .nextCameraId()
      .then((id) => {
        setCameraId(id);
        setName(id);
      })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : 'Request failed'));
  }, [open ]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file || !cameraId.trim() || uploading) return;
    setUploading(true);
    setError(null);
    try {
      const done = await uploadService.upload(file, cameraId.trim().toUpperCase(), name.trim());
      onUploaded(done.cameraId);
      onClose();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Upload failed');
    } finally {
      setUploading(false);
    }
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Upload CCTV Video"
      subtitle="Each video becomes its own camera (CAM1, CAM2, …). Detection starts automatically."
      footer={
        <>
          <button type="button" className="btn-ghost" onClick={onClose} disabled={uploading}>
            Cancel
          </button>
          <button
            type="button"
            className="btn-primary"
            onClick={submit}
            disabled={uploading || !file || !cameraId.trim()}
          >
            {uploading ? (
              'Uploading…'
            ) : (
              <>
                <Upload size={13} aria-hidden /> Upload &amp; run detection
              </>
            )}
          </button>
        </>
      }
    >
      <form onSubmit={submit} className="flex flex-col gap-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label className="label" htmlFor="upload-camera-id">
              Camera ID
            </label>
            <input
              id="upload-camera-id"
              className="input font-mono uppercase"
              value={cameraId}
              onChange={(e) => setCameraId(e.target.value.toUpperCase().replace(/[^A-Z0-9_-]/g, ''))}
              placeholder="CAM1"
              autoComplete="off"
              spellCheck={false}
            />
          </div>
          <div>
            <label className="label" htmlFor="upload-camera-name">
              Display name
            </label>
            <input
              id="upload-camera-name"
              className="input"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="CAM1"
              autoComplete="off"
            />
          </div>
        </div>

        <div>
          <label className="label" htmlFor="upload-video-file">
            CCTV video file
          </label>
          <input
            ref={inputRef}
            id="upload-video-file"
            type="file"
            accept="video/*,.mkv,.avi,.mov,.mp4,.webm"
            className="sr-only"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
          <button
            type="button"
            className="flex w-full items-center gap-3 rounded-xl border border-dashed border-line-strong bg-surface-2/50 px-4 py-5 text-left transition-colors hover:bg-surface-2"
            onClick={() => inputRef.current?.click()}
          >
            <span className="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-brand/10 text-brand">
              <FileVideo size={18} aria-hidden />
            </span>
            <span className="min-w-0">
              {file ? (
                <>
                  <span className="block truncate text-sm font-semibold text-ink">{file.name}</span>
                  <span className="block text-2xs text-ink-faint">
                    {(file.size / 1024 / 1024).toFixed(1)} MB · click to choose a different file
                  </span>
                </>
              ) : (
                <>
                  <span className="block text-sm font-semibold text-ink">Choose a video file</span>
                  <span className="block text-2xs text-ink-faint">MP4 · AVI · MOV · MKV · WEBM</span>
                </>
              )}
            </span>
          </button>
        </div>

        {uploading && (
          <p className="text-xs text-ink-muted" role="status">
            Uploading and starting detection… this can take a while for large videos. You can watch
            the progress on the camera page.
          </p>
        )}
        {error && (
          <p className="rounded-lg border border-critical/30 bg-critical/10 px-3 py-2 text-xs text-critical" role="alert">
            {error}
          </p>
        )}
      </form>
    </Modal>
  );
}
