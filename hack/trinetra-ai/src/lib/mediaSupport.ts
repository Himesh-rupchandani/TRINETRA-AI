/**
 * Browser media-capability probes.
 *
 * The Sentinel grid is mixed H.264 / H.265. WebRTC HEVC decoding is absent in
 * most browsers, so we check *before* negotiating: a camera we cannot decode
 * should say so immediately rather than fail, retry and fail again.
 */

let cachedCodecs: string[] | null = null;

function receiverCodecs(): string[] {
  if (cachedCodecs) return cachedCodecs;
  try {
    const caps = RTCRtpReceiver.getCapabilities('video');
    cachedCodecs = (caps?.codecs ?? []).map((c) => c.mimeType.toLowerCase());
  } catch {
    cachedCodecs = [];
  }
  return cachedCodecs;
}

/** True when this browser can decode the given camera codec over WebRTC. */
export function canDecodeOverWebRtc(codec?: string): boolean {
  if (!codec) return true; // unknown — let negotiation decide
  const c = codec.toUpperCase();
  const list = receiverCodecs();
  if (list.length === 0) return true; // no WebRTC introspection — try anyway
  if (c === 'H265' || c === 'HEVC') {
    return list.some((m) => m.includes('h265') || m.includes('hevc'));
  }
  if (c === 'H264' || c === 'AVC') return list.some((m) => m.includes('h264'));
  return true;
}

/** True when WebRTC is available at all (older/locked-down browsers). */
export function webRtcAvailable(): boolean {
  return typeof RTCPeerConnection !== 'undefined';
}
