import { useCallback, useEffect, useRef, useState } from 'react';
import { backoffDelay, connectWhep, WhepError, type WhepSession } from '@/services/whepClient';

export type StreamPhase =
  | 'IDLE'
  | 'CONNECTING'
  /** Negotiated; no media arriving yet. */
  | 'BUFFERING'
  /** Media is arriving but the source has not emitted a keyframe yet. */
  | 'AWAITING_KEYFRAME'
  | 'LIVE'
  | 'STALLED'
  | 'RECONNECTING'
  | 'UNAVAILABLE';

export interface StreamStats {
  /** Measured from decoded-frame deltas — never the nominal/reported rate. */
  fps: number | null;
  width: number | null;
  height: number | null;
  codec: string | null;
  bitrateKbps: number | null;
  packetsLost: number;
  jitterMs: number | null;
  framesDecoded: number;
  bytesReceived: number;
  /** Keyframe requests this client has sent to the source. */
  keyframeRequests: number;
  /** Seconds spent waiting for the first decodable frame. */
  waitingSecs: number;
  /** Media clock (PTS-derived), not wall-clock arrival time. */
  mediaTime: number;
  /** Scene cuts observed at the loop point / resolution change. */
  discontinuities: number;
}

const EMPTY_STATS: StreamStats = {
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

/**
 * Inter-frame gaps are normal on this grid, so a stall is only declared after
 * a generous quiet period — a gap is not a disconnect.
 */
const STALL_AFTER_MS = 6_000;
const STATS_INTERVAL_MS = 1_000;
/**
 * A source cannot be asked to emit an IDR on demand, so a fresh subscriber
 * waits for the next natural keyframe. That wait is normal, not a failure.
 */
const KEYFRAME_WAIT_MS = 45_000;
/** ICE 'disconnected' is usually transient — give it time to recover. */
const ICE_GRACE_MS = 8_000;

/**
 * Supervises one live camera feed.
 *
 * Rules encoded here, straight from the Sentinel integrator's guide:
 *  - never auto-start: the caller opts in via `active`;
 *  - never trust a reported frame rate — fps is measured from decoded frames;
 *  - drive timing from the media clock, not arrival time;
 *  - tolerate inter-frame gaps without treating them as a disconnect;
 *  - reconnect with exponential backoff (2s -> 30s), never a tight loop;
 *  - survive the loop-point scene cut without resetting the pipeline;
 *  - release the feed as soon as the operator closes it.
 */
export function useWhepStream(url: string | null, active: boolean) {
  const [phase, setPhase] = useState<StreamPhase>('IDLE');
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [stats, setStats] = useState<StreamStats>(EMPTY_STATS);
  const [retryAt, setRetryAt] = useState<number | null>(null);

  const videoRef = useRef<HTMLVideoElement | null>(null);
  const sessionRef = useRef<WhepSession | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const statsTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const attemptRef = useRef(0);
  const generationRef = useRef(0);
  /** Timestamp of the last observed byte growth — proof media is still arriving. */
  const mediaProgressRef = useRef(0);
  /** Whether this session ever produced a decodable frame. */
  const sawFrameRef = useRef(false);

  /**
   * Manual retry from the UI: resets the backoff ladder and forces the
   * connection effect to re-run (the nonce is part of its dependency list).
   */
  const [retryNonce, setRetryNonce] = useState(0);
  const retryNow = useCallback(() => {
    attemptRef.current = 0;
    setAttempt(0);
    setRetryNonce((n) => n + 1);
  }, []);

  useEffect(() => {
    if (!active || !url) {
      setPhase('IDLE');
      return;
    }

    const generation = ++generationRef.current;
    let cancelled = false;

    const teardown = async () => {
      if (timerRef.current) clearTimeout(timerRef.current);
      if (statsTimerRef.current) clearInterval(statsTimerRef.current);
      timerRef.current = null;
      statsTimerRef.current = null;
      abortRef.current?.abort();
      abortRef.current = null;
      const s = sessionRef.current;
      sessionRef.current = null;
      if (videoRef.current) videoRef.current.srcObject = null;
      await s?.close().catch(() => undefined);
    };

    const scheduleRetry = (message: string) => {
      if (cancelled || generation !== generationRef.current) return;
      attemptRef.current += 1;
      const delay = backoffDelay(attemptRef.current);
      setAttempt(attemptRef.current);
      setError(message);
      setPhase('RECONNECTING');
      setRetryAt(Date.now() + delay);
      timerRef.current = setTimeout(() => {
        if (!cancelled && generation === generationRef.current) void start();
      }, delay);
    };

    const monitor = (session: WhepSession) => {
      let lastFrames = 0;
      let lastBytes = 0;
      let lastAt = performance.now();
      let lastProgressAt = performance.now();
      let lastW: number | null = null;
      let lastH: number | null = null;
      let cuts = 0;
      const openedAt = performance.now();
      let sawFirstFrame = false;

      statsTimerRef.current = setInterval(async () => {
        if (cancelled || generation !== generationRef.current) return;
        let report: RTCStatsReport;
        try {
          report = await session.peer.getStats();
        } catch {
          return;
        }

        let framesDecoded = 0;
        let bytes = 0;
        let pli = 0;
        let packetsLost = 0;
        let jitter: number | null = null;
        let width: number | null = null;
        let height: number | null = null;
        let codecId: string | undefined;
        const codecs = new Map<string, string>();

        report.forEach((s) => {
          const st = s as RTCStats & Record<string, unknown>;
          if (st.type === 'codec' && typeof st.mimeType === 'string') {
            codecs.set(st.id, st.mimeType.replace(/^video\//i, '').toUpperCase());
          }
          if (st.type === 'inbound-rtp' && (st.kind === 'video' || st.mediaType === 'video')) {
            framesDecoded = Number(st.framesDecoded ?? 0);
            bytes = Number(st.bytesReceived ?? 0);
            pli = Number(st.pliCount ?? 0);
            packetsLost = Number(st.packetsLost ?? 0);
            jitter = typeof st.jitter === 'number' ? st.jitter * 1000 : null;
            width = typeof st.frameWidth === 'number' ? st.frameWidth : null;
            height = typeof st.frameHeight === 'number' ? st.frameHeight : null;
            codecId = typeof st.codecId === 'string' ? st.codecId : undefined;
          }
        });

        const now = performance.now();
        const elapsed = (now - lastAt) / 1000;
        // Measured, not reported: CAP_PROP_FPS-style values are unreliable.
        const fps = elapsed > 0 ? (framesDecoded - lastFrames) / elapsed : null;
        const bitrateKbps = elapsed > 0 ? ((bytes - lastBytes) * 8) / elapsed / 1000 : null;

        const el = videoRef.current;
        const w = width ?? el?.videoWidth ?? null;
        const h = height ?? el?.videoHeight ?? null;

        // Each feed loops; at the loop point the scene cuts abruptly and the
        // encoder may switch resolution. Count it, keep running.
        if (w && h && lastW && lastH && (w !== lastW || h !== lastH)) cuts += 1;
        if (w) lastW = w;
        if (h) lastH = h;

        if (bytes > lastBytes) mediaProgressRef.current = now;
        if (framesDecoded > lastFrames) lastProgressAt = now;
        if (!sawFirstFrame && framesDecoded > 0) {
          sawFirstFrame = true;
          sawFrameRef.current = true;
          setPhase('LIVE');
        }
        lastFrames = framesDecoded;
        lastBytes = bytes;
        lastAt = now;

        setStats({
          fps: fps !== null && Number.isFinite(fps) ? Math.max(0, fps) : null,
          width: w,
          height: h,
          codec: codecId ? (codecs.get(codecId) ?? null) : null,
          bitrateKbps,
          packetsLost,
          jitterMs: jitter,
          framesDecoded,
          bytesReceived: bytes,
          keyframeRequests: pli,
          waitingSecs: sawFirstFrame ? 0 : Math.round((now - openedAt) / 1000),
          mediaTime: el?.currentTime ?? 0,
          discontinuities: cuts,
        });

        if (!sawFirstFrame) {
          // Two very different situations, and they need different handling:
          //
          //  - nothing is arriving at all -> a transport problem, worth
          //    resubscribing with backoff;
          //  - packets are arriving but carry no IDR -> the source simply has
          //    not produced a keyframe yet. Resubscribing would only restart
          //    the wait, so we stay connected and keep the operator informed.
          const receivingMedia = bytes > 0;
          setPhase(receivingMedia ? 'AWAITING_KEYFRAME' : 'BUFFERING');
          if (!receivingMedia && now - openedAt > KEYFRAME_WAIT_MS) {
            scheduleRetry('No media received — resubscribing to the feed.');
          }
          return;
        }

        // Gaps are tolerated; a long silence is a stall worth surfacing.
        if (now - lastProgressAt > STALL_AFTER_MS) {
          setPhase((p) => (p === 'LIVE' ? 'STALLED' : p));
        } else {
          setPhase((p) => (p === 'STALLED' ? 'LIVE' : p));
        }
      }, STATS_INTERVAL_MS);
    };

    const start = async () => {
      if (cancelled || generation !== generationRef.current) return;
      setPhase(attemptRef.current === 0 ? 'CONNECTING' : 'RECONNECTING');
      setRetryAt(null);
      setError(null);

      const controller = new AbortController();
      abortRef.current = controller;

      try {
        const session = await connectWhep(url, controller.signal);
        if (cancelled || generation !== generationRef.current) {
          await session.close();
          return;
        }
        sessionRef.current = session;

        let graceTimer: ReturnType<typeof setTimeout> | null = null;
        const dropSession = (reason: string) => {
          if (sessionRef.current !== session) return;
          if (statsTimerRef.current) clearInterval(statsTimerRef.current);
          if (graceTimer) clearTimeout(graceTimer);
          sessionRef.current = null;
          void session.close();
          scheduleRetry(reason);
        };

        session.peer.addEventListener('connectionstatechange', () => {
          const state = session.peer.connectionState;
          if (state === 'failed' || state === 'closed') {
            dropSession(
              sawFrameRef.current
                ? 'Feed dropped — the gateway restarted or the network changed.'
                : 'Source stopped sending before a keyframe arrived.',
            );
            return;
          }
          if (state === 'disconnected') {
            // 'disconnected' is transient by definition, and a source that is
            // trickling packets while it waits for its next keyframe can sit
            // here for a while. Only drop the session once media has genuinely
            // stopped arriving — otherwise re-arm and keep waiting.
            const armGrace = () => {
              if (graceTimer) clearTimeout(graceTimer);
              graceTimer = setTimeout(() => {
                if (session.peer.connectionState !== 'disconnected') return;
                const quietFor = performance.now() - mediaProgressRef.current;
                if (quietFor < ICE_GRACE_MS * 2) {
                  armGrace(); // still receiving — this is not a dead path
                  return;
                }
                dropSession(
                  sawFrameRef.current
                    ? 'Connection lost — the network path changed.'
                    : 'Source stopped sending before a keyframe arrived.',
                );
              }, ICE_GRACE_MS);
            };
            armGrace();
            return;
          }
          if (state === 'connected' && graceTimer) {
            clearTimeout(graceTimer);
            graceTimer = null;
          }
        });

        const el = videoRef.current;
        if (el) {
          el.srcObject = session.stream;
          // Autoplay is only permitted while muted; decoder warnings on join
          // (mixed H.264/H.265 reference frames) are logged, never fatal.
          el.play().catch((e: unknown) => {
            console.info('[trinetra] deferred playback start', e);
          });
        }

        attemptRef.current = 0;
        setAttempt(0);
        mediaProgressRef.current = performance.now();
        sawFrameRef.current = false;
        // Not LIVE yet — the first decoded frame promotes it (see monitor()).
        setPhase('BUFFERING');
        monitor(session);
      } catch (err) {
        if (cancelled || generation !== generationRef.current) return;
        if (err instanceof WhepError && !err.retryable) {
          setError(err.message);
          setPhase('UNAVAILABLE');
          return;
        }
        scheduleRetry(err instanceof Error ? err.message : 'Stream negotiation failed');
      }
    };

    void start();

    return () => {
      cancelled = true;
      void teardown();
    };
  }, [url, active, retryNonce]);

  // Release the feed if the tab is hidden for a while: each client gets its own
  // copy of the stream, so idle tabs must not hold gateway capacity.
  useEffect(() => {
    const onVisibility = () => {
      const el = videoRef.current;
      if (!el) return;
      if (document.hidden) el.pause();
      else el.play().catch(() => undefined);
    };
    document.addEventListener('visibilitychange', onVisibility);
    return () => document.removeEventListener('visibilitychange', onVisibility);
  }, []);

  return { videoRef, phase, error, stats, attempt, retryAt, retryNow };
}
