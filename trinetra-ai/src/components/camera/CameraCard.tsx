import { memo, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { Activity, Car, MapPin, Maximize2, Video } from 'lucide-react';
import type { Camera } from '@/types';
import { SourceKindBadge, StatusChip } from '@/components/common/Chips';
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
 * One-frame preview for a tile, never a mounted stream.
 *
 * The backend answers with whatever a live worker already decoded, or with one
 * frame from a recording, and 204 when there is no picture to offer; opening a
 * network stream for a thumbnail is refused there on purpose. So a grid of
 * thirty tiles costs thirty cached JPEG fetches, not thirty ffmpeg sessions.
 * Refresh stops for good the moment a camera proves it has nothing to show -
 * no retry storm against a dead feed - and pauses while the tab is hidden.
 */
const THUMB_REFRESH_MS = 8000;

function useTileSnapshot(camera: Camera): { src: string; onError: () => void } | null {
  const [tick, setTick] = useState(0);
  const [givenUp, setGivenUp] = useState(false);
  const eligible = !config.useMocks && !givenUp && camera.status !== 'NOT_CONFIGURED';
  useEffect(() => {
    if (!eligible) return;
    const timer = window.setInterval(() => {
      if (document.visibilityState === 'visible') setTick((v) => v + 1);
    }, THUMB_REFRESH_MS);
    return () => window.clearInterval(timer);
  }, [eligible]);
  if (!eligible) return null;
  const url = `${config.apiBaseUrl}/cameras/${encodeURIComponent(camera.id)}/snapshot`;
  // the query only breaks the browser's own caching; the route sends no-store
  return { src: `${url}?t=${tick}`, onError: () => setGivenUp(true) };
}

/**
 * Registry card. Deliberately does NOT mount a stream — feeds are only
 * loaded when an operator explicitly opens one (see performance notes). What it
 * does show is the single latest frame, so an operator can pick the right
 * camera from the grid instead of opening thirty of them. In demo mode a
 * clearly-labelled synthetic preview is shown instead.
 */
export const CameraCard = memo(function CameraCard({ camera, onView, compact, selected, variant = 'card' }: Props) {
  const preview = useMemo(
    () => (config.useMocks ? cameraStill(camera.id) : null),
    [camera.id],
  );
  // real mode: the backend's one-frame snapshot; mock mode: the labelled still
  const live = useTileSnapshot(camera);
  const thumb = preview ?? live?.src ?? null;
  const onThumbError = preview ? hideBrokenImage : (live?.onError ?? hideBrokenImage);

  if (variant === 'list') {
    return (
      <Link
        to={`/cameras/${camera.id}`}
        className={cn(
          'flex items-center gap-3 rounded-xl border border-line bg-surface-1 p-2.5 transition-colors hover:border-brand/40 hover:shadow-cardHover enter-up',
          selected && 'border-brand/50 ring-1 ring-brand/20',
        )}
      >
        <span className="relative grid h-12 w-[76px] shrink-0 place-items-center overflow-hidden rounded-lg border border-line bg-surface-2 text-ink-faint">
          <Video size={16} aria-hidden />
          {thumb && (
            <img
              src={thumb}
              alt=""
              onError={onThumbError}
              className="absolute inset-0 h-full w-full object-cover"
              loading="lazy"
            />
          )}
        </span>
        <div className="min-w-0 flex-1">
          <p className="truncate font-mono text-xs font-bold text-ink">{camera.name}</p>
          <p className="mt-0.5 flex items-center gap-1 truncate text-2xs text-ink-faint">
            <MapPin size={10} className="shrink-0" aria-hidden />
            {camera.location}
          </p>
        </div>
        <StatusChip status={camera.status} />
        <SourceKindBadge kind={camera.sourceKind} />
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
        <div className="relative">
          <div className="grid aspect-video w-full place-items-center border-b border-line bg-surface-2 text-ink-faint">
            <Video size={18} aria-hidden />
          </div>
          {thumb && (
            <img
              src={thumb}
              alt={`Latest frame from ${camera.name}`}
              onError={onThumbError}
              className="absolute inset-0 aspect-video w-full border-b border-line object-cover"
              loading="lazy"
            />
          )}
          {preview && (
            <span className="absolute bottom-1.5 right-1.5 rounded bg-black/60 px-1.5 py-0.5 font-mono text-[9px] font-bold tracking-wider text-amber-300">
              DEMO
            </span>
          )}
          {/* A real frame is still a frame: say whether it is live or playback,
              on the image, not only in the card text below it. */}
          {!preview && thumb && camera.sourceKind && (
            <span className="absolute bottom-1.5 left-1.5">
              <SourceKindBadge kind={camera.sourceKind} onDark />
            </span>
          )}
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
