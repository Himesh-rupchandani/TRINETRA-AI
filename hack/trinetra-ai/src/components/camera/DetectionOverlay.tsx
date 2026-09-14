import { useEffect, useRef, useCallback, useState } from 'react';
import { apiUrl } from '@/lib/config';

interface Detection {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  class_name: string;
  confidence: number;
}

/**
 * Overlays real-time YOLO vehicle detection boxes on a live <video> element.
 *
 * Captures frames from the video, sends them to the backend detection API,
 * and draws green bounding boxes on a transparent canvas overlay.  This
 * enables AI detection on WebRTC/HLS cameras where the backend cannot
 * independently open the camera stream (e.g. Sentinel cameras requiring
 * WHEP authentication that only the Vite dev proxy injects).
 */
export function DetectionOverlay({
  videoRef,
  cameraId,
  active,
  onDetecting,
}: {
  videoRef: { current: HTMLVideoElement | null };
  cameraId: string;
  active: boolean;
  onDetecting?: (detecting: boolean) => void;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const captureCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const [, setHasDetected] = useState(false);

  const getCaptureCanvas = useCallback(() => {
    if (!captureCanvasRef.current) {
      captureCanvasRef.current = document.createElement('canvas');
    }
    return captureCanvasRef.current;
  }, []);

  useEffect(() => {
    if (!active) {
      const canvas = canvasRef.current;
      if (canvas) {
        const ctx = canvas.getContext('2d');
        ctx?.clearRect(0, 0, canvas.width, canvas.height);
      }
      setHasDetected(false);
      onDetecting?.(false);
      return;
    }

    let running = true;
    let failCount = 0;

    async function loop() {
      while (running) {
        const video = videoRef.current;
        const canvas = canvasRef.current;
        if (!video || !canvas || video.readyState < 2 || video.paused) {
          await sleep(400);
          continue;
        }

        const vw = video.videoWidth;
        const vh = video.videoHeight;
        if (!vw || !vh) {
          await sleep(400);
          continue;
        }

        // Capture frame to off-screen canvas (downscaled to max 640px wide
        // to reduce bandwidth and match the YOLO default imgsz)
        const capture = getCaptureCanvas();
        const captureScale = Math.min(1, 640 / vw);
        const cw = Math.round(vw * captureScale);
        const ch = Math.round(vh * captureScale);
        capture.width = cw;
        capture.height = ch;
        const cctx = capture.getContext('2d');
        if (!cctx) { await sleep(400); continue; }

        try {
          cctx.drawImage(video, 0, 0, cw, ch);
        } catch {
          // CORS or tainted canvas — wait and retry
          await sleep(2000);
          continue;
        }

        try {
          const blob = await new Promise<Blob | null>((resolve) =>
            capture.toBlob(resolve, 'image/jpeg', 0.65),
          );
          if (!blob || !running) break;

          const res = await fetch(apiUrl(`/api/cameras/${cameraId}/detect-frame`), {
            method: 'POST',
            headers: { 'Content-Type': 'image/jpeg' },
            body: blob,
          });

          if (!running) break;
          if (!res.ok) {
            failCount++;
            if (failCount > 8) {
              onDetecting?.(false);
              break;
            }
            await sleep(1200);
            continue;
          }

          failCount = 0;
          const detections: Detection[] = await res.json();

          drawDetections(canvas, video, detections, vw, vh, captureScale);

          if (detections.length > 0) {
            setHasDetected(true);
            onDetecting?.(true);
          }
        } catch {
          failCount++;
          if (failCount > 8) break;
        }

        // Pace: short gap between rounds (inference is the bottleneck)
        await sleep(200);
      }
    }

    loop();

    return () => {
      running = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, cameraId]);

  return (
    <canvas
      ref={canvasRef}
      className="absolute inset-0 z-[5] pointer-events-none"
      style={{ width: '100%', height: '100%' }}
    />
  );
}

/* ------------------------------------------------------------------ */

function drawDetections(
  canvas: HTMLCanvasElement,
  video: HTMLVideoElement,
  detections: Detection[],
  videoW: number,
  videoH: number,
  captureScale: number,
) {
  const containerW = video.clientWidth;
  const containerH = video.clientHeight;
  canvas.width = containerW;
  canvas.height = containerH;

  const ctx = canvas.getContext('2d');
  if (!ctx) return;
  ctx.clearRect(0, 0, containerW, containerH);

  // Calculate how object-contain positions the video inside the container
  const displayScale = Math.min(containerW / videoW, containerH / videoH);
  const renderW = videoW * displayScale;
  const renderH = videoH * displayScale;
  const offsetX = (containerW - renderW) / 2;
  const offsetY = (containerH - renderH) / 2;

  // Detection coordinates are in the capture canvas pixel space (downscaled).
  // Map: capture coords -> original video coords -> display coords
  const invScale = 1 / captureScale;

  for (const d of detections) {
    const x1 = d.x1 * invScale * displayScale + offsetX;
    const y1 = d.y1 * invScale * displayScale + offsetY;
    const x2 = d.x2 * invScale * displayScale + offsetX;
    const y2 = d.y2 * invScale * displayScale + offsetY;
    const w = x2 - x1;
    const h = y2 - y1;

    // Green bounding box
    ctx.strokeStyle = '#00ff00';
    ctx.lineWidth = 2;
    ctx.strokeRect(x1, y1, w, h);

    // Label background + text
    const label = `${d.class_name} ${Math.round(d.confidence * 100)}%`;
    ctx.font = 'bold 11px monospace';
    const tm = ctx.measureText(label);
    const lh = 14;
    const ly = y1 > lh + 6 ? y1 - lh - 2 : y1 + h + 2;
    ctx.fillStyle = '#00ff00';
    ctx.fillRect(x1, ly, tm.width + 8, lh + 4);
    ctx.fillStyle = '#000000';
    ctx.fillText(label, x1 + 4, ly + lh);
  }
}

function sleep(ms: number) {
  return new Promise((r) => setTimeout(r, ms));
}
