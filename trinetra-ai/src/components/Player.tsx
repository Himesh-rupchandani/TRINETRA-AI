import { useEffect, useState } from 'react';
import { CircleDot, Loader2, Play, RotateCw, ScanSearch, ShieldAlert, Square } from 'lucide-react';
import type { Camera, CameraStreamTicket } from '@/types';
import { cameraService } from '@/services/cameraService';
import { useWhepStream } from '@/hooks/useWhepStream';
import { canDecodeOverWebRtc, webRtcAvailable } from '@/lib/mediaSupport';
import { cn, formatTime } from '@/lib/utils';
import { config } from '@/lib/config';
import { Button } from '@/ui/Button';
import { SwitchChip } from '@/ui/Switch';

/**
 * Live camera player (WebRTC / WHEP), rebuilt UI over the original engine:
 *  - feeds are NEVER auto-started across the grid; the operator opts in;
 *  - playback URL comes from the backend ticket — no credentials here;
 *  - fps/resolution/codec in the OSD are measured from the live decoder;
 *  - MJPEG cameras (file-backed demo feeds) render via <img>;
 *  - the backend's annotated detection view (YOLO boxes) is preferred and
 *    silently falls back to the raw feed when unavailable.
 */
export function Player({
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

  // MJPEG cameras (file-backed demo feeds): <img> playback instead of WHEP.
  const isMjpeg = ticket?.streamType === 'MJPEG';
  const [mjpegAlive, setMjpegAlive] = useState(false);
  const [mjpegSrc, setMjpegSrc] = useState<string | null>(null);

  // Annotated detection view (OpenCV + YOLO, green boxes) when offered.
  const [aiBoxes, setAiBoxes] = useState(true);
  const [detectionFailed, setDetectionFailed] = useState(false);
  const detectionActive = aiBoxes && !detectionFailed && Boolean(ticket?.detectionUrl);
  const useImg = isMjpeg || detectionActive;

  const decodable = canDecodeOverWebRtc(camera.codec);
  const rtcOk = webRtcAvailable();

  const { videoRef, phase, error, stats, attempt, retryAt, retryNow } = useWhepStream(
    useImg ? null : ticket?.streamUrl || null,
    wanted,
  );

  useEffect(() => {
    setMjpegAlive(false);
    if (detectionActive && ticket?.detectionUrl) {
      setMjpegSrc(ticket.detectionUrl);
      return;
    }
    setMjpegSrc(ticket?.streamType === 'MJPEG' ? `/cvfeed/${camera.id}` : null);
  }, [ticket?.cameraId, ticket?.streamUrl, ticket?.detectionUrl, detectionActive, camera.id]);

  const requestStream = async () => {
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
    setRequesting(true);
    setTicketError(null);
    try {
      const t = await cameraService.stream(camera.id);
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
    setDetectionFailed(false);
  };

  // Switching camera always releases the previous feed first.
  useEffect(() => {
    setWanted(false);
    setTicket(null);
    setTicketError(null);
    if (autoRequest && camera.status !== 'OFFLINE') void requestStream();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [camera.id]);

  const noSource = Boolean(ticket && !ticket.streamUrl);
  const connecting =
    requesting || phase === 'CONNECTING' || phase === 'BUFFERING' || phase === 'AWAITING_KEYFRAME';
  const showVideo = wanted && Boolean(ticket?.streamUrl);
  const onAir = useImg ? mjpegAlive : phase === 'LIVE' || phase === 'STALLED';
  const showPoster = ticket?.poster ?? poster;
  const demoFeed =
    config.useMocks && !onAir && (noSource || Boolean(ticketError) || phase === 'UNAVAILABLE');

  const shownRes =
    stats.width && stats.height
      ? `${stats.width}×${stats.height}`
      : camera.width
        ? `${camera.width}×${camera.height}`
        : '—';
  const shownCodec = stats.codec ?? camera.codec ?? '—';
  const shownFps = stats.fps !== null ? stats.fps.toFixed(1) : '—';
  const quality =
    phase === 'STALLED' || (stats.fps !== null && stats.fps < 8) || (stats.jitterMs ?? 0) > 60
      ? 'Poor'
      : 'Good';

  return (
    <div className={cn('overflow-hidden rounded-xl border border-line bg-surface-1 shadow-xs', className)}>
      <div className="relative aspect-video w-full bg-black">
        {showPoster && !showVideo ? (
          <img
            src={showPoster}
            alt={`${camera.name} — last known frame`}
            className="h-full w-full object-cover opacity-90"
            loading="lazy"
            decoding="async"
          />
        ) : null}

        {showVideo && useImg && mjpegSrc && (
          <img
            src={mjpegSrc}
            alt={`${camera.name} — live view`}
            className={cn(
              'absolute inset-0 h-full w-full bg-black object-contain transition-opacity duration-300',
              mjpegAlive ? 'opacity-100' : 'opacity-0',
            )}
            decoding="async"
            onLoad={() => setMjpegAlive(true)}
            onError={() => {
              if (detectionActive && mjpegSrc === ticket?.detectionUrl) {
                setDetectionFailed(true);
              } else if (mjpegSrc !== ticket?.streamUrl && ticket?.streamUrl) {
                setMjpegSrc(ticket.streamUrl);
              } else {
                setMjpegAlive(false);
                setTicketError('Live view unavailable for this camera right now.');
              }
            }}
          />
        )}

        {showVideo && !useImg && (
          <video
            ref={videoRef}
            className={cn(
              'absolute inset-0 h-full w-full bg-black object-contain transition-opacity duration-300',
              onAir ? 'opacity-100' : 'opacity-0',
            )}
            autoPlay
            muted
            playsInline
            controls={onAir}
          />
        )}

        {onAir && <div className="scanline pointer-events-none absolute inset-0" aria-hidden />}

        {/* OSD — top */}
        <div className="pointer-events-none absolute inset-x-0 top-0 z-10 flex items-center justify-end gap-2 bg-gradient-to-b from-black/55 to-transparent px-3 py-2">
          {(phase === 'LIVE' || (detectionActive && mjpegAlive)) && (
            <span className="inline-flex items-center gap-1.5 rounded-full bg-black/55 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-white backdrop-blur-sm">
              <CircleDot size={9} className="animate-pulse-dot text-rose-400" aria-hidden /> Live
            </span>
          )}
          {detectionActive && mjpegAlive && (
            <span className="inline-flex items-center gap-1.5 rounded-full bg-black/55 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-white backdrop-blur-sm">
              <ScanSearch size={9} className="text-emerald-400" aria-hidden /> AI detection
            </span>
          )}
          {phase === 'STALLED' && (
            <span className="rounded-full bg-black/55 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-amber-300 backdrop-blur-sm">
              No frames
            </span>
          )}
        </div>

        {/* OSD — bottom */}
        {onAir && (
          <div className="pointer-events-none absolute inset-x-0 bottom-0 z-10 flex items-center justify-between gap-3 bg-gradient-to-t from-black/70 to-transparent px-3 pb-2 pt-6">
            <span className="mono min-w-0 truncate text-[11px] text-white/90">
              <span className="font-semibold">{camera.name}</span>
              <span className="text-white/60"> · {camera.location}</span>
              <span className="hidden text-white/50 sm:inline">
                {' — '}
                {shownCodec} · {shownRes} · {shownFps} fps
                {stats.bitrateKbps !== null ? ` · ${(stats.bitrateKbps / 1000).toFixed(2)} Mbps` : ''}
              </span>
            </span>
            <span className="mono shrink-0 text-[11px] tabular-nums text-white/80">
              {formatTime(new Date().toISOString())}
            </span>
          </div>
        )}

        {/* Idle / connecting / error overlay */}
        {!onAir && (
          <div
            className={cn(
              'absolute inset-0 z-20 px-4',
              demoFeed ? 'flex flex-col justify-end' : 'grid place-items-center bg-black/70 text-center',
            )}
          >
            {demoFeed ? (
              <div className="flex flex-wrap items-center justify-between gap-2 bg-black/60 px-3.5 py-2 backdrop-blur-sm">
                <span className="flex items-center gap-2.5">
                  <span className="rounded-full border border-amber-300/50 bg-black/40 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-amber-300">
                    Demo feed
                  </span>
                  <span className="text-xs text-white/75">
                    Showing a demo frame — live camera not reachable from here.
                  </span>
                </span>
                <Button
                  variant="secondary"
                  size="xs"
                  onClick={() => {
                    if (ticket?.streamUrl) retryNow();
                    else void requestStream();
                  }}
                >
                  Try live
                </Button>
              </div>
            ) : (
              <div className="max-w-md">
                {!wanted && !requesting ? (
                  <>
                    <Button variant="primary" size="md" onClick={requestStream} disabled={!decodable || !rtcOk}>
                      <Play size={15} aria-hidden /> Watch live video
                    </Button>
                    <p className="mt-3 text-xs leading-relaxed text-white/60">
                      {decodable && rtcOk
                        ? 'Video only starts when you ask for it, so the network stays fast.'
                        : 'This camera uses a video format your browser cannot play.'}
                    </p>
                  </>
                ) : connecting ? (
                  <div>
                    <p className="flex items-center justify-center gap-2 text-[13px] text-white/90">
                      <Loader2 size={14} className="animate-spin" aria-hidden />
                      {requesting
                        ? 'Connecting to camera…'
                        : phase === 'AWAITING_KEYFRAME'
                          ? 'Waiting for the first full picture…'
                          : 'Connecting…'}
                    </p>
                    {phase === 'AWAITING_KEYFRAME' && (
                      <>
                        <p className="mt-2 text-xs leading-relaxed text-white/65">
                          Connected — waiting for the camera to send a complete frame. The video will
                          appear on its own.
                        </p>
                        <p className="mono mt-2 text-[11px] text-white/45">
                          {(stats.bytesReceived / 1024).toFixed(0)} KB received · {stats.keyframeRequests} requests sent
                        </p>
                      </>
                    )}
                  </div>
                ) : phase === 'RECONNECTING' ? (
                  <div>
                    <RotateCw size={18} className="mx-auto mb-2 animate-spin text-amber-300" aria-hidden />
                    <p className="text-sm font-semibold text-white/95">
                      Video interrupted — reconnecting (try {attempt})
                    </p>
                    <p className="mt-1.5 text-xs leading-relaxed text-white/65">
                      Reconnecting automatically
                      {retryAt ? ` — next try in ${Math.max(0, Math.round((retryAt - Date.now()) / 1000))}s` : ''}.
                    </p>
                  </div>
                ) : (
                  <div>
                    <ShieldAlert size={20} className="mx-auto mb-2 text-amber-300" aria-hidden />
                    <p className="text-sm font-semibold text-white/95">Video not available</p>
                    <p className="mt-1.5 text-xs leading-relaxed text-white/65">
                      {ticketError ??
                        error ??
                        (camera.status === 'OFFLINE'
                          ? 'This camera is switched off or disconnected.'
                          : 'No video source is published for this camera right now.')}
                    </p>
                    {!noSource && !decodable === false && (
                      <Button variant="secondary" size="xs" className="mt-3" onClick={() => void requestStream()}>
                        Retry
                      </Button>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Control strip */}
      {showVideo && (
        <div className="border-t border-line bg-surface-1 px-4 py-2.5">
          <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
            <span className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-ink-muted">
              {onAir ? (
                <span className="inline-flex items-center gap-1.5 font-medium text-ink">
                  <span
                    className={cn('h-1.5 w-1.5 rounded-full', quality === 'Good' ? 'bg-online' : 'bg-warn')}
                    aria-hidden
                  />
                  {quality === 'Good' ? 'Video is clear' : 'Video quality is poor'}
                </span>
              ) : (
                <span>Connecting…</span>
              )}
              <span>
                Watching for <span className="mono">{Math.round(stats.mediaTime)}s</span>
              </span>
            </span>
            <span className="flex flex-wrap items-center gap-2">
              {ticket?.detectionUrl && !detectionFailed && (
                <SwitchChip
                  checked={aiBoxes}
                  onChange={setAiBoxes}
                  label="Vehicle detection"
                  title="Real-time vehicle detection (green boxes) rendered by the backend"
                />
              )}
              <Button variant="ghost" size="xs" onClick={() => setShowTechnical((v) => !v)} aria-expanded={showTechnical}>
                {showTechnical ? 'Hide' : 'Show'} technical
              </Button>
              <Button variant="ghost" size="xs" onClick={stopStream}>
                <Square size={11} aria-hidden /> Stop
              </Button>
            </span>
          </div>

          {showTechnical && (
            <dl className="mono mt-3 grid grid-cols-2 gap-x-5 gap-y-2 border-t border-line pt-3 text-[11px] text-ink-faint sm:grid-cols-4">
              <div>
                Transport <span className="text-ink-muted">{detectionActive ? 'MJPEG (AI view)' : (ticket?.streamType ?? 'WEBRTC')}</span>
              </div>
              <div>
                Media clock <span className="text-ink-muted">{stats.mediaTime.toFixed(1)}s</span>
              </div>
              <div>
                Frames <span className="text-ink-muted">{stats.framesDecoded.toLocaleString()}</span>
              </div>
              <div>
                Lost packets <span className="text-ink-muted">{stats.packetsLost}</span>
              </div>
              <div>
                Jitter <span className="text-ink-muted">{stats.jitterMs !== null ? `${stats.jitterMs.toFixed(0)} ms` : '—'}</span>
              </div>
              <div>
                Scene cuts <span className="text-ink-muted">{stats.discontinuities}</span>
              </div>
              <div className="col-span-2">
                Codec / size <span className="text-ink-muted">{shownCodec} · {shownRes} · {shownFps} fps</span>
              </div>
            </dl>
          )}
        </div>
      )}
    </div>
  );
}
