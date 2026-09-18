import { useCallback, useEffect, useRef, useState, type RefObject } from 'react';
import type { Camera } from '@/types';
import { cameraService } from '@/services/cameraService';
import { backoffDelay, connectWhep, type WhepSession } from '@/services/whepClient';
import { whepUrlToHls } from '@/hooks/useHlsStream';
import { useInViewport } from '@/hooks/useInViewport';
import { canDecodeOverWebRtc, webRtcAvailable } from '@/lib/mediaSupport';
import { cameraStill } from '@/utils/mediaAssets';
import { config } from '@/lib/config';

/**
 * LIVE PREVIEW FOR A CAMERA CARD.
 *
 * The registry grid used to render a grey camera icon for every tile — the
 * streams only started after an operator clicked through to the full player.
 * This hook gives each card the same live picture, but under control-room
 * rules so that showing 30 tiles does not cost 30 simultaneous feeds:
 *
 *  - a preview only runs while its card is actually on screen (viewport gate);
 *  - it starts automatically — the operator does not have to click anything;
 *  - transport follows the same ladder as the full player: WebRTC (WHEP)
 *    first, the HLS compatibility stream when WebRTC cannot get through, and
 *    the backend's AI detection view (MJPEG, green boxes) when it is offered
 *    for that camera;
 *  - a browser that cannot decode the camera's codec at all is reported as
 *    such instead of retry-looping forever;
 *  - failures back off (2s → 30s) a bounded number of times, then either fall
 *    back to the demo frame (mock mode) or show an honest "not available"
 *    tile with a manual retry;
 *  - mock mode keeps a clearly labelled synthetic frame, never a fake "LIVE".
 */

export type PreviewPhase =
  /** Nothing requested (off screen, disabled, or switched off by config). */
  | 'IDLE'
  | 'CONNECTING'
  | 'LIVE'
  | 'RECONNECTING'
  /** Mock mode only: a labelled synthetic frame stands in for the feed. */
  | 'DEMO'
  /** Camera switched off / nothing published for it. */
  | 'OFFLINE'
  /** This browser (or the gateway) cannot play this feed at all. */
  | 'BLOCKED';

export type PreviewTransport = 'WEBRTC' | 'HLS' | 'MJPEG' | 'STILL' | null;

/** Same wording as the full player, so the two views never contradict. */
const NO_RTC = 'This browser cannot play live video. Please use Chrome, Edge or Safari.';
const NO_CODEC = 'This camera records in a format your browser cannot play.';
const UNAVAILABLE = 'Live view unavailable for this camera right now.';
const NO_SIGNAL = 'No live signal from this camera.';
const NO_SOURCE = 'No video source is set up for this camera yet.';
/** Steady-state cadence of the live-signal probe (ms). */
const SIGNAL_POLL_MS = 8_000;
/** A first miss is re-checked sooner than that before it becomes a verdict. */
const SIGNAL_RECHECK_MS = 2_000;

/** Media attempts before a tile stops retrying and offers a manual retry. */
const MAX_ATTEMPTS = 6;
/** WebRTC attempts before stepping down to the HLS compatibility stream. */
const WHEP_ATTEMPTS_BEFORE_HLS = 2;

interface Plan {
  kind: 'IDLE' | 'DEMO' | 'OFFLINE' | 'BLOCKED' | 'MJPEG' | 'WEBRTC';
  /** MJPEG image URL, or the WebRTC signalling URL. */
  url?: string;
  /** HLS compatibility URL for the same camera (WHEP step-down). */
  hlsUrl?: string | null;
  /** Mock-mode synthetic frame — shown as poster and as last-resort fallback. */
  still?: string | null;
  /** True when this is the backend's annotated vehicle-detection view. */
  detection?: boolean;
  reason?: string;
}

/**
 * Append the manual-retry counter to a stream URL.
 *
 * A browser does not re-request an <img> whose src string has not changed, so
 * "Try live" on an MJPEG tile would otherwise re-render the same dead picture
 * forever. The backend ignores unknown query parameters; the counter only has
 * to be unique per retry.
 */
function withRetryMarker(url: string, nonce: number): string {
  if (!nonce) return url;
  return `${url}${url.includes('?') ? '&' : '?'}_r=${nonce}`;
}

function nativeHls(el: HTMLVideoElement): boolean {
  try {
    return el.canPlayType('application/vnd.apple.mpegurl') !== '';
  } catch {
    return false;
  }
}

/**
 * Attach the HLS compatibility stream (native on Safari, hls.js elsewhere).
 * Resolves with a disposer; `onFatal` reports stream failure to the caller.
 */
