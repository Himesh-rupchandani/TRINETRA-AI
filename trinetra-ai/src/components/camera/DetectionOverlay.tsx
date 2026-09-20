import { useEffect, useRef } from 'react';
import { liveAnprService, type LiveAnprSnapshot } from '@/services/liveAnprService';
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

    const capture = document.createElement('canvas');
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

    const draw = () => {
      const video = videoRef.current;
      clear();
      if (!video || !snapshot || video.paused || video.seeking || video.readyState < 2 || document.hidden) return;
      // Include network/render time in the expiry, not just the server's age.
      const current = { ...snapshot, result_age_ms: (snapshot.result_age_ms ?? Infinity) + performance.now() - receivedAt };
      if (!canDrawSnapshot(current, `browser:${clientId}`, video.currentTime)) return;
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
        const mediaTime = video.currentTime;
        lastMediaTime = mediaTime;
        // 640px JPEGs discarded most plate detail. Keep 1280px at high quality,
        // but send one sample/second instead of slowing the video to inference FPS.
        const scale = Math.min(1, 1280 / Math.max(video.videoWidth, video.videoHeight));
        capture.width = Math.round(video.videoWidth * scale);
        capture.height = Math.round(video.videoHeight * scale);
        capture.getContext('2d')?.drawImage(video, 0, 0, capture.width, capture.height);
        const jpeg = await new Promise<Blob | null>((resolve) => capture.toBlob(resolve, 'image/jpeg', 0.9));
        if (stopped || !jpeg) return;
        const result = await liveAnprService.sample(cameraId, jpeg, clientId, mediaTime, controller.signal);
        if (stopped) return;
        snapshot = result;
        receivedAt = performance.now();
        onError(null);
        onStatus(result);
        draw();
        clearTimeout(expiry);
        expiry = setTimeout(clear, Math.max(0, result.overlay_ttl_ms - (result.result_age_ms ?? result.overlay_ttl_ms)));
        delay = Math.max(750, result.sample_interval_ms);
        if (result.status === 'UNAVAILABLE' || result.status === 'ERROR') delay = 5000;
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
