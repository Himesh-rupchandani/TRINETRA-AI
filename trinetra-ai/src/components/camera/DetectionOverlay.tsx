import { useEffect, useRef } from 'react';
import { liveAnprService, type LiveAnprSnapshot } from '@/services/liveAnprService';
import { FrameEncoder } from '@/services/frameEncoder';
import { frameAdmissionDelay, nextSampleDelay } from '@/lib/anprScheduling';
import { canDrawSnapshot, containedBox, matchesSceneSignature } from '@/lib/liveDetections';

/** Browser playback stays native. Only sampled JPEGs visit the ANPR worker. */
export function DetectionOverlay({ videoRef, cameraId, active, onStatus, onError }: {
  videoRef: { current: HTMLVideoElement | null };
  cameraId: string;
  active: boolean;
  onStatus: (status: LiveAnprSnapshot) => void;
  onError: (reason: string | null) => void;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const clear = () => canvas.getContext('2d')?.clearRect(0, 0, canvas.width, canvas.height);
    clear();
    if (!active) return;

    const capture = new FrameEncoder(() => new Worker(new URL('./frameCapture.worker.ts', import.meta.url), { type: 'module' }));
    const scene = document.createElement('canvas');
    scene.width = 16;
    scene.height = 9;
    const sceneContext = scene.getContext('2d', { willReadFrequently: true });
    if (sceneContext) sceneContext.imageSmoothingQuality = 'high';
    const clientId = crypto.randomUUID();
    const controller = new AbortController();
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    let expiry: ReturnType<typeof setTimeout>;
    let paintTimer: ReturnType<typeof setTimeout>;
    let lastMediaTime = -1;
    let snapshot: LiveAnprSnapshot | null = null;
    let receivedAt = 0;
    let lastPaintTime = -1;
    let lastPaintSnapshot: LiveAnprSnapshot | null = null;
    let lastDropped = 0;
    let lastFrames = 0;

    const draw = () => {
      const video = videoRef.current;
      if (!video || !snapshot || !snapshot.detections.length || video.paused || video.seeking || video.readyState < 2 || document.hidden) { clear(); return; }
      // Include network/render time in the expiry, not just the server's age.
      const current = { ...snapshot, result_age_ms: (snapshot.result_age_ms ?? Infinity) + performance.now() - receivedAt };
      if (!canDrawSnapshot(current, `browser:${clientId}`, video.currentTime)) { clear(); return; }
      if (lastPaintTime === video.currentTime && lastPaintSnapshot === snapshot && canvas.width === video.clientWidth && canvas.height === video.clientHeight) return;
      lastPaintTime = video.currentTime;
      lastPaintSnapshot = snapshot;
      clear();
      if (snapshot.frame_signature) {
        if (!sceneContext) return;
        try {
          sceneContext.drawImage(video, 0, 0, scene.width, scene.height);
          if (!matchesSceneSignature(snapshot.frame_signature, sceneContext.getImageData(0, 0, scene.width, scene.height).data)) return;
        } catch { return; } // tainted/cross-origin video: never guess an overlay
      }
      drawDetections(canvas, video, snapshot);
    };
    // Cheap visual checks between OCR requests catch seeks/cuts without ever
    // waiting for inference or making another network request.
    const paint = () => {
      if (stopped) return;
      draw();
      paintTimer = setTimeout(paint, 200);
    };
    paint();
    const resize = new ResizeObserver(draw);
    resize.observe(canvas);

    const sample = async () => {
      if (stopped) return;
      const video = videoRef.current;
      let delay = 1000;
      try {
        if (!video || document.hidden || video.paused || video.readyState < 2 ||
            !video.videoWidth || video.currentTime === lastMediaTime) {
          clear();
          return;
        }
        // A tiny status request is cheaper than encoding/uploading JPEGs that
        // the busy, shared or memory-limited backend cannot accept anyway.
        const preflight = await liveAnprService.status(cameraId, controller.signal);
        if (stopped) return;
        const wait = frameAdmissionDelay(preflight, `browser:${clientId}`);
        if (wait) {
          snapshot = preflight; receivedAt = performance.now();
          onStatus(preflight); onError(null); draw();
          delay = wait;
          return;
        }
        // Encoding uses a Web Worker where supported; playback remains native.
        // Keep the same 1280px / .9 quality rather than discarding plate pixels.
        const captured = await capture.capture(video);
        if (stopped || !captured || video.paused || document.hidden) return;
        const { blob: jpeg, mediaTime } = captured;
        lastMediaTime = mediaTime;
        const result = await liveAnprService.sample(cameraId, jpeg, clientId, mediaTime, controller.signal);
        if (stopped) return;
        snapshot = result;
        receivedAt = performance.now();
        onError(null);
        onStatus(result);
        draw();
        clearTimeout(expiry);
        expiry = setTimeout(clear, Math.max(0, result.overlay_ttl_ms - (result.result_age_ms ?? result.overlay_ttl_ms)));
        const quality = video.getVideoPlaybackQuality?.();
        const dropped = quality ? Math.max(0, quality.droppedVideoFrames-lastDropped) : 0;
        const frames = quality ? Math.max(0, quality.totalVideoFrames-lastFrames) : 0;
        if (quality) { lastDropped = quality.droppedVideoFrames; lastFrames = quality.totalVideoFrames; }
        delay = nextSampleDelay(result, captured.costMs, dropped, frames);
        if (result.status === 'UNAVAILABLE' || result.status === 'ERROR') delay = Math.max(delay, 5000);
      } catch (error) {
        clear();
        if (!stopped) onError(error instanceof Error ? error.message : 'Plate scanning unavailable. Video is unaffected.');
        delay = 5000;
      } finally {
        // Recursive timer: never more than one request per player in flight.
        if (!stopped) timer = setTimeout(sample, delay);
      }
    };

    const visibility = () => { if (document.hidden) clear(); };
    document.addEventListener('visibilitychange', visibility);
    void sample();
    return () => {
      stopped = true;
      controller.abort();
      capture.dispose();
      clearTimeout(timer);
      clearTimeout(expiry);
      clearTimeout(paintTimer);
      resize.disconnect();
      document.removeEventListener('visibilitychange', visibility);
      clear();
    };
  }, [active, cameraId, videoRef, onStatus, onError]);

  return <canvas ref={canvasRef} className="pointer-events-none absolute inset-0 z-[5] h-full w-full" aria-hidden />;
}

