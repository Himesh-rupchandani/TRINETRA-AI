import { memo, useMemo } from 'react';
import { Link } from 'react-router-dom';
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
 * Registry camera tile — name, ID, state, last activity and 24 h count.
 * Deliberately does NOT mount a stream: feeds start only when an
 * operator opens one (the WHEP gateway is a shared resource).
 */
export const CameraCard = memo(function CameraCard({ camera, selected, variant = 'card' }: Props) {
  // Demo stills are labelled scenery — mock mode only, never live output.
  const preview = useMemo(() => (config.useMocks ? cameraStill(camera.id) : null), [camera.id]);

  if (variant === 'list') {
    return (
      <Link
        to={`/cameras/${camera.id}`}
        className={cn(
          'flex items-center gap-3.5 rounded-lg border border-transparent p-2.5 transition-colors duration-150',
          'hover:border-line hover:bg-surface-2/70 active:bg-surface-3/60',
          selected && 'border-accent/30 bg-accent-weak/50',
        )}
      >
        <span className="relative grid h-11 w-[72px] shrink-0 place-items-center overflow-hidden rounded-md border border-line bg-surface-2 text-ink-faint">
          {preview ? (
            <img
              src={preview}
              alt=""
              onError={hideBrokenImage}
              className="absolute inset-0 h-full w-full object-cover"
              loading="lazy"
            />
          ) : (
            <span className="mono text-[9px] uppercase tracking-wider">
              {camera.status === 'ONLINE' ? 'feed' : 'off'}
            </span>
          )}
        </span>
        <div className="min-w-0 flex-1">
          <p className="mono truncate text-xs font-semibold text-ink">{camera.name}</p>
          <p className="mono mt-0.5 truncate text-[11px] text-ink-faint">
            {camera.id.toUpperCase()} · {camera.location}
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
        'group flex flex-col overflow-hidden rounded-lg border border-line bg-surface-1',
        'transition-colors duration-150 hover:border-line-strong active:bg-surface-2/60',
        selected && 'border-accent/40 ring-1 ring-accent/20',
      )}
    >
      {/* Frame area — the tile's primary region */}
      <div className="relative border-b border-line bg-surface-2">
        <div className="grid aspect-video w-full place-items-center">
          {preview ? (
            <img
              src={preview}
              alt=""
              onError={hideBrokenImage}
              className="absolute inset-0 aspect-video w-full object-cover"
              loading="lazy"
            />
          ) : (
            <span className="mono flex items-center gap-2 text-[11px] text-ink-faint">
              <span
                className={cn(
                  'h-1.5 w-1.5 rounded-full',
                  camera.status === 'ONLINE' ? 'live-dot bg-online' : camera.status === 'OFFLINE' ? 'bg-offline' : 'bg-warn',
                )}
                aria-hidden
              />
              {camera.status === 'ONLINE' ? 'Feed ready — open to watch' : 'No feed'}
            </span>
          )}
        </div>
        {preview && (
          <span className="absolute bottom-2 left-2 rounded bg-black/60 px-1.5 py-0.5 font-mono text-[9px] font-bold tracking-wider text-amber-200">
            DEMO FRAME
          </span>
        )}
        <span className="absolute bottom-2 right-2">
          <CameraStatusBadge status={camera.status} />
        </span>
      </div>

      {/* Identity */}
      <div className="px-4 pt-3">
        <div className="flex items-baseline justify-between gap-3">
          <h3 className="mono truncate text-[13px] font-semibold text-ink">{camera.name}</h3>
          <span className="mono shrink-0 text-[10px] uppercase tracking-wider text-ink-faint">
            {camera.id.toUpperCase()}
          </span>
        </div>
        <p className="mt-0.5 truncate text-xs text-ink-muted">{camera.location}</p>
      </div>

      {/* Facts */}
      <dl className="grid grid-cols-2 gap-x-4 gap-y-2 px-4 pb-3 pt-3 text-xs">
        <dt className="text-ink-faint">Department</dt>
        <dd className="truncate text-right text-ink-muted">{camera.department ?? '—'}</dd>
        <dt className="text-ink-faint">Format</dt>
        <dd className="mono text-right text-ink-muted">{camera.codec ?? '—'}</dd>
        <dt className="text-ink-faint">Vehicles · 24 h</dt>
        <dd className="mono text-right tabular-nums text-ink">{camera.eventCount24h ?? 0}</dd>
        <dt className="text-ink-faint">Last vehicle</dt>
        <dd className="mono text-right tabular-nums text-ink-muted">
          {camera.lastEventAt ? formatTime(camera.lastEventAt) : '—'}
        </dd>
      </dl>

      <div className="mt-auto flex items-center justify-between border-t border-line px-4 py-2.5">
        <span className="text-[11px] text-ink-faint" title="Time since the last vehicle was recorded">
          {relativeTime(camera.lastEventAt ?? camera.lastSeen)}
        </span>
        <span className="text-xs font-semibold text-accent opacity-0 transition-opacity duration-150 group-hover:opacity-100">
          Open monitor →
        </span>
      </div>
    </Link>
  );
});
