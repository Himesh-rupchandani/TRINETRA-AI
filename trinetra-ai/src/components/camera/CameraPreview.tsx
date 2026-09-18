import { Cctv, CircleDot, Loader2, RefreshCw, RotateCw, ScanSearch } from 'lucide-react';
import type { Camera } from '@/types';
import { useCameraPreview } from '@/hooks/useCameraPreview';
import { hideBrokenImage } from '@/utils/mediaAssets';
import { cn } from '@/lib/utils';

/**
 * The live picture on a camera card.
 *
 * It replaces the grey camera tile the registry used to show: every card now
 * plays its own camera, and the grey placeholder only remains as the honest
 * "nothing to play" state (camera off / preview switched off / browser cannot
 * decode the feed).
 *
 * Bandwidth rules live in `useCameraPreview` — nothing is requested until the
 * card is on screen, WebRTC is preferred with the HLS stream as fallback, and
 * mock mode always labels a synthetic frame as such.
 */
export function CameraPreview({
  camera,
  enabled = true,
  className,
}: {
  camera: Camera;
  /** false = never start a stream for this tile (table view, compact cards). */
  enabled?: boolean;
  className?: string;
}) {
  const {
    containerRef,
    videoRef,
    phase,
    transport,
    imageSrc,
    posterSrc,
    isLive,
    synthetic,
    detectionView,
    recorded,
    needsVideo,
    retryable,
    attempt,
    error,
    markAlive,
    markFailed,
    retryNow,
  } = useCameraPreview(camera, enabled);

  const connecting = phase === 'CONNECTING' || phase === 'RECONNECTING';
  // IDLE deliberately shows nothing but the placeholder: it is also the state
  // of the first frame (before the viewport observer has answered), and a
  // "preview off" note flashing on every card would be noise.
  const dead = phase === 'OFFLINE' || phase === 'BLOCKED';
  // A mock-mode frame is labelled whenever it is what the eye is on: as the
  // fallback tile, or as the poster before real video paints. A tile that is
  // showing real video carries no such chip.
  const showDemoChip = synthetic || (Boolean(posterSrc) && !isLive);

  return (
    <div
      ref={containerRef}
      className={cn('relative isolate h-full w-full overflow-hidden bg-surface-2', className)}
    >
      {/* Base layer: the grey camera tile. It is a placeholder, never a
          stand-in for a running feed — anything live is drawn over it. */}
      <div className="absolute inset-0 grid place-items-center text-ink-faint" aria-hidden>
        <Cctv size={18} />
      </div>

      {posterSrc && !imageSrc && (
        <img
          src={posterSrc}
          alt=""
          className="absolute inset-0 h-full w-full object-cover"
          loading="lazy"
          decoding="async"
          onError={hideBrokenImage}
        />
      )}

      {imageSrc && (
        <img
          src={imageSrc}
          alt={`${camera.name} — live view`}
          className={cn(
            'absolute inset-0 h-full w-full bg-black object-cover transition-opacity',
            // An MJPEG view stays hidden until it has actually painted a frame;
            // the mock still is a finished picture, so it shows immediately.
            transport === 'MJPEG' && !isLive ? 'opacity-0' : 'opacity-100',
          )}
          decoding="async"
          onLoad={markAlive}
          onError={markFailed}
        />
      )}

      {needsVideo && (
        <video
          ref={videoRef}
          className={cn(
            'absolute inset-0 h-full w-full bg-black object-cover transition-opacity',
            isLive ? 'opacity-100' : 'opacity-0',
          )}
          autoPlay
          muted
          playsInline
          disablePictureInPicture
        />
      )}

      {/* On-screen display — the same language as the full player. */}
      <div className="pointer-events-none absolute inset-x-0 top-0 z-10 flex flex-wrap items-center justify-end gap-1.5 bg-gradient-to-b from-black/55 to-transparent px-2 py-1.5">
        {isLive && !recorded && (
          <span className="chip border-critical/60 bg-critical/25 text-white">
            <CircleDot size={9} className="animate-pulse" aria-hidden /> LIVE
          </span>
        )}
        {/* A file-backed camera replays a recording — saying LIVE there would
            be a lie, whatever the transport underneath. */}
        {isLive && recorded && (
          <span className="chip border-white/25 bg-black/45 text-white/85">PLAYBACK</span>
        )}
        {isLive && detectionView && (
          <span className="chip border-online/60 bg-online/25 text-white">
            <ScanSearch size={9} aria-hidden /> AI DETECTION
          </span>
        )}
        {isLive && transport === 'HLS' && (
          <span className="chip border-white/25 bg-black/45 text-white/80">HLS</span>
        )}
        {showDemoChip && (
          <span className="chip border-amber-400/60 bg-black/50 text-amber-300">DEMO FEED</span>
        )}
        {connecting && (
          <span className="chip border-white/25 bg-black/50 text-white/85">
            {phase === 'RECONNECTING' ? (
              <>
                <RotateCw size={9} className="animate-spin" aria-hidden /> Reconnecting
                {attempt > 1 ? ` (${attempt})` : ''}
              </>
            ) : (
              <>
                <Loader2 size={9} className="animate-spin" aria-hidden /> Connecting…
              </>
            )}
          </span>
        )}
        {phase === 'OFFLINE' && (
          <span className="chip border-white/25 bg-black/50 text-white/75">CAMERA OFF</span>
        )}
      </div>

      {isLive && (
        <div className="pointer-events-none absolute inset-x-0 bottom-0 z-10 flex items-center justify-between gap-2 bg-gradient-to-t from-black/75 to-transparent px-2 py-1.5">
          <span className="min-w-0 truncate font-mono text-2xs text-white/90">
            <span className="font-bold">{camera.name}</span>
            <span className="text-white/55"> · {camera.location}</span>
          </span>
        </div>
      )}

      {/* Terminal states get one short sentence and, when it can help, a retry.
          A tile that cannot play is better than a tile that lies. */}
      {dead && !isLive && (
        <div className="absolute inset-0 z-20 flex flex-col items-center justify-center gap-1.5 bg-black/45 px-3 text-center">
          <p className="text-2xs font-semibold text-white/90">
            {phase === 'OFFLINE' ? 'Camera is switched off' : (error ?? 'Live view not available')}
          </p>
          {phase === 'BLOCKED' && retryable && (
            <button type="button" className="btn-ghost btn-xs border-white/30 text-white/85" onClick={retryNow}>
              <RefreshCw size={10} aria-hidden /> Try live
            </button>
          )}
        </div>
      )}

      {synthetic && (
        <div className="absolute inset-x-0 bottom-0 z-20 flex items-center justify-end px-2 py-1.5">
          <button
            type="button"
            className="btn-ghost btn-xs border-white/30 bg-black/40 text-white/85"
            onClick={retryNow}
          >
            <RefreshCw size={10} aria-hidden /> Try live
          </button>
        </div>
      )}
    </div>
  );
}
