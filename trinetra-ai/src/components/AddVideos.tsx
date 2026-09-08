import { useState } from 'react';
import { FolderOpen, Loader2, UploadCloud } from 'lucide-react';
import { videoAnalysisService } from '@/services/videoAnalysisService';
import { Button } from '@/ui/Button';
import { Modal } from '@/ui/Modal';
import { useToast } from '@/features/system/ToastProvider';

/**
 * Add-source dialog: upload files, or register a shared Google Drive
 * link (validated by the backend, which also proposes the camera the
 * footage most likely belongs to).
 */
export function AddVideos({ onAdded }: { onAdded?: (batchId: string) => void }) {
  const toast = useToast();
  const [mode, setMode] = useState<'none' | 'drive'>('none');
  const [url, setUrl] = useState('');
  const [cameraId, setCameraId] = useState('');
  const [checking, setChecking] = useState(false);
  const [validation, setValidation] = useState<{ ok: boolean; message: string; suggestedCameraId?: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const check = async () => {
    setChecking(true);
    setValidation(null);
    try {
      const res = await videoAnalysisService.validateDriveLink(url);
      if (res.valid) {
        setValidation({
          ok: true,
          message: `Accessible: ${res.fileName ?? 'video'}${res.suggestedCameraId ? ` — looks like ${res.suggestedCameraId.toUpperCase()} footage` : ''}`,
          suggestedCameraId: res.suggestedCameraId,
        });
        if (res.suggestedCameraId && !cameraId) setCameraId(res.suggestedCameraId);
      } else {
        setValidation({ ok: false, message: res.reason ?? 'Link could not be validated.' });
      }
    } catch (e) {
      setValidation({ ok: false, message: e instanceof Error ? e.message : 'Validation failed.' });
    } finally {
      setChecking(false);
    }
  };

  const submit = async () => {
    setBusy(true);
    const batchId = `drive-${Date.now().toString(36)}`;
    try {
      await videoAnalysisService.addDriveVideo(url, cameraId || undefined, batchId);
      toast.success('Drive video queued', 'It will be fetched and processed shortly.');
      setMode('none');
      setUrl('');
      setCameraId('');
      setValidation(null);
      onAdded?.(batchId);
    } catch (e) {
      toast.error('Could not add Drive video', e instanceof Error ? e.message : undefined);
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <div className="flex flex-wrap gap-2.5">
        <Button variant="secondary" onClick={() => setMode('drive')}>
          <FolderOpen size={13} aria-hidden /> Connect Drive folder
        </Button>
        <Button
          variant="secondary"
          onClick={() => document.dispatchEvent(new CustomEvent('trinetra:open-upload'))}
        >
          <UploadCloud size={13} aria-hidden /> Upload files
        </Button>
      </div>

      <Modal
        open={mode === 'drive'}
        onClose={() => setMode('none')}
        title="Add video from Google Drive"
        subtitle="The shared file is fetched by the server and processed like an upload."
        footer={
          <>
            <Button variant="ghost" onClick={() => setMode('none')} disabled={busy}>
              Cancel
            </Button>
            <Button variant="primary" onClick={check} loading={checking} disabled={!url.trim()}>
              Validate link
            </Button>
            <Button
              variant="primary"
              onClick={submit}
              loading={busy}
              disabled={!validation?.ok}
            >
              Add to queue
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <div>
            <label htmlFor="drive-url" className="field-label">
              Shared Drive link
            </label>
            <input
              id="drive-url"
              value={url}
              onChange={(e) => {
                setUrl(e.target.value);
                setValidation(null);
              }}
              placeholder="https://drive.google.com/file/d/…/view"
              className="field"
              type="url"
              inputMode="url"
            />
          </div>
          <div>
            <label htmlFor="drive-camera" className="field-label">
              Camera <span className="font-normal text-ink-faint">(optional — which camera recorded this)</span>
            </label>
            <input
              id="drive-camera"
              value={cameraId}
              onChange={(e) => setCameraId(e.target.value)}
              placeholder="e.g. cam07 — left blank if unknown"
              className="field font-mono uppercase"
            />
          </div>

          {checking && (
            <p className="flex items-center gap-2 text-xs text-ink-muted" role="status">
              <Loader2 size={12} className="animate-spin" aria-hidden /> Checking the link…
            </p>
          )}
          {validation && (
            <p
              role="status"
              className={
                validation.ok
                  ? 'rounded-lg border border-online/25 bg-online/[0.06] px-3.5 py-2.5 text-xs leading-relaxed text-ink'
                  : 'rounded-lg border border-critical/25 bg-critical/[0.05] px-3.5 py-2.5 text-xs leading-relaxed text-ink'
              }
            >
              {validation.message}
            </p>
          )}
        </div>
      </Modal>
    </>
  );
}
