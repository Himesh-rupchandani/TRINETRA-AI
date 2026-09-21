export interface CapturedFrame { blob: Blob; mediaTime: number; costMs: number }

/** One capture in flight; no bitmap queue and no video element/transport changes. */
export class FrameEncoder {
  private worker: Worker | null = null;
  private workerFailed = false;
  private canvas: HTMLCanvasElement | null = null;
  private closed = false;
  private busy = false;
  private sequence = 0;
  private cancelJob: (() => void) | null = null;

  private makeWorker: () => Worker;
  constructor(makeWorker: () => Worker) { this.makeWorker = makeWorker; }

  async capture(video: HTMLVideoElement): Promise<CapturedFrame | null> {
    if (this.closed || this.busy || video.readyState < 2 || video.paused || !video.videoWidth) return null;
    this.busy = true;
    const started = performance.now();
    try {
      const scale = Math.min(1, 1280 / Math.max(video.videoWidth, video.videoHeight));
      const width = Math.max(1, Math.round(video.videoWidth * scale));
      const height = Math.max(1, Math.round(video.videoHeight * scale));
      if (!this.workerFailed && typeof OffscreenCanvas !== 'undefined' && typeof createImageBitmap === 'function') {
        let bitmap: ImageBitmap | null = null;
        try {
          this.worker ??= this.makeWorker();
          const mediaTime = video.currentTime;
          bitmap = await createImageBitmap(video, { resizeWidth: width, resizeHeight: height, resizeQuality: 'high' });
          if (this.closed) { bitmap.close(); return null; }
          const blob = await this.encodeBitmap(bitmap);
          bitmap = null; // transferred worker owns/closes it
          return blob && !this.closed ? { blob, mediaTime, costMs: performance.now()-started } : null;
        } catch {
          try { bitmap?.close(); } catch { /* transferred bitmap already released */ }
          this.workerFailed = true;
          this.worker?.terminate(); this.worker = null;
          if (this.closed) return null;
        }
      }
      // Older browsers: yield to painting before the bounded fallback capture.
      await new Promise<void>(resolve => {
        const id = setTimeout(() => { this.cancelJob = null; resolve(); }, 0);
        this.cancelJob = () => { clearTimeout(id); resolve(); };
      });
      if (this.closed || video.paused || video.readyState < 2) return null;
      this.canvas ??= document.createElement('canvas');
      if (this.canvas.width !== width) this.canvas.width = width;
      if (this.canvas.height !== height) this.canvas.height = height;
      const context = this.canvas.getContext('2d');
      if (!context) return null;
      const mediaTime = video.currentTime;
      context.drawImage(video, 0, 0, width, height);
      const blob = await new Promise<Blob | null>(resolve => {
        this.cancelJob = () => resolve(null);
        this.canvas!.toBlob(value => { this.cancelJob = null; resolve(value); }, 'image/jpeg', .9);
      });
      return blob && !this.closed ? { blob, mediaTime, costMs: performance.now()-started } : null;
    } finally { this.busy = false; }
  }

  private encodeBitmap(bitmap: ImageBitmap): Promise<Blob | null> {
    const id = ++this.sequence;
    return new Promise((resolve, reject) => {
      const finish = (blob: Blob | null, error?: string) => {
        clearTimeout(timer); this.cancelJob = null;
        if (this.worker) { this.worker.onmessage = null; this.worker.onerror = null; }
        if (error) reject(new Error(error)); else resolve(blob);
      };
      const timer = setTimeout(() => finish(null, 'Frame encoder timed out'), 4000);
      this.cancelJob = () => finish(null);
      this.worker!.onmessage = (event: MessageEvent<{ id: number; blob?: Blob; error?: string }>) => {
        if (event.data.id === id) finish(event.data.blob ?? null, event.data.error);
      };
      this.worker!.onerror = () => finish(null, 'Frame worker failed');
      try { this.worker!.postMessage({ id, bitmap }, [bitmap]); }
      catch { finish(null, 'Frame transfer failed'); }
    });
  }

  dispose() {
    this.closed = true;
    this.cancelJob?.(); this.cancelJob = null;
    this.worker?.terminate(); this.worker = null;
    if (this.canvas) { this.canvas.width = 1; this.canvas.height = 1; this.canvas = null; }
  }
}
