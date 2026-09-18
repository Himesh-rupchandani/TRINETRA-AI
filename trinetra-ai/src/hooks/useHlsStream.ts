import { useCallback, useEffect, useRef, useState } from 'react';
import { backoffDelay } from '@/services/whepClient';

export type HlsPhase = 'IDLE' | 'CONNECTING' | 'RECONNECTING' | 'LIVE' | 'UNAVAILABLE';

/**
 * Map a Sentinel WHEP signalling URL onto its HLS playback URL (guide §1).
 * Same-origin /sentinel URLs stay same-origin (proxied); absolute gateway
 * URLs are rebuilt onto the default HTTP port where HLS is served.
 */
export function whepUrlToHls(url: string | null | undefined): string | null {
  if (!url) return null;
  const m = /\/stream\/([^/?#]+)\/whep/.exec(url);
  if (!m) return null;
  const hlsPath = `/live/stream/${m[1]}/index.m3u8`;
  if (/^https?:\/\//i.test(url)) {
    try {
      const u = new URL(url);
      return `${u.protocol}//${u.hostname}${hlsPath}`;
    } catch {
      return null;
    }
  }
  return url.startsWith('/sentinel') ? `/sentinel${hlsPath}` : hlsPath;
}

function nativeHls(el: HTMLVideoElement): boolean {
  try {
    return el.canPlayType('application/vnd.apple.mpegurl') !== '';
  } catch {
    return false;
  }
}

/**
 * Compatibility playback for restricted networks (guide §1: HLS is the
 * fallback when WebRTC/UDP cannot get through) and for codecs the browser
 * cannot decode over WebRTC. Safari plays HLS natively; every other browser
 * gets hls.js (lazy-loaded, only on this path).
 *
 * Fatal errors never stop the loop: the stream reconnects automatically
 * with backoff (2s → 30s) until playback starts — the operator opting out
 * (or the camera going offline) is the only off switch. This mirrors the
 * WHEP hook so the player shows the same "reconnecting (try N)" state.
 */
export function useHlsStream(url: string | null, active: boolean) {
  const [phase, setPhase] = useState<HlsPhase>('IDLE');
  const [error, setError] = useState<string | null>(null);
  const [mediaTime, setMediaTime] = useState(0);
  const [attempt, setAttempt] = useState(0);
  const [retryAt, setRetryAt] = useState<number | null>(null);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [retryNonce, setRetryNonce] = useState(0);
  const retryNow = useCallback(() => setRetryNonce((n) => n + 1), []);

  useEffect(() => {
    if (!active || !url) {
      setPhase('IDLE');
      setAttempt(0);
      setRetryAt(null);
      return;
    }
    let cancelled = false;
    let hls: { destroy: () => void } | null = null;
    let retryTimer: ReturnType<typeof setTimeout> | null = null;
    let timeTimer: ReturnType<typeof setInterval> | null = null;
    let attempts = 0;
    const cleanupFns: Array<() => void> = [];
    setAttempt(0);
    setRetryAt(null);

    // Drop the previous attempt's listeners/hls.js instance before re-arming.
    // Retries run forever, so without this the video element would accumulate
    // one duplicate `playing`/`error` listener pair per retry.
    const stopCurrent = () => {
      for (const fn of cleanupFns.splice(0)) {
        try {
          fn();
        } catch {
          /* noop */
        }
      }
      if (hls) {
        try {
          hls.destroy();
        } catch {
          /* already gone */
        }
        hls = null;
      }
    };

    const start = () => {
      const v = videoRef.current;
      // A previous WebRTC session leaves srcObject behind, which wins over
      // src — clear it so the playlist actually loads.
      if (v) v.srcObject = null;
      if (!v) {
        fail('No video element to play into.');
        return;
      }
      stopCurrent();
      setRetryAt(null); // attempt in progress — hide the countdown
      if (nativeHls(v)) startNative(v);
      else void startHlsJs(v);
    };

    // Fatal errors never park the player: reconnect with the same backoff
    // ladder as the WHEP path (~2s, 4s, 8s … capped at 30s) until playback
    // starts. Playlists 404 frequently at session start, and the upstream
    // gateway may restart — so "try again" is automatic, not manual.
    const fail = (message: string) => {
      if (cancelled) return;
      attempts += 1;
      const delay = backoffDelay(attempts);
      setError(message);
      setAttempt(attempts);
      setPhase('RECONNECTING');
      setRetryAt(Date.now() + delay);
      retryTimer = setTimeout(() => {
        if (!cancelled) start();
      }, delay);
    };

    const goLive = () => {
      if (cancelled) return;
      setPhase('LIVE');
      setAttempt(0); // it is playing — reset the ladder
      setRetryAt(null);
      const v = videoRef.current;
      if (v) {
        timeTimer = setInterval(() => {
          if (!cancelled) setMediaTime(v.currentTime || 0);
        }, 1000);
      }
    };

    const startNative = (v: HTMLVideoElement) => {
      setPhase('CONNECTING');
      const onPlaying = () => goLive();
      const onError = () => fail('The compatibility stream could not be played.');
      v.addEventListener('playing', onPlaying);
      v.addEventListener('error', onError);
      v.src = url;
      v.play().catch(() => undefined);
      cleanupFns.push(() => {
        v.removeEventListener('playing', onPlaying);
        v.removeEventListener('error', onError);
        v.removeAttribute('src');
        v.load();
      });
    };

    const startHlsJs = async (v: HTMLVideoElement) => {
      setPhase('CONNECTING');
      let HlsMod: typeof import('hls.js');
      try {
        HlsMod = await import('hls.js');
      } catch {
        fail('The compatibility player could not be loaded.');
        return;
      }
      if (cancelled) return;
      const Hls = HlsMod.default;
      if (!Hls.isSupported()) {
        fail('This browser cannot play the compatibility stream.');
        return;
      }
      const inst = new Hls({ maxBufferLength: 15, liveSyncDurationCount: 2 });
      hls = inst;
      inst.on(Hls.Events.MANIFEST_PARSED, () => {
        v.play()
          .then(() => goLive())
          .catch(() => goLive());
      });
      inst.on(Hls.Events.ERROR, (_e, d) => {
        const data = d as { fatal?: boolean };
        if (!data.fatal) return;
        try {
          inst.destroy();
        } catch {
          /* already gone */
        }
        hls = null;
        fail('The compatibility stream dropped.');
      });
      inst.loadSource(url);
      inst.attachMedia(v);
    };

    start();
    return () => {
      cancelled = true;
      if (retryTimer) clearTimeout(retryTimer);
      if (timeTimer) clearInterval(timeTimer);
      cleanupFns.forEach((fn) => {
        try {
          fn();
        } catch {
          /* noop */
        }
      });
      if (hls) {
        try {
          hls.destroy();
        } catch {
          /* noop */
        }
        hls = null;
      }
    };
  }, [url, active, retryNonce]);

  return { videoRef, phase, error, mediaTime, attempt, retryAt, retryNow };
}
