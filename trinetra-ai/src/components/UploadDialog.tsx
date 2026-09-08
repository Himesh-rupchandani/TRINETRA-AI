import { useCallback, useRef, useState } from 'react';
import { FileVideo, UploadCloud } from 'lucide-react';
import { Modal } from '@/ui/Modal';
import { Button } from '@/ui/Button';
import { Badge } from '@/ui/Badge';
import { useToast } from '@/features/system/ToastProvider';
import { uploadService } from '@/services/uploadService';
import { cn } from '@/lib/utils';

/**
 * Video upload dialog with a real drop-zone. Files go to the analysis
 * queue via uploadService.uploadFiles; per-file errors are reported
 * verbatim from the backend.
 */
export function UploadDialog({
  open,
  onClose,
  onUploaded,
}: {
  open: boolean;
  onClose: () => void;
  onUploaded?: (batchId: string) => void;
}) {
  const toast = useToast();
  const inputRef = useRef<HTMLInputElement>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [dragOver, setDragOver] = useState(false);
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState<{ source_name: string; error: string }[]>([]);

  const addFiles = useCallback((incoming: FileList | null) => {
    if (!incoming) return;
    const vids = Array.from(incoming).filter((f) => f.type.startsWith('video/') || /\.(mp4|avi|mkv|mov|webm)$/i.test(f.name));
    if (vids.length < incoming.length) {
      toast.info('Some files were skipped', 'Only video files can be analysed.');
    }
    setFiles((prev) => [...prev, ...vids.filter((v) => !prev.some((p) => p.name === v.name && p.size === v.size))]);
  }, [toast]);

  const submit = async () => {
    if (files.length === 0) return;
    setBusy(true);
    setErrors([]);
    const batchId = `up-${Date.now().toString(36)}`;
    const failures: { source_name: string; error: string }[] = [];
    let added = 0;
    try {
      for (const file of files) {
        try {
          const cameraId = await uploadService.nextCameraId();
          await uploadService.upload(file, cameraId, file.name.replace(/\.[^.]+$/, ''));
          added += 1;
        } catch (e) {
          failures.push({
            source_name: file.name,
            error: e instanceof Error ? e.message : 'Upload rejected',
          });
        }
      }
      setErrors(failures);
      if (added > 0) {
        toast.success(
          `${added} video${added > 1 ? 's' : ''} queued for analysis`,
          'Progress appears in the upload list below.',
        );
        setFiles((prev) => prev.filter((f) => !failures.some((x) => x.source_name === f.name)));
        onUploaded?.(batchId);
        if (failures.length === 0) onClose();
      } else {
        toast.error('No videos could be queued', 'Check the errors listed below.');
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Upload video for analysis"
      subtitle="Recordings are processed by the same ANPR pipeline as live cameras."
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button variant="primary" onClick={submit} loading={busy} disabled={files.length === 0}>
            Queue {files.length > 0 ? `${files.length} video${files.length > 1 ? 's' : ''}` : 'videos'}
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <div
          role="button"
          tabIndex={0}
          aria-label="Choose video files to upload"
          className={cn(
            'flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed px-6 py-10 text-center transition-all duration-150',
            dragOver ? 'border-accent bg-accent-weak/60 scale-[0.99]' : 'border-line-strong/70 hover:border-accent/50 hover:bg-surface-2/60',
          )}
          onClick={() => inputRef.current?.click()}
          onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && inputRef.current?.click()}
          onDragOver={(e) => {
            e.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragOver(false);
            addFiles(e.dataTransfer.files);
          }}
        >
          <span className="grid h-11 w-11 place-items-center rounded-full border border-line bg-surface-2 text-ink-muted">
            <UploadCloud size={18} aria-hidden />
          </span>
          <p className="text-sm font-medium text-ink">Drop video files here or click to browse</p>
          <p className="text-xs text-ink-faint">MP4, AVI, MKV or MOV — several files can be queued together</p>
          <input
            ref={inputRef}
            type="file"
            accept="video/*,.mkv"
            multiple
            className="sr-only"
            onChange={(e) => {
              addFiles(e.target.files);
              e.target.value = '';
            }}
          />
        </div>

        {files.length > 0 && (
          <ul className="divide-y divide-line/70 rounded-xl border border-line" aria-label="Selected files">
            {files.map((f, i) => (
              <li key={`${f.name}-${f.size}`} className="flex items-center gap-3 px-3.5 py-2.5">
                <FileVideo size={15} className="shrink-0 text-ink-faint" aria-hidden />
                <span className="min-w-0 flex-1 truncate text-[13px] text-ink">{f.name}</span>
                <span className="mono shrink-0 text-[11px] text-ink-faint">{(f.size / 1024 / 1024).toFixed(1)} MB</span>
                <button
                  type="button"
                  className="shrink-0 rounded p-1 text-ink-faint transition-colors hover:bg-surface-2 hover:text-critical active:scale-90"
                  onClick={() => setFiles((prev) => prev.filter((_, j) => j !== i))}
                  aria-label={`Remove ${f.name}`}
                >
                  ✕
                </button>
              </li>
            ))}
          </ul>
        )}

        {errors.length > 0 && (
          <div className="rounded-xl border border-critical/25 bg-critical/[0.05] p-3.5" role="alert">
            <p className="text-xs font-semibold text-critical">Some files were rejected:</p>
            <ul className="mt-1.5 space-y-1">
              {errors.map((e) => (
                <li key={e.source_name} className="text-xs text-ink-muted">
                  <span className="font-medium text-ink">{e.source_name}</span> — {e.error}
                </li>
              ))}
            </ul>
          </div>
        )}

        <p className="flex items-center gap-2 text-xs text-ink-faint">
          <Badge tone="info">How it works</Badge>
          Frames are scanned for vehicles, plates are read with OCR, and results appear in this
          tool and in the vehicle log.
        </p>
      </div>
    </Modal>
  );
}
