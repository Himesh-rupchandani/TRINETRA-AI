import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { backoffDelay } from '@/services/whepClient';
import { CircleDot, Loader2, Play, RotateCw, ScanSearch, ShieldAlert, Square } from 'lucide-react';
import type { Camera, CameraStreamTicket } from '@/types';
import { cameraService } from '@/services/cameraService';
import { useWhepStream, type StreamStats } from '@/hooks/useWhepStream';
import { useHlsStream, whepUrlToHls } from '@/hooks/useHlsStream';
import { canDecodeOverWebRtc, webRtcAvailable } from '@/lib/mediaSupport';
import { cn, formatTime } from '@/lib/utils';
import { config } from '@/lib/config';
import { anprStatusLabel } from '@/lib/liveDetections';
import { CountingOverlay } from './CountingOverlay';
import type { CountingPreview } from '@/services/trafficService';
import { StatusChip } from '@/components/common/Chips';
import { DetectionOverlay } from './DetectionOverlay';
import { liveAnprService, type LiveAnprSnapshot } from '@/services/liveAnprService';

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
 *  - when WebRTC cannot get through (or the codec is undecodable over it),
 *    playback steps down to the HLS compatibility stream (guide §1).
 */
/**
 * Ticket errors that mean "this browser can never play this feed" — retrying
 * cannot help, so the auto-retry loop stays off for these. Everything else
 * (gateway 502, expired ticket, cold start…) is retried automatically.
 */
const NO_RTC_ERROR = 'This browser cannot play live video. Please use Chrome, Edge or Safari.';
const NO_CODEC_ERROR =
  'This camera records in a video format your browser cannot play. Its recordings are still used by the AI system — try opening it in a different browser.';
const FATAL_BROWSER_ERRORS = new Set([NO_RTC_ERROR, NO_CODEC_ERROR]);

/** Zeroed stats for the HLS path — the OSD falls back to catalogue values. */
const HLS_ZERO_STATS: StreamStats = {
  fps: null,
  width: null,
  height: null,
  codec: null,
  bitrateKbps: null,
  packetsLost: 0,
  jitterMs: null,
  framesDecoded: 0,
  bytesReceived: 0,
  keyframeRequests: 0,
  waitingSecs: 0,
  mediaTime: 0,
  discontinuities: 0,
};

