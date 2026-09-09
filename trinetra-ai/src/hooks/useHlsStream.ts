import { useCallback, useEffect, useRef, useState } from 'react';

export type HlsPhase = 'IDLE' | 'CONNECTING' | 'LIVE' | 'UNAVAILABLE';

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
 * gets hls.js (lazy-loaded, only on this path). One quiet re-attempt on
 * fatal errors, then UNAVAILABLE — the player decides what comes next.
 */
export function useHlsStream(url: string | null, active: boolean) {
  const [phase, setPhase] = useState<HlsPhase>('IDLE');
  const [error, setError] = useState<string | null>(null);
  const [mediaTime, setMediaTime] = useState(0);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [retryNonce, setRetryNonce] = useState(0);
  const retryNow = useCallback(() => setRetryNonce((n) => n + 1), []);

  useEffect(() => {
    if (!active || !url) {
      setPhase('IDLE');
      return;
    }
    let cancelled = false;
    let hls: { destroy: () => void } | null = null;
    let retryTimer: ReturnType<typeof setTimeout> | null = null;
    let timeTimer: ReturnType<typeof setInterval> | null = null;
    let attempts = 0;
    const cleanupFns: Array<() => void> = [];

    const start = () => {
      const v = videoRef.current;
      // A previous WebRTC session leaves srcObject behind, which wins over
      // src — clear it so the playlist actually loads.
      if (v) v.srcObject = null;
      if (!v) {
        fail('No video element to play into.');
        return;
      }
      if (nativeHls(v)) startNative(v);
      else void startHlsJs(v);
    };

    const fail = (message: string) => {
      if (cancelled) return;
      attempts += 1;
      if (attempts < 2) {
        // One quiet re-attempt: playlists can 404 briefly at session start.
        retryTimer = setTimeout(() => {
          if (!cancelled) start();
        }, 3000);
        return;
      }
      setError(message);
      setPhase('UNAVAILABLE');
    };

    const goLive = () => {
      if (cancelled) return;
      setPhase('LIVE');
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

  return { videoRef, phase, error, mediaTime, retryNow };
}
