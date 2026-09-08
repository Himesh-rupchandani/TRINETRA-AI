import { memo, useMemo } from 'react';
import { Link } from 'react-router-dom';
import { Activity, Car, MapPin, Maximize2, Video } from 'lucide-react';
import type { Camera } from '@/types';
import { StatusChip } from '@/components/common/Chips';
import { cn, formatTime, relativeTime } from '@/lib/utils';
import { config } from '@/lib/config';
import { cameraStill, hideBrokenImage } from '@/utils/mediaAssets';

interface Props {
  camera: Camera;
  onView?: (camera: Camera) => void;
  compact?: boolean;
  selected?: boolean;
  variant?: 'card' | 'list';
}

/**
 * Registry card. Deliberately does NOT mount a stream — feeds are only
 * loaded when an operator explicitly opens one (see performance notes).
 * In demo mode a clearly-labelled synthetic preview is shown instead.
 */
export const CameraCard = memo(function CameraCard({ camera, onView, compact, selected, variant = 'card' }: Props) {
  const preview = useMemo(
    () => (config.useMocks ? cameraStill(camera.id) : null),
    [camera.id],
  );

  if (variant === 'list') {
    return (
      <Link
        to={`/cameras/${camera.id}`}
        className={cn(
          'flex items-center gap-3.5 rounded-lg border border-line bg-surface-1 p-3 transition duration-150 hover:border-line-strong hover:bg-surface-2/50 active:scale-[0.99]',
          selected && 'border-brand/40 ring-1 ring-brand/20',
        )}
      >
        <span className="relative grid h-12 w-[76px] shrink-0 place-items-center overflow-hidden rounded-md border border-line bg-surface-2 text-ink-faint">
          <Video size={16} aria-hidden />
          {preview && (
            <img
              src={preview}
              alt=""
              onError={hideBrokenImage}
              className="absolute inset-0 h-full w-full object-cover"
              loading="lazy"
            />
          )}
        </span>
        <div className="min-w-0 flex-1">
          <p className="truncate font-mono text-xs font-semibold text-ink">{camera.name}</p>
          <p className="mt-1 flex items-center gap-1 truncate text-2xs text-ink-faint">
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
        'panel card-interactive group flex flex-col overflow-hidden hover:border-line-strong',
        selected && 'border-brand/40 ring-1 ring-brand/20',
      )}
    >
      {!compact && (
        <div className="relative">
          <div className="grid aspect-video w-full place-items-center border-b border-line bg-surface-2 text-ink-faint">
            <Video size={18} aria-hidden />
          </div>
          {preview && (
            <img
              src={preview}
              alt=""
              onError={hideBrokenImage}
              className="absolute inset-0 aspect-video w-full border-b border-line object-cover"
              loading="lazy"
            />
          )}
          {preview && (
            <span className="absolute bottom-2 right-2 rounded bg-black/60 px-1.5 py-0.5 font-mono text-[9px] font-semibold tracking-wider text-white/85">
              DEMO
            </span>
          )}
        </div>
      )}

      <div className="flex items-start justify-between gap-3 px-5 py-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <Video size={14} className="shrink-0 text-ink-faint" aria-hidden />
            <h3 className="truncate font-mono text-sm font-semibold text-ink">{camera.name}</h3>
          </div>
          <p className="mt-1 flex items-center gap-1 truncate text-2xs text-ink-muted">
            <MapPin size={10} className="shrink-0" aria-hidden />
            {camera.location}
          </p>
        </div>
        <StatusChip status={camera.status} />
      </div>

      {!compact && (
        <dl className="grid grid-cols-2 gap-x-4 gap-y-2.5 px-5 pb-4 text-2xs">
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

      <div className="mt-auto flex flex-wrap items-center justify-between gap-x-3 gap-y-2 border-t border-line px-5 py-3.5">
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
