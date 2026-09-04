import { useEffect, useState } from 'react';
import { CircleDot, Loader2, Play, RotateCw, ShieldAlert, Square } from 'lucide-react';
import type { Camera, CameraStreamTicket } from '@/types';
import { cameraService } from '@/services/cameraService';
import { useWhepStream } from '@/hooks/useWhepStream';
import { canDecodeOverWebRtc, webRtcAvailable } from '@/lib/mediaSupport';
import { cn, formatTime } from '@/lib/utils';
import { config } from '@/lib/config';
import { StatusChip } from '@/components/common/Chips';

/**
 * Live camera player (WebRTC / WHEP).
 *
 * Behaviour follows the Sentinel integrator's guide:
 *  - feeds are NEVER auto-started across the grid; the operator opts in, so the
 *    control room never pulls 30 concurrent copies of the stream;
 *  - the playback URL comes from the backend ticket — no credentials here;
 *  - the reported frame rate is ignored: fps/resolution/codec shown in the OSD
 *    are measured from the live decoder;
 *  - inter-frame gaps are tolerated, drops trigger backoff reconnection;
 *  - the loop-point scene cut is counted and survived, not treated as an error.
 */
export function CameraPlayer({
  camera,
  poster,
  autoRequest = false,
  className,
}: {
  camera: Camera;
  poster?: string;
  autoRequest?: boolean;
  className?: string;
}) {
  const [ticket, setTicket] = useState<CameraStreamTicket | null>(null);
  const [requesting, setRequesting] = useState(false);
  const [ticketError, setTicketError] = useState<string | null>(null);
  const [wanted, setWanted] = useState(false);
  const [showTechnical, setShowTechnical] = useState(false);

  // Checked before negotiating: an undecodable codec must not retry-loop.
  const decodable = canDecodeOverWebRtc(camera.codec);
  const rtcOk = webRtcAvailable();

  /**
   * MJPEG is served by our own ingestion pipeline over the same origin, so it
   * needs no WebRTC signalling to an external gateway. When the backend hands
   * us an MJPEG ticket we render it with a plain <img> and skip WHEP entirely.
   */
  const isMjpeg = ticket?.streamType === 'MJPEG';
  const [mjpegOk, setMjpegOk] = useState(false);
  const [mjpegNonce, setMjpegNonce] = useState(0);

  const { videoRef, phase, error, stats, attempt, retryAt, retryNow } = useWhepStream(
    isMjpeg ? null : ticket?.streamUrl || null,
    wanted && !isMjpeg,
  );

  // Cache-busting nonce forces the browser to open a fresh multipart response
  // on retry; without it a stalled MJPEG connection can be reused.
  const mjpegSrc =
    isMjpeg && wanted && ticket?.streamUrl
      ? `${ticket.streamUrl}${ticket.streamUrl.includes('?') ? '&' : '?'}t=${mjpegNonce}`
      : null;

  const requestStream = async () => {
    setRequesting(true);
    setTicketError(null);
    setMjpegOk(false);
    try {
      // Ask the backend which transport to use BEFORE applying WebRTC-only
      // capability checks — an MJPEG feed plays fine in browsers with no
      // WebRTC and decodes codecs WebRTC would reject.
      const t = await cameraService.stream(camera.id);
      if (t.streamType !== 'MJPEG') {
        if (!rtcOk) {
          setTicketError('This browser cannot play live video. Please use Chrome, Edge or Safari.');
          return;
        }
        if (!decodable) {
          setTicketError(
            'This camera records in a video format your browser cannot play. Its recordings are still used by the AI system — try opening it in a different browser.',
          );
          return;
        }
      }
      setTicket(t);
      setWanted(true);
    } catch (e) {
      setTicketError(e instanceof Error ? e.message : 'Could not connect to this camera.');
    } finally {
      setRequesting(false);
    }
  };

  const stopStream = () => {
    setWanted(false);
    setTicket(null);
  };

  // Switching camera always releases the previous feed first.
  useEffect(() => {
    setWanted(false);
    setTicket(null);
    setTicketError(null);
    setMjpegOk(false);
    if (autoRequest && camera.status !== 'OFFLINE') void requestStream();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [camera.id]);

  const noSource = Boolean(ticket && !ticket.streamUrl);
  const connecting =
    requesting || phase === 'CONNECTING' || phase === 'BUFFERING' || phase === 'AWAITING_KEYFRAME';
  const showVideo = wanted && Boolean(ticket?.streamUrl);
  const onAir = isMjpeg ? mjpegOk : phase === 'LIVE' || phase === 'STALLED';

  /** Retry that works for whichever transport is active. */
  const retryStream = () => {
    if (isMjpeg) {
      setMjpegOk(false);
      setMjpegNonce((n) => n + 1);
      return;
    }
    if (ticket?.streamUrl) retryNow();
    else void requestStream();
  };
  const showPoster = ticket?.poster ?? poster;
  /** Demo mode with no reachable gateway: show a clean demo frame, not an error. */
  const demoFeed =
    config.useMocks && !onAir && (noSource || Boolean(ticketError) || phase === 'UNAVAILABLE');

  // Measured values win over catalogue metadata; fall back only when unknown.
  const shownRes =
    stats.width && stats.height
      ? `${stats.width}×${stats.height}`
      : camera.width
        ? `${camera.width}×${camera.height}`
        : '—';
  const shownCodec = stats.codec ?? camera.codec ?? '—';
  const shownFps = stats.fps !== null ? stats.fps.toFixed(1) : '—';

  /** One-word verdict an officer can act on, instead of raw jitter/loss numbers. */
  const quality =
    phase === 'STALLED' || (stats.fps !== null && stats.fps < 8) || (stats.jitterMs ?? 0) > 60
      ? 'Poor'
      : 'Good';

  return (
    <div className={cn('relative overflow-hidden rounded border border-line bg-black', className)}>
      <div className="relative aspect-video w-full">
        {showPoster ? (
          <img
            src={showPoster}
            alt={`${camera.name} — last known frame`}
            className="h-full w-full object-cover"
            loading="lazy"
            decoding="async"
          />
        ) : (
          <div className="grid h-full w-full place-items-center bg-surface-2" />
        )}

        {showVideo && (
          <video
            ref={videoRef}
            className={cn(
              'absolute inset-0 h-full w-full bg-black object-contain transition-opacity',
              onAir ? 'opacity-100' : 'opacity-0',
            )}
            autoPlay
            muted
            playsInline
            controls={onAir}
          />
        )}

        {/*
          MJPEG feed from our own pipeline. A multipart response renders in a
          plain <img>, so this works with no WebRTC, no codec negotiation and
          no external gateway — and it carries the AI overlay we already draw.
        */}
        {mjpegSrc && (
          <img
            key={mjpegSrc}
            src={mjpegSrc}
            alt={`Live view from ${camera.name}`}
            className={cn(
              'absolute inset-0 h-full w-full bg-black object-contain transition-opacity',
              mjpegOk ? 'opacity-100' : 'opacity-0',
            )}
            onLoad={() => setMjpegOk(true)}
            onError={() => setMjpegOk(false)}
          />
        )}

        <div className="scanline pointer-events-none absolute inset-0" aria-hidden />

        {/* On-screen display */}
        {/* Chips only: the source burns its own timestamp into the top-left corner. */}
        <div className="pointer-events-none absolute inset-x-0 top-0 z-10 flex items-center justify-end gap-2 bg-gradient-to-b from-black/60 to-transparent px-2.5 py-1.5">
          <span className="flex items-center gap-1.5">
            {phase === 'LIVE' && (
              <span className="chip border-critical/60 bg-critical/25 text-white">
                <CircleDot size={9} className="animate-pulse" aria-hidden /> LIVE
              </span>
            )}
            {phase === 'STALLED' && (
              <span className="chip border-degraded/60 bg-degraded/25 text-white">NO FRAMES</span>
            )}
            <StatusChip status={camera.status} />
          </span>
        </div>

        <div className="pointer-events-none absolute inset-x-0 bottom-0 z-10 flex items-center justify-between gap-2 bg-gradient-to-t from-black/80 to-transparent px-2.5 py-1.5">
          <span className="min-w-0 truncate font-mono text-2xs text-white/85">
            <span className="font-bold text-white/95">{camera.name}</span> · {camera.location}
            <span className="text-white/55">
              {' — '}
              {shownCodec} · {shownRes} · {shownFps} fps
              {stats.bitrateKbps !== null && onAir
                ? ` · ${(stats.bitrateKbps / 1000).toFixed(2)} Mbps`
                : ''}
            </span>
          </span>
          <span className="font-mono text-2xs text-white/80">
            {formatTime(new Date().toISOString())}
          </span>
        </div>

        {/* Idle / connecting / error overlay — or a clean demo frame in mock mode */}
        {!onAir && (
          <div
            className={cn(
              'absolute inset-0 z-20 px-4',
              demoFeed
                ? 'flex flex-col justify-end'
                : 'grid place-items-center bg-black/60 text-center',
            )}
          >
            {demoFeed ? (
              <div className="flex flex-wrap items-center justify-between gap-2 rounded-t-lg bg-black/55 px-3 py-2">
                <span className="flex items-center gap-2">
                  <span className="chip border-amber-400/50 bg-black/40 text-amber-300">
                    <CircleDot size={9} className="animate-pulse" aria-hidden /> DEMO FEED
                  </span>
                  <span className="text-2xs text-white/75">
                    Showing a demo frame — live camera not reachable from here.
                  </span>
                </span>
                <button
                  type="button"
                  className="btn-ghost btn-xs border-white/30 text-white/85"
                  onClick={retryStream}
                >
                  Try live
                </button>
              </div>
            ) : (
            <div className="max-w-md">
              {connecting ? (
                <div>
                  <p className="flex items-center justify-center gap-2 text-xs text-white/85">
                    <Loader2 size={14} className="animate-spin" aria-hidden />
                    {requesting
                      ? 'Connecting to camera…'
                      : phase === 'AWAITING_KEYFRAME'
                        ? `Starting video… ${stats.waitingSecs}s`
                        : 'Connecting to camera…'}
                  </p>
                  {phase === 'AWAITING_KEYFRAME' && (
                    <>
                      <p className="mt-2 text-xs leading-relaxed text-white/70">
                        We are connected to this camera and waiting for it to send a full
                        picture. This can take a moment on a busy camera. The video will
                        appear on its own.
                      </p>
                      <p className="mt-2 font-mono text-2xs text-white/45">
                        {(stats.bytesReceived / 1024).toFixed(0)} KB received ·{' '}
                        {stats.keyframeRequests} requests sent
                      </p>
                      <button
                        type="button"
                        className="btn-ghost btn-xs mt-3 border-white/30 text-white/85"
                        onClick={retryNow}
                      >
                        Try again
                      </button>
                    </>
                  )}
                </div>
              ) : phase === 'RECONNECTING' ? (
                <>
                  <RotateCw size={18} className="mx-auto mb-1.5 animate-spin text-degraded" aria-hidden />
                  <p className="text-sm font-semibold text-white/90">
                    Video interrupted — reconnecting (try {attempt})
                  </p>
                  <p className="mt-1 text-2xs leading-relaxed text-white/65">
                    The camera stopped sending video. We are reconnecting automatically —
                    you do not need to do anything.
                    {retryAt
                      ? ` Next try in ${Math.max(0, Math.round((retryAt - Date.now()) / 1000))} seconds.`
                      : ''}
                  </p>
                  <button
                    type="button"
                    className="btn-ghost btn-xs mt-3 border-white/30 text-white/85"
                    onClick={retryStream}
                  >
                    Try now
                  </button>
                </>
              ) : phase === 'UNAVAILABLE' || ticketError || noSource ? (
                <>
                  <ShieldAlert size={20} className="mx-auto mb-1.5 text-degraded" aria-hidden />
                  <p className="text-sm font-semibold text-white/90">Video not available</p>
                  <p className="mt-1 text-2xs leading-relaxed text-white/65">
                    {ticketError ??
                      error ??
                      (camera.status === 'OFFLINE'
                        ? 'This camera is switched off or disconnected, so there is nothing to show.'
                        : 'This camera is not sending video at the moment.')}
                  </p>
                  <button
                    type="button"
                    className="btn-ghost btn-xs mt-2.5 border-white/30 text-white/85"
                    onClick={retryStream}
                  >
                    Try again
                  </button>
                </>
              ) : camera.status === 'OFFLINE' ? (
                <>
                  <p className="text-sm font-semibold text-offline">Camera is offline</p>
                  <p className="mt-1.5 text-xs text-white/65">
                    Last working at {formatTime(camera.lastSeen)}. No video available.
                  </p>
                </>
              ) : (
                <>
                  <button
                    type="button"
                    className="btn-solid mx-auto"
                    onClick={requestStream}
                  >
                    <Play size={15} aria-hidden /> Watch live video
                  </button>
                  <p className="mt-2 text-2xs text-white/60">
                    {decodable && rtcOk
                      ? 'Video only starts when you ask for it, so the network stays fast.'
                      : 'This camera uses a video format your browser cannot play.'}
                  </p>
                </>
              )}
            </div>
            )}
          </div>
        )}
      </div>

      {showVideo && (
        <div className="border-t border-line bg-surface-1 px-3 py-2">
          <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1.5">
            <span className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink-muted">
              {onAir ? (
                <span className="inline-flex items-center gap-1.5 font-medium text-ink">
                  <span
                    className={cn(
                      'h-2 w-2 rounded-full',
                      quality === 'Good' ? 'bg-online' : 'bg-degraded',
                    )}
                    aria-hidden
                  />
                  {quality === 'Good' ? 'Video is clear' : 'Video quality is poor'}
                </span>
              ) : (
                <span>Connecting…</span>
              )}
              <span>Watching for {Math.round(stats.mediaTime)}s</span>
            </span>
            <span className="flex items-center gap-1.5">
              <button
                type="button"
                className="btn-ghost btn-xs"
                onClick={() => setShowTechnical((v) => !v)}
                aria-expanded={showTechnical}
              >
                {showTechnical ? 'Hide' : 'Show'} technical details
              </button>
              <button type="button" className="btn-ghost btn-xs" onClick={stopStream}>
                <Square size={11} aria-hidden /> Stop video
              </button>
            </span>
          </div>

          {showTechnical && (
            <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 border-t border-line pt-2 font-mono text-2xs text-ink-faint sm:grid-cols-4">
              <div>
                <dt className="inline">Transport </dt>
                <dd className="inline text-ink-muted">{ticket?.streamType ?? 'WEBRTC'}</dd>
              </div>
              <div>
                <dt className="inline">Media clock </dt>
                <dd className="inline text-ink-muted">{stats.mediaTime.toFixed(1)}s</dd>
              </div>
              <div>
                <dt className="inline">Frames </dt>
                <dd className="inline text-ink-muted">{stats.framesDecoded.toLocaleString()}</dd>
              </div>
              <div>
                <dt className="inline">Lost packets </dt>
                <dd className="inline text-ink-muted">{stats.packetsLost}</dd>
              </div>
              <div>
                <dt className="inline">Jitter </dt>
                <dd className="inline text-ink-muted">
                  {stats.jitterMs !== null ? `${stats.jitterMs.toFixed(0)} ms` : '—'}
                </dd>
              </div>
              <div>
                <dt className="inline">Scene cuts </dt>
                <dd className="inline text-ink-muted">{stats.discontinuities}</dd>
              </div>
              <div className="col-span-2">
                <dt className="inline">Codec / size </dt>
                <dd className="inline text-ink-muted">
                  {shownCodec} · {shownRes} · {shownFps} fps
                </dd>
              </div>
            </dl>
          )}
        </div>
      )}
    </div>
  );
}
