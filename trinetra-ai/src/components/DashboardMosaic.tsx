import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { CircleDot, VideoOff } from 'lucide-react';
import type { Camera } from '@/types';
import { cameraService } from '@/services/cameraService';
import type { CameraStreamTicket } from '@/types';
import { config } from '@/lib/config';
import { cn, formatTime, relativeTime } from '@/lib/utils';
import { cameraStill, hideBrokenImage } from '@/utils/mediaAssets';

/**
 * Dashboard mosaic tile — the backend's annotated live detection view
 * (MJPEG, real boxes drawn by the CV engine). Falls back honestly:
 * registry still when the preview is unavailable, never a fake feed.
 */
function MosaicTile({ camera }: {
  camera: Camera;
}) {
  const [ticket, setTicket] = useState<CameraStreamTicket | null>(null);
  const [failed, setFailed] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const [source, setSource] = useState<string | null>(null);
  // Stills are demo-mode scenery — never shown as live-camera output.
  const still = config.useMocks ? cameraStill(camera.id) : null;

  useEffect(() => {
    let alive = true;
    setTicket(null);
    setFailed(false);
    setStreaming(false);
    cameraService
      .stream(camera.id)
      .then((t) => {
        if (!alive) return;
        setTicket(t);
        setSource(t.detectionUrl ?? null);
      })
      .catch(() => alive && setFailed(true));
    return () => {
      alive = false;
    };
  }, [camera.id]);

  const showStream = Boolean(source) && !failed;
  const showStill = !showStream && Boolean(still);

  return (
    <Link
      to={`/cameras/${camera.id}`}
      className="group relative block overflow-hidden rounded-lg border border-line bg-black transition-colors duration-150 hover:border-line-strong"
      aria-label={`Open camera ${camera.name}`}
    >
      <div className="relative aspect-[16/10] w-full">
        {showStill && (
          <img
            src={still ?? undefined}
            alt=""
            onError={hideBrokenImage}
            className="absolute inset-0 h-full w-full object-cover opacity-90"
            loading="lazy"
          />
        )}
        {showStream && source && (
          <img
            src={source}
            alt={`${camera.name} — live annotated view`}
            className={cn(
              'absolute inset-0 h-full w-full bg-black object-contain transition-opacity duration-300',
              streaming ? 'opacity-100' : 'opacity-0',
            )}
            onLoad={() => setStreaming(true)}
            onError={() => {
              setStreaming(false);
              setFailed(true);
            }}
          />
        )}
        {streaming && <div className="scanline pointer-events-none absolute inset-0" aria-hidden />}

        {/* Nothing available — honest placeholder, no invented imagery */}
        {!showStill && !showStream && (
          <div className="absolute inset-0 grid place-items-center bg-surface-2 text-ink-faint">
            <span className="flex items-center gap-2 text-[11px]">
              <VideoOff size={13} aria-hidden />
              {failed || !ticket ? 'Preview unavailable' : 'Connecting…'}
            </span>
          </div>
        )}

        {/* Top overlays: identity + state */}
        <div className="pointer-events-none absolute inset-x-0 top-0 flex items-start justify-between gap-2 bg-gradient-to-b from-black/60 to-transparent px-2.5 pb-4 pt-2">
          <span className="min-w-0">
            <span className="mono block truncate text-[11px] font-semibold text-white/95">{camera.name}</span>
            <span className="mono block text-[9.5px] uppercase tracking-wider text-white/60">
              {camera.id.toUpperCase()}
            </span>
          </span>
          {streaming ? (
            <span className="inline-flex shrink-0 items-center gap-1 rounded-md bg-black/55 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider text-white">
              <CircleDot size={8} className="animate-pulse-dot text-rose-400" aria-hidden /> Live
            </span>
          ) : (
            <span
              className={cn(
                'inline-flex shrink-0 items-center gap-1.5 rounded-md bg-black/45 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider text-white/85',
              )}
            >
              <span className={cn('h-1.5 w-1.5 rounded-full', camera.status === 'ONLINE' ? 'bg-emerald-400' : 'bg-red-400')} aria-hidden />
              {camera.status.toLowerCase()}
            </span>
          )}
        </div>

        {/* Bottom overlay: last activity */}
        <div className="pointer-events-none absolute inset-x-0 bottom-0 flex items-center justify-between gap-2 bg-gradient-to-t from-black/65 to-transparent px-2.5 pb-1.5 pt-5">
          <span className="mono text-[9.5px] text-white/70">
            {camera.eventCount24h ? `${camera.eventCount24h} veh · 24 h` : 'no reads yet'}
          </span>
          <span className="mono text-[9.5px] tabular-nums text-white/70">
            {camera.lastEventAt ? `${formatTime(camera.lastEventAt)} · ${relativeTime(camera.lastEventAt)}` : '—'}
          </span>
        </div>
      </div>
    </Link>
  );
}

/**
 * Live camera mosaic — the Command Center's primary visual. Top online
 * cameras with the CV engine's real detection overlay. Streams are the
 * backend's own annotated previews; nothing here is simulated.
 */
export function DashboardMosaic({ cameras, count = 4 }: { cameras: Camera[]; count?: number }) {
  const picks = cameras.filter((c) => c.status === 'ONLINE').slice(0, count);
  const rest = cameras.filter((c) => c.status !== 'ONLINE').slice(0, Math.max(0, count - picks.length));
  const tiles = [...picks, ...rest].slice(0, count);

  if (tiles.length === 0) {
    return (
      <div className="rounded-lg border border-line bg-surface-1 px-6 py-10 text-center">
        <p className="text-sm font-semibold text-ink">No cameras online</p>
        <p className="mt-1 text-xs text-ink-faint">Live previews will appear here when cameras report in.</p>
      </div>
    );
  }

  return (
    <div
      className={cn(
        'grid gap-4',
        tiles.length === 1 ? 'sm:grid-cols-1' : 'grid-cols-1 sm:grid-cols-2',
      )}
      aria-label="Live camera mosaic"
    >
      {tiles.map((c) => (
        <MosaicTile key={c.id} camera={c} />
      ))}
    </div>
  );
}
