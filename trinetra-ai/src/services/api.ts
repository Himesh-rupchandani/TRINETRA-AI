import axios, { type AxiosInstance, type AxiosRequestConfig } from 'axios';
import { config } from '@/lib/config';
import { backendMissingMessage, isSpaFallbackBody } from '@/lib/backendStatus';

/**
 * Single axios instance for the whole app.
 * Components never import this directly — they go through services/ + hooks/.
 */
export const http: AxiosInstance = axios.create({
  baseURL: config.apiBaseUrl,
  timeout: 15_000,
  headers: { Accept: 'application/json' },
});

/**
 * Auth hook-point. The token is injected at runtime (e.g. after login or from
 * an httpOnly-cookie exchange) — it is never compiled into the bundle.
 */
let authToken: string | null = null;
export function setAuthToken(token: string | null): void {
  authToken = token;
}

http.interceptors.request.use((cfg) => {
  if (authToken) cfg.headers.Authorization = `Bearer ${authToken}`;
  return cfg;
});

export class ApiError extends Error {
  status?: number;
  constructor(message: string, status?: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

http.interceptors.response.use(
  (r) => r,
  (error) => {
    const status = error?.response?.status;
    const detail =
      error?.response?.data?.message ??
      error?.response?.data?.detail ??
      error?.message ??
      'Request failed';
    // Never log request bodies or headers — they may carry credentials.
    return Promise.reject(new ApiError(detail, status));
  },
);

/**
 * A JSON endpoint that answers with the SPA's own HTML shell is a DEPLOYMENT
 * shape, not data: Vercel serves `/api/*` from the `backend` service only when
 * the project's Root Directory is the repository root, so a frontend-rooted
 * project hands `index.html` back with a `200`. axios returns that HTML as a
 * string, callers read zero rows, and the dashboard rendered an empty grid
 * (`0/0`) instead of naming the problem.
 *
 * Failing loudly here is what keeps that class of bug visible:
 * `lib/backendStatus.ts` explains the cause, and `MainLayout` shows that
 * explanation to the operator.
 */
function assertJsonBody(url: string, data: unknown): void {
  if (!isSpaFallbackBody(data)) return;
  const origin =
    typeof window !== 'undefined' && window.location ? window.location.origin : config.apiBaseUrl;
  throw new ApiError(`${config.apiBaseUrl}${url} — ${backendMissingMessage(origin, url, 200)}`, 200);
}

export async function get<T>(url: string, cfg?: AxiosRequestConfig): Promise<T> {
  const res = await http.get<T>(url, cfg);
  assertJsonBody(url, res.data);
  return res.data;
}

export async function post<T>(url: string, body?: unknown, cfg?: AxiosRequestConfig): Promise<T> {
  const res = await http.post<T>(url, body, cfg);
  assertJsonBody(url, res.data);
  return res.data;
}

/** True when the app is running against synthetic data. */
export const isMockMode = config.useMocks;

/** Absolute URL for a realtime endpoint, honouring the configured base URL. */
export function realtimeUrl(path: string, protocol: 'http' | 'ws' = 'http'): string {
  const base = config.apiBaseUrl.startsWith('http')
    ? config.apiBaseUrl
    : `${window.location.origin}${config.apiBaseUrl}`;
  const url = new URL(base.replace(/\/$/, '') + path);
  if (protocol === 'ws') url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
  return url.toString();
}
