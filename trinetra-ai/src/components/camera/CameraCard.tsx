import { memo } from 'react';
import { Link } from 'react-router-dom';
import { Activity, Car, MapPin, Maximize2, Video } from 'lucide-react';
import type { Camera } from '@/types';
import { StatusChip } from '@/components/common/Chips';
import { CameraPreview } from '@/components/camera/CameraPreview';
import { cn, formatTime, relativeTime } from '@/lib/utils';

interface Props {
  camera: Camera;
  onView?: (camera: Camera) => void;
  compact?: boolean;
  selected?: boolean;
  variant?: 'card' | 'list';
  /**
   * Play this camera on the card. Live preview is the default: the video only
   * starts while the card is on screen (see `useCameraPreview`), so a full
   * registry page does not pull the whole grid through the gateway.
   */
  preview?: boolean;
}

/**
 * Registry card. The media area shows the camera's LIVE picture — WebRTC with
 * an HLS fallback, or the backend's AI detection view when it is offered —
 * instead of the grey camera icon it used to render. It is still not a stream
 * wall: every preview is viewport-gated and released again when the card is
 * scrolled away, and compact/list contexts keep the plain placeholder.
 */
export const CameraCard = memo(function CameraCard({
  camera,
  onView,
  compact,
  selected,
  variant = 'card',
  preview = true,
}: Props) {
  if (variant === 'list') {
    return (
      <Link
        to={`/cameras/${camera.id}`}
        className={cn(
          'flex items-center gap-3 rounded-xl border border-line bg-surface-1 p-2.5 transition-colors hover:border-brand/40 hover:shadow-cardHover enter-up',
          selected && 'border-brand/50 ring-1 ring-brand/20',
        )}
      >
        {/* Rows stay a lightweight icon: a 76px thumbnail is too small to read
            and its player buttons could not be nested inside this link. */}
        <span className="relative grid h-12 w-[76px] shrink-0 place-items-center overflow-hidden rounded-lg border border-line bg-surface-2 text-ink-faint">
          <Video size={16} aria-hidden />
        </span>
        <div className="min-w-0 flex-1">
          <p className="truncate font-mono text-xs font-bold text-ink">{camera.name}</p>
          <p className="mt-0.5 flex items-center gap-1 truncate text-2xs text-ink-faint">
            <MapPin size={10} className="shrink-0" aria-hidden />
            {camera.location}
          </p>
        </div>
        <StatusChip status={camera.status} />
      </Link>
    );
  }

  return (
    <article
      className={cn(
        'panel group enter-up flex flex-col overflow-hidden transition-shadow hover:shadow-[0_14px_34px_-8px_rgb(37_99_235_/_0.32)] hover:ring-2 hover:ring-brand/30',
        selected && 'border-brand/60 ring-1 ring-brand/30',
      )}
    >
      {!compact && (
        /* The media area is the camera itself — live, no click required.
            Navigation stays on the buttons below so the preview's own controls
            (retry / try live) never end up nested inside a link. */
        <div className="relative aspect-video w-full border-b border-line bg-surface-2">
          <CameraPreview camera={camera} enabled={preview} />
        </div>
      )}

      <div className="flex items-start justify-between gap-2.5 px-4 py-3">
        <div className="min-w-0">
          <div className="flex items-center gap-1.5">
            <Video size={14} className="shrink-0 text-ink-faint" aria-hidden />
            <h3 className="truncate font-mono text-sm font-bold text-ink">{camera.name}</h3>
          </div>
          <p className="mt-1 flex items-center gap-1 truncate text-2xs text-ink-muted">
            <MapPin size={10} className="shrink-0" aria-hidden />
            {camera.location}
          </p>
        </div>
        <StatusChip status={camera.status} />
      </div>

      {!compact && (
        <dl className="grid grid-cols-2 gap-x-3 gap-y-2 px-4 pb-3 text-2xs">
          <dt className="text-ink-faint">Department</dt>
          <dd className="truncate text-right text-ink-muted">{camera.department ?? '—'}</dd>
          <dt className="text-ink-faint">Video format</dt>
          <dd className="text-right font-mono text-ink-muted">{camera.codec ?? '—'}</dd>
          <dt className="text-ink-faint">Picture size</dt>
          <dd className="text-right font-mono text-ink-muted">
            {camera.width ? `${camera.width}×${camera.height}` : '—'}
          </dd>
          <dt className="text-ink-faint">Last vehicle</dt>
          <dd className="text-right font-mono text-ink-muted">
            {camera.lastEventAt ? formatTime(camera.lastEventAt) : '—'}
          </dd>
        </dl>
      )}

      <div className="mt-auto flex flex-wrap items-center justify-between gap-x-2.5 gap-y-2 border-t border-line/70 px-4 py-3">
        <span
          className="flex items-center gap-1.5 whitespace-nowrap text-2xs text-ink-faint"
          title="Vehicles seen by this camera in the last 24 hours"
        >
          <Activity size={12} aria-hidden />
          {camera.eventCount24h ?? 0} {(camera.eventCount24h ?? 0) === 1 ? 'vehicle' : 'vehicles'} · {relativeTime(camera.lastEventAt)}
        </span>
        <div className="ml-auto flex items-center gap-2">
          {onView && (
            <button
              type="button"
              className="btn-ghost btn-xs"
              onClick={() => onView(camera)}
              title="Quick look without leaving this page"
            >
              <Maximize2 size={12} aria-hidden /> Quick look
            </button>
          )}
          <Link to={`/cameras/${camera.id}`} className="btn-primary btn-xs">
            <Car size={12} aria-hidden /> Open camera
          </Link>
        </div>
      </div>
    </article>
  );
});