export function CameraPlayer({
  camera,
  poster,
  autoRequest = false,
  embedded = false,
  className,
  onDetectionSnapshot,
  countingPreview,
}: {
  camera: Camera;
  poster?: string;
  autoRequest?: boolean;
  /** Hide the standalone control footer — used when embedded inside a card. */
  embedded?: boolean;
  className?: string;
  onDetectionSnapshot?: (snapshot: LiveAnprSnapshot | null) => void;
  countingPreview?: CountingPreview | null;
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

  // Real-time vehicle detection: when the backend offers an annotated view of
  // this camera (OpenCV + YOLO, green boxes) it is shown instead of the raw
  // feed. The operator can switch back to the raw stream at any time, and any
  // failure of the detection view silently falls back to the raw feed.
  const [aiBoxes, setAiBoxes] = useState(true);
  const [detectionFailed, setDetectionFailed] = useState(false);
  // Keep WHEP/HLS on the native video decoder; switching them to MJPEG for
  // AI tied playback to inference speed. Only file/MJPEG cameras use that view.
  const detectionActive = isMjpeg && aiBoxes && !detectionFailed && Boolean(ticket?.detectionUrl);
  const [anprStatus, setAnprStatus] = useState<LiveAnprSnapshot | null>(null);
  const [anprError, setAnprError] = useState<string | null>(null);
  const onAnprStatus = useCallback((value: LiveAnprSnapshot) => {
    setAnprStatus(value);
    setAnprError(null);
    onDetectionSnapshot?.(value);
  }, [onDetectionSnapshot]);
  const useImg = isMjpeg || detectionActive;

  useEffect(() => {
    setAnprStatus(null);
    setAnprError(null);
    onDetectionSnapshot?.(null);
    if (!detectionActive || !wanted || config.useMocks) return;
    const abort = new AbortController();
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const value = await liveAnprService.status(camera.id, abort.signal);
        if (!stopped) onAnprStatus(value);
      } catch (error) {
        if (!stopped) setAnprError(error instanceof Error ? error.message : 'Plate scanning unavailable.');
      } finally {
        if (!stopped) timer = setTimeout(poll, 1500);
      }
    };
    void poll();
    return () => { stopped = true; abort.abort(); clearTimeout(timer); };
  }, [detectionActive, wanted, camera.id, onAnprStatus, onDetectionSnapshot]);

  // The MJPEG views (file feed / AI detection view) can also serve an honest
  // "NO SIGNAL" placeholder when the camera source is unreachable from this
  // network. Probe the backend so the chips reflect reality — a LIVE /
  // AI DETECTION badge over a NO-SIGNAL frame would mislead the operator.
  const [mjpegSignal, setMjpegSignal] = useState(true);
  useEffect(() => {
    if (!useImg || !wanted) return;
    if (config.useMocks) {
      setMjpegSignal(true);
      return;
    }
    let stop = false;
    const check = async () => {
      try {
        const ok = await cameraService.signal(camera.id);
        if (!stop) setMjpegSignal(ok);
      } catch {
        if (!stop) setMjpegSignal(false);
      }
    };
    void check();
    const timer = window.setInterval(check, 3000);
    return () => {
      stop = true;
      window.clearInterval(timer);
    };
  }, [useImg, wanted, camera.id]);

  // Transport ladder: WebRTC first, HLS compatibility stream when WebRTC
  // cannot get through (guide §1: HLS is the restricted-network fallback).
  const [transport, setTransport] = useState<'whep' | 'hls'>('whep');
  const hlsUrl = useMemo(() => whepUrlToHls(ticket?.streamUrl), [ticket?.streamUrl]);

  // Checked before negotiating: an undecodable codec must not retry-loop.
  const decodable = canDecodeOverWebRtc(camera.codec);
  const rtcOk = webRtcAvailable();

  const hlsActive = transport === 'hls';
  const {
    videoRef: whepRef,
    phase: whepPhase,
    error: whepError,
    stats: whepStats,
    attempt: whepAttempt,
    retryAt: whepRetryAt,
    retryNow: whepRetry,
  } = useWhepStream(useImg || hlsActive ? null : ticket?.streamUrl || null, wanted && !hlsActive);
  const {
    videoRef: hlsRef,
    phase: hlsPhase,
    error: hlsError,
    mediaTime: hlsMediaTime,
    attempt: hlsAttempt,
    retryAt: hlsRetryAt,
    retryNow: hlsRetry,
  } = useHlsStream(useImg || !hlsActive ? null : hlsUrl, wanted && hlsActive);

  // The UI below always reads the active transport through these selectors.
  const videoRef = hlsActive ? hlsRef : whepRef;
  const phase = hlsActive ? hlsPhase : whepPhase;
  const error = hlsActive ? hlsError : whepError;
  const stats = hlsActive ? { ...HLS_ZERO_STATS, mediaTime: hlsMediaTime } : whepStats;
  const attempt = hlsActive ? hlsAttempt : whepAttempt;
  const retryAt = hlsActive ? hlsRetryAt : whepRetryAt;
  const retryNow = hlsActive ? hlsRetry : whepRetry;
  /** Manual "start over": back to WebRTC with a reset backoff ladder. */
  const restartChain = () => {
    setTransport('whep');
    hlsRetry();
    whepRetry();
  };

  // WebRTC exhausted without ever going live: step down to HLS once.
  useEffect(() => {
    if (transport !== 'whep' || useImg || !wanted || !hlsUrl) return;
    if (whepPhase === 'UNAVAILABLE' || (whepPhase === 'RECONNECTING' && whepAttempt >= 2)) {
      setTransport('hls');
    }
  }, [transport, useImg, wanted, hlsUrl, whepPhase, whepAttempt]);

  // Prefer the CV engine's annotated live view; fall back to the backend's
  // own MJPEG mirror of the same source when the CV engine is not running.
  // With the backend detection view available, that view comes first.
  useEffect(() => {
    setMjpegAlive(false);
    if (detectionActive && ticket?.detectionUrl) {
      setMjpegSrc(ticket.detectionUrl);
      return;
    }
    setMjpegSrc(isMjpeg ? (ticket?.streamUrl || `/cvfeed/${camera.id}`) : null);
    // `isMjpeg` (i.e. ticket.streamType) MUST be a dependency: the body reads
    // it, and it is also what flips the player into <img> mode. Omitting it let
    // a ticket that changed transport (e.g. an MJPEG fallback issued for the
    // same camera/URL) leave mjpegSrc null while useImg was already true — a
    // permanently black player with no fallback.
  }, [ticket?.cameraId, ticket?.streamUrl, ticket?.detectionUrl, detectionActive, camera.id, isMjpeg]);

  const requestStream = async () => {
    setRequesting(true);
    setTicketError(null);
    try {
      const t = await cameraService.stream(camera.id);
      setTicket(t);
      const hls = whepUrlToHls(t.streamUrl);
      // No WebRTC, or a codec this browser cannot decode over it: step
      // straight onto the HLS compatibility stream instead of failing.
      if ((!rtcOk || !decodable) && hls) {
        setTransport('hls');
      } else if (!rtcOk && t.streamType !== 'MJPEG') {
        setTicketError(NO_RTC_ERROR);
        return;
      } else if (!decodable && t.streamType !== 'MJPEG') {
        setTicketError(NO_CODEC_ERROR);
        return;
      } else {
        setTransport('whep');
      }
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
    setTransport('whep');
    setDetectionFailed(false);
    setAutoRetryAt(null);
    pendingRetryRef.current = null;
    roundRef.current = 0;
    setRetryRound(0);
  };

  // Switching camera always releases the previous feed first.
  useEffect(() => {
    setWanted(false);
    setTicket(null);
    setTransport('whep');
    setTicketError(null);
    setDetectionFailed(false);
    setAutoRetryAt(null);
    pendingRetryRef.current = null;
    roundRef.current = 0;
    setRetryRound(0);
    if (autoRequest && camera.status !== 'OFFLINE') void requestStream();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [camera.id]);

  const noSource = Boolean(ticket && !ticket.streamUrl);
  const connecting =
    requesting || phase === 'CONNECTING' || phase === 'BUFFERING' || phase === 'AWAITING_KEYFRAME';
  const showVideo = wanted && Boolean(ticket?.streamUrl);
  const onAir = useImg ? mjpegAlive : phase === 'LIVE' || phase === 'STALLED';
  const showPoster = ticket?.poster ?? poster;
  /** Demo mode with no reachable gateway: show a clean demo frame, not an error. */
  const demoFeed =
    config.useMocks && !onAir && (noSource || Boolean(ticketError) || phase === 'UNAVAILABLE');

  // ------------------------------------------------------------------
  // Persistent auto-reconnect
  //
  // A feed the operator asked for keeps trying until it plays. The WHEP
  // and HLS hooks each retry internally with backoff (2s → 30s), and
  // this scheduler covers the gaps between them: a failed ticket fetch
  // (gateway 502, cold start) or a WebRTC verdict with no compatibility
  // stream falls back to a FRESH ticket, which restarts the ladder from
  // the top. Only a switched-off camera, an unconfigured source, or a
  // browser that cannot play this feed at all stops the loop.
  const [autoRetryAt, setAutoRetryAt] = useState<number | null>(null);
  const [retryRound, setRetryRound] = useState(0);
  const roundRef = useRef(0);
  const pendingRetryRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    if (onAir) {
      roundRef.current = 0;
      setRetryRound(0);
    }
  }, [onAir]);

  useLayoutEffect(() => {
    if (
      !wanted ||
      onAir ||
      connecting ||
      camera.status === 'OFFLINE' ||
      noSource ||
      (ticketError != null && FATAL_BROWSER_ERRORS.has(ticketError))
    ) {
      if (autoRetryAt != null) setAutoRetryAt(null);
      return;
    }
    const deadEnd =
      (transport === 'hls' && hlsPhase === 'UNAVAILABLE') ||
      (transport === 'whep' && whepPhase === 'UNAVAILABLE' && !hlsUrl) ||
      (ticketError != null && !requesting);
    if (!deadEnd || autoRetryAt != null) return;
    const delay = backoffDelay((roundRef.current += 1));
    pendingRetryRef.current = () => {
      pendingRetryRef.current = null;
      void requestStream();
    };
    setAutoRetryAt(Date.now() + delay);
    setRetryRound(roundRef.current);
    const t = setTimeout(() => {
      setAutoRetryAt(null);
      pendingRetryRef.current?.();
    }, delay);
    return () => {
      clearTimeout(t);
      pendingRetryRef.current = null;
    };
  }, [
    wanted,
    onAir,
    connecting,
    camera.status,
    noSource,
    ticketError,
    requesting,
    transport,
    hlsPhase,
    whepPhase,
    hlsUrl,
    autoRetryAt,
  ]);

  /** "Try now": run the scheduled auto-retry immediately, or nudge the active hook. */
  const tryNow = () => {
    if (autoRetryAt != null) {
      setAutoRetryAt(null);
      pendingRetryRef.current?.();
      return;
    }
    retryNow();
  };

  // The "Next try in X seconds" countdown needs a render every second while
  // a retry is pending (the WHEP stats interval does this for free on that
  // path; the HLS path and the ticket scheduler have none of their own).
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (phase !== 'RECONNECTING' && autoRetryAt == null) return;
    const id = window.setInterval(() => setTick((n) => n + 1), 1000);
    return () => window.clearInterval(id);
  }, [phase, autoRetryAt]);
  const nowMs = useMemo(() => Date.now(), [tick]);
  const nextTryAt = autoRetryAt ?? retryAt;

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
    <div className={cn('relative isolate overflow-hidden rounded border border-line bg-black', className)}>
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

        {showVideo && useImg && mjpegSrc && (
          <img
            src={mjpegSrc}
            alt={`${camera.name} — live view`}
            className={cn(
              'absolute inset-0 h-full w-full bg-black object-contain transition-opacity',
              mjpegAlive ? 'opacity-100' : 'opacity-0',
            )}
            decoding="async"
            onLoad={() => setMjpegAlive(true)}
            onError={() => {
              if (detectionActive && mjpegSrc === ticket?.detectionUrl) {
                setDetectionFailed(true); // detection view unavailable -> raw feed
              } else if (mjpegSrc !== ticket?.streamUrl && ticket?.streamUrl) {
                setMjpegSrc(ticket.streamUrl); // CV engine not running -> backend view
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
              'absolute inset-0 h-full w-full bg-black object-contain transition-opacity',
              onAir ? 'opacity-100' : 'opacity-0',
            )}
            autoPlay
            muted
            playsInline
            controls={onAir}
          />
        )}

        {showVideo && !useImg && !config.useMocks && (
          <DetectionOverlay videoRef={videoRef} cameraId={camera.id}
            active={aiBoxes && phase === 'LIVE'} onStatus={onAnprStatus} onError={setAnprError} />
        )}

        {showVideo && onAir && anprStatus && (countingPreview || anprStatus.traffic) && (
          <CountingOverlay preview={countingPreview ?? { config: anprStatus.traffic!.config, draft: false }}
            width={anprStatus.frame_width} height={anprStatus.frame_height} />
        )}
        <div className="scanline pointer-events-none absolute inset-0" aria-hidden />

        {/* On-screen display */}
        {/* Chips only: the source burns its own timestamp into the top-left corner. */}
        <div className="pointer-events-none absolute inset-x-0 top-0 z-10 flex items-center justify-end gap-2 bg-gradient-to-b from-black/60 to-transparent px-2.5 py-1.5">
          <span className="flex items-center gap-1.5">
            {(phase === 'LIVE' || (useImg && mjpegAlive && mjpegSignal)) && (
              <span className="chip border-critical/60 bg-critical/25 text-white">
                <CircleDot size={9} className="animate-pulse" aria-hidden /> {camera.streamType === 'FILE' ? 'RECORDED' : 'LIVE'}
              </span>
            )}
            {aiBoxes && onAir && !config.useMocks && (
              <span className="chip border-online/60 bg-black/70 text-white" title={detectionFailed ? 'Detection stream unavailable; showing raw video.' : anprError ?? anprStatus?.reason ?? 'Sampled plate recognition; playback stays independent'}>
                <ScanSearch size={9} aria-hidden />
                {anprStatusLabel(anprStatus, anprError, detectionFailed)}
              </span>
            )}
            {useImg && mjpegAlive && !mjpegSignal && (
              <span className="chip border-degraded/60 bg-degraded/25 text-white">
                <CircleDot size={9} aria-hidden /> NO LIVE SIGNAL
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
                  onClick={() => {
                    if (ticket?.streamUrl) restartChain();
                    else void requestStream();
                  }}
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
              ) : phase === 'RECONNECTING' || autoRetryAt != null ? (
                <>
                  <RotateCw size={18} className="mx-auto mb-1.5 animate-spin text-degraded" aria-hidden />
                  <p className="text-sm font-semibold text-white/90">
                    Video interrupted — reconnecting (try {autoRetryAt != null ? retryRound : attempt})
                  </p>
                  <p className="mt-1 text-2xs leading-relaxed text-white/65">
                    {autoRetryAt != null
                      ? 'The video stream is not responding. We are requesting it again automatically — you do not need to do anything.'
                      : 'The camera stopped sending video. We are reconnecting automatically — you do not need to do anything.'}
                    {nextTryAt
                      ? ` Next try in ${Math.max(0, Math.round((nextTryAt - nowMs) / 1000))} seconds.`
                      : ''}
                  </p>
                  <button
                    type="button"
                    className="btn-ghost btn-xs mt-3 border-white/30 text-white/85"
                    onClick={tryNow}
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
                    onClick={() => {
                      if (ticket?.streamUrl) restartChain();
                      else void requestStream();
                    }}
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
                      : 'Your browser will use the compatibility stream for this camera.'}
                  </p>
                </>
              )}
            </div>
            )}
          </div>
        )}
      </div>

      {showVideo && !embedded && (
        <div className="border-t border-line bg-surface-1 px-3 py-2">
          <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1.5">
            <span className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink-muted">
              {onAir ? (
                <span className="inline-flex items-center gap-1.5 font-medium text-ink">
                  <span
                    className={cn(
                      'h-2 w-2 rounded-full',
                      useImg && !mjpegSignal
                        ? 'bg-degraded'
                        : quality === 'Good'
                          ? 'bg-online'
                          : 'bg-degraded',
                    )}
                    aria-hidden
                  />
                  {useImg && !mjpegSignal
                    ? 'No live signal — source unreachable from this network'
                    : quality === 'Good'
                      ? 'Video is clear'
                      : 'Video quality is poor'}
                </span>
              ) : (
                <span>Connecting…</span>
              )}
              <span>Watching for {Math.round(stats.mediaTime)}s</span>
            </span>
            <span className="flex items-center gap-1.5">
              {!config.useMocks && (
                <button
                  type="button"
                  className="btn-ghost btn-xs"
                  onClick={() => setAiBoxes((v) => !v)}
                  aria-pressed={aiBoxes}
                  title="Read plates, notify and save to Vehicle Log. Up to 3 vehicles per sampled frame by default."
                >
                  <ScanSearch size={11} aria-hidden /> Plate detection: {aiBoxes ? 'On' : 'Off'}
                </button>
              )}
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

          {aiBoxes && !config.useMocks && (
            <p className="mt-1.5 text-2xs text-ink-muted" role="status">
              {anprError ?? anprStatus?.reason ?? 'Readable plates → notification + Vehicle Log. Repeated sightings are deduplicated; unclear reads need verification.'}
            </p>
          )}

          {showTechnical && (
            <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 border-t border-line pt-2 font-mono text-2xs text-ink-faint sm:grid-cols-4">
              <div>
                <dt className="inline">Transport </dt>
                <dd className="inline text-ink-muted">
                  {detectionActive ? 'MJPEG (AI detection)' : transport === 'hls' ? 'HLS (compatibility)' : (ticket?.streamType ?? 'WEBRTC')}
                </dd>
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