async function attachHls(
  el: HTMLVideoElement,
  url: string,
  onFatal: () => void,
): Promise<() => void> {
  if (nativeHls(el)) {
    el.src = url;
    void el.play().catch(() => undefined);
    return () => {
      el.removeAttribute('src');
      el.load();
    };
  }
  // hls.js is heavy: it is only fetched on this path (as in the full player).
  const mod = await import('hls.js');
  const Hls = mod.default;
  if (!Hls.isSupported()) throw new Error(UNAVAILABLE);
  const inst = new Hls({ maxBufferLength: 15, liveSyncDurationCount: 2 });
  inst.on(Hls.Events.MANIFEST_PARSED, () => void el.play().catch(() => undefined));
  inst.on(Hls.Events.ERROR, (_evt, data) => {
    if ((data as { fatal?: boolean }).fatal) onFatal();
  });
  inst.loadSource(url);
  inst.attachMedia(el);
  return () => {
    try {
      inst.destroy();
    } catch {
      /* already gone */
    }
  };
}

export interface CameraPreviewState {
  /** Attach to the tile that holds the preview (drives the viewport gate). */
  containerRef: RefObject<HTMLDivElement | null>;
  /** Attach to the <video> element when `needsVideo` is true. */
  videoRef: RefObject<HTMLVideoElement | null>;
  phase: PreviewPhase;
  transport: PreviewTransport;
  /** MJPEG (AI detection view) or mock still to render in an <img>. */
  imageSrc: string | null;
  /** Mock-mode frame used as poster while connecting / as fallback. */
  posterSrc: string | null;
  /** True while the preview is real video (WebRTC/HLS/MJPEG) and playing. */
  isLive: boolean;
  /** True when the mock synthetic frame is what the operator is looking at. */
  synthetic: boolean;
  /** Render a <video> element (WebRTC/HLS plan is in flight). */
  needsVideo: boolean;
  /** True when a manual retry can help (capability failures cannot). */
  retryable: boolean;
  /** True when the picture is the server-annotated detection view. */
  detectionView: boolean;
  /**
   * True for file-backed cameras (uploaded clips / demo footage). Their
   * picture is a recording the backend replays, so the tile says so instead
   * of badging it LIVE.
   */
  recorded: boolean;
  attempt: number;
  error: string | null;
  /** Called by the <img> once an MJPEG view has painted a frame. */
  markAlive: () => void;
  /** Called by the <img> when an MJPEG view fails to load. */
  markFailed: () => void;
  retryNow: () => void;
}