function drawDetections(canvas: HTMLCanvasElement, video: HTMLVideoElement, result: LiveAnprSnapshot) {
  if (canvas.width !== video.clientWidth) canvas.width = video.clientWidth;
  if (canvas.height !== video.clientHeight) canvas.height = video.clientHeight;
  const ctx = canvas.getContext('2d');
  if (!ctx) return;
  for (const detection of result.detections) {
    const color = detection.plate_status === 'LOW_CONFIDENCE' ? '#fbbf24' : '#22ff88';
    const map = (box: readonly number[]) => containedBox(box, result.frame_width, result.frame_height, canvas.width, canvas.height);
    const [x, y, w, h] = map([detection.x1, detection.y1, detection.x2, detection.y2]);
    ctx.strokeStyle = color;
    ctx.lineWidth = 2;
    ctx.strokeRect(x, y, w, h);
    if (detection.plate_box) ctx.strokeRect(...map(detection.plate_box));
    const label = detection.plate_number
      ? `${detection.plate_number}${detection.plate_status === 'LOW_CONFIDENCE' ? ' · verify' : ''}`
      : `${detection.class_name} · reading plate`;
    ctx.font = 'bold 12px monospace';
    const labelWidth = ctx.measureText(label).width + 12;
    const labelX = Math.max(0, Math.min(x, canvas.width - labelWidth));
    const labelY = Math.max(0, y - 22);
    ctx.fillStyle = '#07130fee';
    ctx.fillRect(labelX, labelY, labelWidth, 21);
    ctx.fillStyle = color;
    ctx.fillText(label, labelX + 6, labelY + 15);
  }
}
