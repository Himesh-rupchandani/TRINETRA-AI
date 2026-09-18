/**
 * Chunked upload client — splits a File into 3 MB chunks and posts them one at
 * a time to `/api/uploads/chunks/*`. The chunks are intentionally small enough
 * to fit under Vercel's hard 4.5 MB serverless-function body limit, which is
 * why the user was seeing "Request failed with status code 413".
 *
 * One ChunkedUploader handles ONE file. For multi-file uploads, instantiate
 * one per file and await them in sequence/parallel as needed.
 */
import { post } from './api';

export const CHUNK_SIZE = 3 * 1024 * 1024; // 3 MB — must stay < 4.5 MB
export const DIRECT_UPLOAD_THRESHOLD = 2 * 1024 * 1024; // <2MB: legacy POST

export interface ChunkedInitOptions {
  source: 'upload' | 'analysis';
  filename: string;
  totalSize: number;
  totalChunks: number;
  cameraId?: string;
  name?: string;
  location?: string;
  cameraIdsCsv?: string;
  batchId?: string;
  autoStart?: boolean;
}

export interface ChunkedInitResponse {
  upload_id: string;
  chunk_size: number;
  total_chunks: number;
  total_size: number;
}

export interface ChunkProgress {
  loaded: number;       // bytes sent so far
  total: number;        // total bytes
  percentage: number;   // 0..100
  chunksSent: number;
  totalChunks: number;
}

export type ChunkProgressCb = (p: ChunkProgress) => void;

/** Send the init handshake. */
async function initSession(opts: ChunkedInitOptions): Promise<ChunkedInitResponse> {
  const form = new FormData();
  form.append('filename', opts.filename);
  form.append('total_chunks', String(opts.totalChunks));
  form.append('total_size', String(opts.totalSize));
  form.append('source', opts.source);
  if (opts.cameraId) form.append('camera_id', opts.cameraId);
  if (opts.name) form.append('name', opts.name);
  if (opts.location) form.append('location', opts.location);
  if (opts.cameraIdsCsv) form.append('camera_ids', opts.cameraIdsCsv);
  if (opts.batchId) form.append('batch_id', opts.batchId);
  form.append('auto_start', String(Boolean(opts.autoStart)));
  return post<ChunkedInitResponse>('/uploads/chunks/init', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 0,
  });
}

/** Send one chunk using fetch (so we can have clean cancellation + progress). */
async function sendChunk(
  uploadId: string,
  chunkIndex: number,
  blob: Blob,
  signal?: AbortSignal,
): Promise<{ received: number; total_chunks: number; done: boolean }> {
  const form = new FormData();
  form.append('chunk_number', String(chunkIndex));
  form.append('chunk', blob, `chunk-${chunkIndex}`);

  const res = await fetch(`/api/uploads/chunks/${encodeURIComponent(uploadId)}`, {
    method: 'POST',
    body: form,
    signal,
  });
  if (!res.ok) {
    let msg = `Chunk ${chunkIndex} failed (HTTP ${res.status})`;
    try {
      const data = await res.json();
      if (data?.detail) msg += `: ${data.detail}`;
    } catch {
      /* ignore */
    }
    throw new Error(msg);
  }
  return res.json();
}

/** Complete the session — triggers server-side assembly and returns the
 *  resulting DTO (shape depends on source). */
async function completeSession<T = unknown>(uploadId: string): Promise<T> {
  return post<T>(`/uploads/chunks/${encodeURIComponent(uploadId)}/complete`, undefined, {
    timeout: 0,
  });
}

export interface ChunkedUploadResult<T> {
  data: T;
  uploadId: string;
}

export async function uploadChunked<T>(
  file: File,
  opts: Omit<ChunkedInitOptions, 'filename' | 'totalSize' | 'totalChunks'>,
  onProgress?: ChunkProgressCb,
  signal?: AbortSignal,
): Promise<ChunkedUploadResult<T>> {
  const totalChunks = Math.max(1, Math.ceil(file.size / CHUNK_SIZE));
  const init = await initSession({
    ...opts,
    filename: file.name,
    totalSize: file.size,
    totalChunks,
  });
  try {
    for (let i = 0; i < totalChunks; i++) {
      if (signal?.aborted) throw new Error('Upload cancelled.');
      const start = i * CHUNK_SIZE;
      const end = Math.min(start + CHUNK_SIZE, file.size);
      const blob = file.slice(start, end);
      await sendChunk(init.upload_id, i, blob, signal);
      const loaded = end;
      onProgress?.({
        loaded,
        total: file.size,
        percentage: Math.min(100, Math.round((loaded / file.size) * 100)),
        chunksSent: i + 1,
        totalChunks,
      });
    }
    const data = await completeSession<T>(init.upload_id);
    return { data, uploadId: init.upload_id };
  } catch (err) {
    // Best-effort abort — clean the temp file on the server.
    try {
      await fetch(`/api/uploads/chunks/${encodeURIComponent(init.upload_id)}/abort`, {
        method: 'POST',
      });
    } catch {
      /* ignore */
    }
    throw err;
  }
}