export function useCameraPreview(camera: Camera, enabled = true): CameraPreviewState {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const visible = useInViewport(containerRef, enabled);

  const [plan, setPlan] = useState<Plan>({ kind: 'IDLE' });
  const [phase, setPhase] = useState<PreviewPhase>('IDLE');
  const [attempt, setAttempt] = useState(0);
  const [error, setError] = useState<string | null>(null);
  /** WHEP proved unusable for this tile → play the HLS compatibility stream. */
  const [useHls, setUseHls] = useState(false);
  const [retryNonce, setRetryNonce] = useState(0);
  /** Retry budget spent — release the media and settle on a terminal state. */
  const [giveUp, setGiveUp] = useState(false);
  const [imgState, setImgState] = useState<'CONNECTING' | 'ALIVE' | 'FAILED'>('CONNECTING');
  /** MJPEG views can answer 200 while the source delivers no frames at all. */
  const [signalLost, setSignalLost] = useState(false);

  /* ------------------------------------------------------------------ */
  /* 1. What should this tile play? (ticket + transport ladder)          */
  /* ------------------------------------------------------------------ */
  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let tries = 0;
    const still = config.useMocks ? cameraStill(camera.id) : null;

    setAttempt(0);
    setError(null);
    setUseHls(false);
    setGiveUp(false);
    setImgState('CONNECTING');
    setSignalLost(false);

    /** Mock mode degrades to a clean demo frame instead of an error tile. */
    const fallback = (reason?: string) => {
      if (still) {
        setPlan({ kind: 'DEMO', still, reason });
        setPhase('DEMO');
        return;
      }
      setPlan({ kind: 'OFFLINE', reason });
      setPhase(camera.status === 'OFFLINE' ? 'OFFLINE' : 'BLOCKED');
      setError(reason ?? null);
    };

    // The viewport gate: nothing is requested for a card nobody is looking at.
    if (!enabled || !visible) {
      setPlan({ kind: 'IDLE' });
      setPhase('IDLE');
      return;
    }
    if (camera.status === 'OFFLINE' || camera.status === 'NOT_CONFIGURED') {
      const reason = camera.status === 'NOT_CONFIGURED' ? NO_SOURCE : undefined;
      setPlan({ kind: 'OFFLINE', reason });
      setPhase('OFFLINE');
      setError(reason ?? null);
      return;
    }
    if (!config.liveStreams) {
      fallback();
      return;
    }

    const load = async () => {
      try {
        // Tickets come from the backend in both mock and connected mode, so
        // the tile follows exactly the same route as the full player.
        const ticket = await cameraService.stream(camera.id);
        if (cancelled) return;
        if (!ticket.streamUrl) {
          // Registry row without an authorized source: say so, do not retry.
          fallback(NO_SOURCE);
          return;
        }
        if (ticket.detectionUrl) {
          // Real-time vehicle detection view (green boxes) when offered.
          setPlan({
            kind: 'MJPEG',
            url: withRetryMarker(ticket.detectionUrl, retryNonce),
            still,
            detection: true,
          });
          setPhase('CONNECTING');
          return;
        }
        if (ticket.streamType === 'MJPEG') {
          setPlan({
            kind: 'MJPEG',
            url: withRetryMarker(ticket.streamUrl, retryNonce),
            still: null,
          });
          setPhase('CONNECTING');
          return;
        }

        const hls = whepUrlToHls(ticket.streamUrl);
        if (!webRtcAvailable() || !canDecodeOverWebRtc(camera.codec)) {
          if (hls) {
            // Step straight onto HLS: a codec WebRTC cannot carry is still
            // playable through the compatibility stream.
            setPlan({ kind: 'WEBRTC', url: hls, hlsUrl: hls, still });
            setUseHls(true);
            setPhase('CONNECTING');
            return;
          }
          setPlan({
            kind: 'BLOCKED',
            reason: !webRtcAvailable() ? NO_RTC : NO_CODEC,
            still,
          });
          setPhase('BLOCKED');
          setError(!webRtcAvailable() ? NO_RTC : NO_CODEC);
          return;
        }
        setPlan({ kind: 'WEBRTC', url: ticket.streamUrl, hlsUrl: hls, still });
        setPhase('CONNECTING');
      } catch (e: unknown) {
        if (cancelled) return;
        tries += 1;
        const reason = e instanceof Error ? e.message : UNAVAILABLE;
        // Gateway cold starts and expired tickets are transient — retry with
        // the shared backoff ladder, then report honestly.
        if (tries < MAX_ATTEMPTS) {
          setPhase('RECONNECTING');
          setError(reason);
          setAttempt(tries);
          timer = setTimeout(() => {
            if (!cancelled) void load();
          }, backoffDelay(tries));
          return;
        }
        fallback(reason);
      }
    };

    void load();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
    // `retryNonce` re-arms a manual retry; `visible` gates on the viewport.
  }, [camera.id, camera.status, camera.codec, enabled, visible, retryNonce]);

  /* ------------------------------------------------------------------ */
  /* 2. Media element supervision (WebRTC / HLS)                         */
  /* ------------------------------------------------------------------ */
  useEffect(() => {
    if (plan.kind !== 'WEBRTC' || giveUp) return;
    const el = videoRef.current;
    if (!el) return; // the element mounts with the plan's first render
    const url = (useHls ? plan.hlsUrl : plan.url) ?? null;
    if (!url) {
      setPhase(plan.still ? 'DEMO' : 'BLOCKED');
      setError(UNAVAILABLE);
      return;
    }

    let cancelled = false;
    let session: WhepSession | null = null;
    let dispose: (() => void) | null = null;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let tries = 0;

    /** A previous WebRTC session leaves srcObject behind, which wins over src. */
    const dropMedia = () => {
      if (dispose) {
        try {
          dispose();
        } catch {
          /* already gone */
        }
        dispose = null;
      }
      if (session) {
        void session.close().catch(() => undefined);
        session = null;
      }
      el.srcObject = null;
    };

    const goLive = () => {
      if (cancelled) return;
      tries = 0;
      setAttempt(0);
      setError(null);
      setPhase('LIVE');
    };
    const onPlaying = () => goLive();
    el.addEventListener('playing', onPlaying);

    const fail = (reason: string) => {
      if (cancelled) return;
      tries += 1;
      setAttempt(tries);
      dropMedia();
      // WebRTC produced no picture at all → try the compatibility stream once.
      if (!useHls && plan.hlsUrl && tries > WHEP_ATTEMPTS_BEFORE_HLS) {
        setUseHls(true);
        return;
      }
      if (tries >= MAX_ATTEMPTS) {
        // Giving up flips `giveUp`, which tears the media down through this
        // effect's cleanup — a dead tile must not hold a peer connection open.
        setGiveUp(true);
        if (plan.still) setPhase('DEMO');
        else {
          setPhase('BLOCKED');
          setError(reason);
        }
        return;
      }
      setPhase('RECONNECTING');
      setError(reason);
      timer = setTimeout(() => {
        if (!cancelled) void connect();
      }, backoffDelay(tries));
    };

    const connect = async () => {
      if (cancelled) return;
      setPhase('CONNECTING');
      try {
        if (useHls) {
          dispose = await attachHls(el, url, () => fail(UNAVAILABLE));
          return; // 'playing' promotes the tile to LIVE
        }
        const next = await connectWhep(url);
        if (cancelled) {
          void next.close().catch(() => undefined);
          return;
        }
        session = next;
        el.srcObject = next.stream;
        void el.play().catch(() => undefined);
      } catch (e: unknown) {
        fail(e instanceof Error ? e.message : UNAVAILABLE);
      }
    };

    void connect();
    return () => {
      cancelled = true;
      el.removeEventListener('playing', onPlaying);
      if (timer) clearTimeout(timer);
      dropMedia();
    };
  }, [plan, useHls, retryNonce, giveUp]);

  const markAlive = useCallback(() => setImgState('ALIVE'), []);
  const markFailed = useCallback(() => setImgState('FAILED'), []);

  /* An MJPEG view that never paints must not leave the tile "connecting". */
  useEffect(() => {
    if (plan.kind !== 'MJPEG' || imgState !== 'FAILED') return;
    if (plan.still) setPhase('DEMO');
    else {
      setPhase('BLOCKED');
      setError(UNAVAILABLE);
    }
  }, [plan, imgState]);
  useEffect(() => {
    if (plan.kind === 'MJPEG' && imgState === 'ALIVE') {
      setPhase('LIVE');
      setError(null);
    }
  }, [plan, imgState]);

  /**
   * An MJPEG view answers with a stream even when the camera source is dead —
   * that is the backend's "NO SIGNAL" placeholder, a 200 response that would
   * otherwise be badged LIVE. The full player probes the signal for exactly
   * this reason; the grid does the same, under two rules that keep it honest
   * in both directions:
   *
   *  - the probe only starts once this tile has actually painted a frame, so
   *    it can never mistake "my own request has not started yet" for a dead
   *    camera (the backend only counts frames seen in the last 6 seconds);
   *  - one bad probe is not a verdict — the first miss is re-checked two
   *    seconds later, and only then does the tile stop claiming to be live.
   *    A camera that comes back flips the tile straight back to live.
   */
  useEffect(() => {
    if (plan.kind !== 'MJPEG' || !visible || imgState !== 'ALIVE') return;
    let stop = false;
    let timer: number | null = null;
    let misses = 0;

    const schedule = (ms: number) => {
      timer = window.setTimeout(() => void check(), ms);
    };
    const check = async () => {
      let ok = false;
      try {
        ok = await cameraService.signal(camera.id);
      } catch {
        /* transient probe failure — keep the current verdict and re-check */
        if (!stop) schedule(SIGNAL_POLL_MS);
        return;
      }
      if (stop) return;
      misses = ok ? 0 : misses + 1;
      setSignalLost(misses >= 2);
      schedule(!ok && misses === 1 ? SIGNAL_RECHECK_MS : SIGNAL_POLL_MS);
    };

    // Probe as soon as this tile has painted: the backend has already counted
    // the frame that produced this paint, so a live camera answers true here.
    schedule(250);
    return () => {
      stop = true;
      if (timer !== null) window.clearTimeout(timer);
    };
  }, [plan.kind, visible, imgState, camera.id]);

  const retryNow = useCallback(() => {
    setAttempt(0);
    setError(null);
    setUseHls(false);
    setGiveUp(false);
    setImgState('CONNECTING');
    setSignalLost(false);
    setRetryNonce((n) => n + 1);
  }, []);

  const isMjpeg = plan.kind === 'MJPEG' && imgState !== 'FAILED';
  const noSignal = isMjpeg && signalLost;
  const demoTile = plan.kind === 'DEMO' || phase === 'DEMO';
  const transport: PreviewTransport =
    plan.kind === 'WEBRTC'
      ? useHls
        ? 'HLS'
        : 'WEBRTC'
      : isMjpeg
        ? 'MJPEG'
        : demoTile
          ? 'STILL'
          : null;

  return {
    containerRef,
    videoRef,
    // A dead source never reaches the UI as LIVE, whatever the transport.
    phase: noSignal ? 'BLOCKED' : phase,
    transport,
    imageSrc: isMjpeg ? (plan.url ?? null) : demoTile ? (plan.still ?? null) : null,
    posterSrc: plan.still ?? null,
    isLive: phase === 'LIVE' && !noSignal,
    synthetic: demoTile,
    needsVideo: plan.kind === 'WEBRTC' && !demoTile,
    retryable: error !== NO_RTC && error !== NO_CODEC,
    detectionView: plan.kind === 'MJPEG' && plan.detection === true,
    recorded: (camera.streamType ?? '').toUpperCase() === 'FILE',
    attempt,
    error: noSignal ? NO_SIGNAL : (error ?? plan.reason ?? null),
    markAlive,
    markFailed,
    retryNow,
  };
}
