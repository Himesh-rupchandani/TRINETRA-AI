import { memo, useMemo } from 'react';
import { Link } from 'react-router-dom';
import { MapPin, Video } from 'lucide-react';
import type { Camera } from '@/types';
import { CameraStatusBadge } from '@/ui/Badge';
import { cn, formatTime, relativeTime } from '@/lib/utils';
import { config } from '@/lib/config';
import { cameraStill, hideBrokenImage } from '@/utils/mediaAssets';

interface Props {
  camera: Camera;
  selected?: boolean;
  variant?: 'card' | 'list';
}

/**
 * Registry camera. Deliberately does NOT mount a stream — feeds load only
 * when an operator opens one. Demo mode shows a labelled still instead.
 */
export const CameraCard = memo(function CameraCard({ camera, selected, variant = 'card' }: Props) {
  const preview = useMemo(() => (config.useMocks ? cameraStill(camera.id) : null), [camera.id]);

  if (variant === 'list') {
    return (
      <Link
        to={`/cameras/${camera.id}`}
        className={cn(
          'flex items-center gap-3.5 rounded-lg border border-transparent p-2.5 transition-all duration-150',
          'hover:border-line hover:bg-surface-2/70 hover:shadow-xs active:scale-[0.99]',
          selected && 'border-accent/30 bg-accent-weak/50',
        )}
      >
        <span className="relative grid h-11 w-[72px] shrink-0 place-items-center overflow-hidden rounded-md border border-line bg-surface-3 text-ink-faint">
          <Video size={15} aria-hidden />
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
          <p className="mono truncate text-xs font-semibold text-ink">{camera.name}</p>
          <p className="mt-0.5 flex items-center gap-1 truncate text-[11px] text-ink-faint">
            <MapPin size={9} className="shrink-0" aria-hidden />
            {camera.location}
          </p>
        </div>
        <CameraStatusBadge status={camera.status} />
      </Link>
    );
  }

  return (
    <Link
      to={`/cameras/${camera.id}`}
      className={cn(
        'group flex flex-col overflow-hidden rounded-xl border border-line bg-surface-1 shadow-xs',
        'transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md active:translate-y-0 active:scale-[0.995]',
        selected && 'border-accent/40 ring-1 ring-accent/20',
      )}
    >
      <div className="relative">
        <div className="grid aspect-video w-full place-items-center border-b border-line bg-surface-3 text-ink-faint">
          <Video size={18} aria-hidden />
        </div>
        {preview && (
          <img
            src={preview}
            alt=""
            onError={hideBrokenImage}
            className="absolute inset-0 aspect-video w-full object-cover"
            loading="lazy"
          />
        )}
        {preview && (
          <span className="absolute bottom-2 right-2 rounded bg-black/60 px-1.5 py-0.5 font-mono text-[9px] font-bold tracking-wider text-amber-300">
            DEMO
          </span>
        )}
      </div>

      <div className="flex items-start justify-between gap-3 px-4 pt-3.5">
        <div className="min-w-0">
          <h3 className="mono truncate text-[13px] font-semibold text-ink">{camera.name}</h3>
          <p className="mt-0.5 flex items-center gap-1 truncate text-xs text-ink-muted">
            <MapPin size={10} className="shrink-0" aria-hidden />
            {camera.location}
          </p>
        </div>
        <CameraStatusBadge status={camera.status} />
      </div>

      <dl className="grid grid-cols-2 gap-x-4 gap-y-2 px-4 pb-3.5 pt-3 text-xs">
        <dt className="text-ink-faint">Department</dt>
        <dd className="truncate text-right text-ink-muted">{camera.department ?? '—'}</dd>
        <dt className="text-ink-faint">Format</dt>
        <dd className="mono text-right text-ink-muted">{camera.codec ?? '—'}</dd>
        <dt className="text-ink-faint">Resolution</dt>
        <dd className="mono text-right text-ink-muted">
          {camera.width ? `${camera.width}×${camera.height}` : '—'}
        </dd>
        <dt className="text-ink-faint">Last vehicle</dt>
        <dd className="mono text-right text-ink-muted">
          {camera.lastEventAt ? formatTime(camera.lastEventAt) : '—'}
        </dd>
      </dl>

      <div className="mt-auto flex items-center justify-between gap-3 border-t border-line px-4 py-2.5">
        <span
          className="flex items-center gap-1.5 text-[11px] text-ink-faint"
          title="Vehicles seen by this camera in the last 24 hours"
        >
          {camera.eventCount24h ?? 0} vehicles · {relativeTime(camera.lastEventAt)}
        </span>
        <span className="text-xs font-semibold text-accent opacity-0 transition-opacity duration-150 group-hover:opacity-100">
          Open →
        </span>
      </div>
    </Link>
  );
});
