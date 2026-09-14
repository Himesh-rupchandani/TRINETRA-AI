import { Buffer } from 'node:buffer';

/**
 * Production twin of the Vite dev proxy for the Sentinel media gateway
 * (see vite.config.ts → sentinelProxy / sentinelHlsProxy).
 *
 * The browser only ever talks to the same-origin /sentinel/* path:
 *  - WHEP signalling  POST /sentinel/stream/<id>/whep (201 + Location),
 *                     DELETE <location> on teardown
 *  - HLS fallback     GET  /sentinel/live/stream/<id>/index.m3u8
 *
 * Gateway credentials live in Vercel environment variables
 * (SENTINEL_EMAIL / SENTINEL_PASSWORD, NO VITE_ prefix) and are injected
 * here server-side as HTTP Basic auth — they are never compiled into the
 * public bundle. Without them the proxy forwards unauthenticated and logs a
 * warning, mirroring the dev proxy behaviour.
 */

const DEFAULT_WHEP_ORIGIN = 'http://103.250.160.189:8889';

function basicAuth(): string | null {
  const email = (process.env.SENTINEL_EMAIL ?? '').trim();
  const password = (process.env.SENTINEL_PASSWORD ?? '').trim();
  return email && password
    ? `Basic ${Buffer.from(`${email}:${password}`).toString('base64')}`
    : null;
}

function hopByHopBlocked(header: string): boolean {
  return [
    'host',
    'connection',
    'keep-alive',
    'proxy-authenticate',
    'proxy-authorization',
    'te',
    'trailer',
    'transfer-encoding',
    'upgrade',
  ].includes(header.toLowerCase());
}

export default async function handler(
  req: Request,
  ctx: { params: { path: string[] } },
): Promise<Response> {
  const sub = (ctx.params.path ?? []).join('/');
  const isHls = sub === 'live' || sub.startsWith('live/');

  // /sentinel/live/... rides the gateway's HTTP port (port 80), exactly like
  // the Vite HLS proxy; everything else goes to the WHEP origin.
  const whepOrigin = process.env.SENTINEL_WHEP_ORIGIN || DEFAULT_WHEP_ORIGIN;
  let targetBase: string;
  if (isHls) {
    targetBase = process.env.SENTINEL_HLS_ORIGIN;
    if (!targetBase) {
      try {
        targetBase = `http://${new URL(whepOrigin).hostname}`;
      } catch {
        targetBase = 'http://103.250.160.189';
      }
    }
  } else {
    targetBase = whepOrigin;
  }

  const url = `${targetBase.replace(/\/+$/, '')}/${sub}`;

  const headers = new Headers();
  for (const [key, value] of req.headers) {
    if (hopByHopBlocked(key) || ['origin', 'referer', 'cookie'].includes(key.toLowerCase())) continue;
    headers.set(key, value);
  }
  const basic = basicAuth();
  if (basic) {
    headers.set('authorization', basic);
  } else if (!/103\.250\.160\.189/.test(url)) {
    // eslint-disable-next-line no-console
    console.warn('[sentinel proxy] SENTINEL_EMAIL/SENTINEL_PASSWORD missing — forwarding unauthenticated.');
  }

  const upstream = await fetch(url, {
    method: req.method,
    headers,
    body: req.method === 'GET' || req.method === 'HEAD' ? undefined : await req.arrayBuffer(),
    redirect: 'manual',
    cache: 'no-store',
  });

  // WHEP replies 201 + Location: rewrite the session resource onto our own
  // /sentinel origin so the browser never talks to the gateway directly
  // (mirrors the dev proxy; avoids mixed content + CORS over HTTPS).
  const resHeaders = new Headers(upstream.headers);
  const location = resHeaders.get('location');
  if (upstream.status === 201 && location) {
    let out = location;
    if (/^https?:\/\//i.test(out)) {
      try {
        const u = new URL(out);
        out = `${u.pathname}${u.search}`;
      } catch {
        /* keep as-is */
      }
    }
    resHeaders.set('location', `/sentinel${out.startsWith('/') ? '' : '/'}${out}`);
  }
  // The gateway may set cookie/CSRF headers that must not leak onto our origin.
  resHeaders.delete('set-cookie');

  return new Response(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: resHeaders,
  });
}
