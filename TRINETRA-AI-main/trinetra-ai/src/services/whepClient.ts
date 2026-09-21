/**
 * WHEP (WebRTC-HTTP Egress Protocol) client for the Sentinel camera grid.
 *
 * Sentinel publishes every camera as a *live* endpoint: one second of video
 * takes one second to arrive, there is no seeking and no way to run ahead of
 * real time. This module therefore treats a stream like a physical camera —
 * it negotiates, it supervises, and it reconnects. It never buffers history.
 *
 * Transport choice (per the integrator's guide):
 *   - RTSP  : TCP-only, not reachable from a browser at all.
 *   - HLS   : CDN host, sits behind the Sentinel access password.
 *   - WHEP  : browser-native, low latency. <-- what we use.
 *
 * Signalling goes through the backend's `/sentinel/...` proxy, either on the
 * same origin or the configured public Render origin. The backend resolves the
 * real gateway; no Sentinel password, key or token is present in this bundle.
 */

export interface WhepSession {
  /** Live MediaStream to attach to a <video> element. */
  stream: MediaStream;
  peer: RTCPeerConnection;
  /** Tears down the PeerConnection and DELETEs the WHEP resource. */
  close: () => Promise<void>;
}

export class WhepError extends Error {
  status?: number;
  retryable: boolean;

  constructor(message: string, status?: number, retryable = true) {
    super(message);
    this.name = 'WhepError';
    this.status = status;
    this.retryable = retryable;
  }
}

/** ICE gathering never blocks negotiation for longer than this. */
const ICE_GATHER_TIMEOUT_MS = 2_500;

/**
 * Resolve ICE gathering, but do not wait forever: with a public gateway the
 * host/srflx candidates we need are produced almost immediately, and hanging
 * on a slow STUN server would only delay first frame.
 */
function waitForIceGathering(peer: RTCPeerConnection): Promise<void> {
  if (peer.iceGatheringState === 'complete') return Promise.resolve();

  return new Promise((resolve) => {
    let done = false;
    const finish = () => {
      if (done) return;
      done = true;
      peer.removeEventListener('icegatheringstatechange', onChange);
      clearTimeout(timer);
      resolve();
    };
    const onChange = () => {
      if (peer.iceGatheringState === 'complete') finish();
    };
    const timer = setTimeout(finish, ICE_GATHER_TIMEOUT_MS);
    peer.addEventListener('icegatheringstatechange', onChange);
  });
}

/**
 * Negotiate a receive-only WHEP session.
 *
 * @param url    Public backend WHEP endpoint (proxied to the gateway).
 * @param signal Abort signal — cancels an in-flight negotiation cleanly.
 */
export async function connectWhep(url: string, signal?: AbortSignal): Promise<WhepSession> {
  const peer = new RTCPeerConnection({
    iceServers: [{ urls: 'stun:stun.l.google.com:19302' }],
    bundlePolicy: 'max-bundle',
  });

  // Receive-only: a control-room client never publishes media upstream.
  peer.addTransceiver('video', { direction: 'recvonly' });
  peer.addTransceiver('audio', { direction: 'recvonly' });

  const stream = new MediaStream();
  peer.addEventListener('track', (ev) => {
    stream.addTrack(ev.track);
  });

  const abort = async () => {
    peer.close();
  };
  signal?.addEventListener('abort', abort, { once: true });

  try {
    const offer = await peer.createOffer();
    await peer.setLocalDescription(offer);
    await waitForIceGathering(peer);
    if (signal?.aborted) throw new WhepError('Cancelled', undefined, false);

    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/sdp' },
      body: peer.localDescription?.sdp ?? offer.sdp ?? '',
      signal,
    });

    if (!res.ok) {
      const body = await res.text().catch(() => '');

      // The gateway rejects an offer whose codec list cannot carry the
      // published track — typically an H.265 camera in a browser without HEVC.
      // Retrying cannot fix that, so it is a terminal condition.
      if (res.status === 400 && /codec/i.test(body)) {
        throw new WhepError(
          'This camera publishes a codec your browser cannot decode (the grid mixes H.264 and H.265).',
          res.status,
          false,
        );
      }

      throw new WhepError(
        res.status === 404 || res.status === 500
          ? 'Camera path is not published on the gateway'
          : `Gateway refused the WHEP offer (HTTP ${res.status})`,
        res.status,
        res.status !== 404,
      );
    }

    const answer = await res.text();
    if (!answer.trim().startsWith('v=')) {
      throw new WhepError('Gateway returned a malformed SDP answer');
    }

    await peer.setRemoteDescription({ type: 'answer', sdp: answer });

    // The WHEP session resource, used to release the stream on teardown.
    const location = res.headers.get('Location');
    const resourceUrl = location ? new URL(location, new URL(url, window.location.href)).toString() : null;

    return {
      stream,
      peer,
      async close() {
        signal?.removeEventListener('abort', abort);
        for (const t of stream.getTracks()) t.stop();
        peer.close();
        if (resourceUrl) {
          // Best-effort: releasing our copy of the feed frees gateway capacity.
          await fetch(resourceUrl, { method: 'DELETE', keepalive: true }).catch(() => undefined);
        }
      },
    };
  } catch (err) {
    peer.close();
    if (err instanceof WhepError) throw err;
    if (err instanceof DOMException && err.name === 'AbortError') {
      throw new WhepError('Cancelled', undefined, false);
    }
    throw new WhepError(err instanceof Error ? err.message : 'WHEP negotiation failed');
  }
}

/**
 * Exponential backoff with jitter: ~2s, 4s, 8s, 16s, capped at 30s.
 * Feeds are supervised upstream and may restart — we must never tight-loop.
 */
export function backoffDelay(attempt: number): number {
  const base = Math.min(2_000 * 2 ** Math.max(0, attempt - 1), 30_000);
  return Math.round(base * (0.75 + Math.random() * 0.5));
}
