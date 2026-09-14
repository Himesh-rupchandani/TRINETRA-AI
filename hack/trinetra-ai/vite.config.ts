import { defineConfig, loadEnv, type ProxyOptions } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';

// Control-room frontend.
//  - /api      -> our backend (VITE_API_BASE_URL); dev-proxied when BACKEND_ORIGIN is set.
//  - /sentinel -> Sentinel media gateway (WebRTC/WHEP signalling).
//
// The Sentinel origin and credentials live in NON-VITE_ variables so they are
// resolved by the dev server / reverse proxy and never compiled into the
// public bundle. loadEnv() reads them from trinetra-ai/.env (or the real
// shell environment, which wins); only VITE_-prefixed variables ever reach
// the browser. Proxying keeps the app same-origin: no mixed-content block
// when the UI is served over HTTPS, no CORS preflight failures, and the
// Sentinel gateway still authenticates every connection (integrator guide):
// the proxy adds the Authorization header server-side.

/**
 * Sentinel gateway credentials are read from the environment / untracked
 * `trinetra-ai/.env` only. They were previously hardcoded in this file as an
 * "auto-login" fallback, which committed a live username and password to the
 * repository. When they are missing the proxy logs a warning (see below) and
 * forwards unauthenticated — the browser bundle never carries a secret.
 */
function sentinelBasic(env: Record<string, string | undefined>): string | null {
  const email = (env.SENTINEL_EMAIL ?? process.env.SENTINEL_EMAIL ?? '').trim();
  const password = (env.SENTINEL_PASSWORD ?? process.env.SENTINEL_PASSWORD ?? '').trim();
  // Sentinel authenticates with your registered email + access password —
  // equivalent to HTTP Basic auth. The browser only ever talks to the
  // same-origin /sentinel path, so the proxy injects the Authorization
  // header. No credential is compiled into the app bundle (VITE_ prefix absent).
  return email && password
    ? `Basic ${Buffer.from(`${email}:${password}`).toString('base64')}`
    : null;
}

function sentinelProxy(env: Record<string, string | undefined>): ProxyOptions {
  const target = env.SENTINEL_WHEP_ORIGIN || 'http://103.250.160.189:8889';
  const basic = sentinelBasic(env);

  if (!basic && /103\.250\.160\.189/.test(target)) {
    // eslint-disable-next-line no-console
    console.warn(
      '[vite] Sentinel WHEP credentials missing — the gateway requires them. ' +
        'Set SENTINEL_EMAIL and SENTINEL_PASSWORD in trinetra-ai/.env (server-side only, no VITE_ prefix).',
    );
  }

  return {
    target,
    changeOrigin: true,
    secure: false,
    // /sentinel/stream/cam04/whep -> /stream/cam04/whep on the gateway.
    rewrite: (p) => p.replace(/^\/sentinel/, ''),
    configure(proxy) {
      if (basic) {
        proxy.on('proxyReq', (proxyReq) => {
          proxyReq.setHeader('Authorization', basic);
        });
      }
      proxy.on('proxyRes', (proxyRes) => {
        // WHEP replies 201 + Location: the session resource the client DELETEs
        // on teardown. Rewrite it onto our origin so the browser never has to
        // talk to the gateway directly (no mixed content, no CORS). Handles
        // both relative and absolute Location headers.
        const loc = proxyRes.headers.location;
        if (typeof loc !== 'string' || loc.startsWith('/sentinel')) return;
        let out = loc;
        if (/^https?:\/\//i.test(loc)) {
          try {
            const u = new URL(loc);
            out = `${u.pathname}${u.search}`;
          } catch {
            return;
          }
        }
        proxyRes.headers.location = `/sentinel${out.startsWith('/') ? '' : '/'}${out}`;
      });
    },
  };
}

/**
 * HLS compatibility playback (guide §1): /sentinel/live/... -> /live/...
 * on the gateway's HTTP port. Playlists use relative segment URLs, so
 * segments resolve under /sentinel/live/... and ride the same proxy.
 */
function sentinelHlsProxy(env: Record<string, string | undefined>): ProxyOptions {
  let host = '103.250.160.189';
  try {
    host = new URL(env.SENTINEL_WHEP_ORIGIN || 'http://103.250.160.189:8889').hostname;
  } catch {
    /* keep the default host */
  }
  return {
    target: env.SENTINEL_HLS_ORIGIN || `http://${host}`,
    changeOrigin: true,
    secure: false,
    rewrite: (p) => p.replace(/^\/sentinel\/live/, '/live'),
    configure(proxy) {
      const basic = sentinelBasic(env);
      if (basic) {
        proxy.on('proxyReq', (proxyReq) => {
          proxyReq.setHeader('Authorization', basic);
        });
      }
    },
  };
}

export default defineConfig(({ mode }) => {
  // Read the NON-VITE_ server-side Sentinel vars from trinetra-ai/.env, with
  // real shell environment variables taking precedence over the file.
  const env: Record<string, string | undefined> = {
    ...loadEnv(mode, process.cwd(), ''),
    ...process.env,
  };
  const proxy = sentinelProxy(env);
  const hlsProxy = sentinelHlsProxy(env);

  return {
    plugins: [react()],
    resolve: {
      alias: { '@': path.resolve(__dirname, './src') },
    },
    server: {
      host: '0.0.0.0',
      port: 5173,
      strictPort: true,
      // Allow the sandboxed preview host + any deployment host.
      allowedHosts: true,
      proxy: {
        // First match wins: the HLS prefix must precede the WHEP prefix.
        '/sentinel/live': hlsProxy,
        '/sentinel': proxy,
        // CV engine's annotated MJPEG preview (live detection boxes).
        '/cvfeed': {
          target: process.env.CV_FEED_ORIGIN ?? 'http://localhost:8555',
          changeOrigin: true,
          secure: false,
        },
        // Backend API — always proxied in dev so backend+frontend works out of the box.
        // Set BACKEND_ORIGIN env var to override (e.g. http://localhost:8000 is default).
        '/api': {
          target: process.env.BACKEND_ORIGIN ?? 'http://localhost:8000',
          changeOrigin: true,
          secure: false,
          // Also proxy WebSocket upgrades (/api/ws/events) when the
          // realtime transport is configured as `ws`.
          ws: true,
        },
      },
    },
    preview: {
      host: '0.0.0.0',
      port: 4173,
      allowedHosts: true,
      proxy: {
        // First match wins: the HLS prefix must precede the WHEP prefix.
        '/sentinel/live': hlsProxy,
        '/sentinel': proxy,
        '/cvfeed': {
          target: process.env.CV_FEED_ORIGIN ?? 'http://localhost:8555',
          changeOrigin: true,
          secure: false,
        },
        // Serve the verified production build against a real backend: same-origin
        // /api so the browser never needs to know where the API lives.
        // Default to localhost:8000 for simple backend+frontend runs.
        '/api': {
          target: process.env.BACKEND_ORIGIN ?? 'http://localhost:8000',
          changeOrigin: true,
          ws: true,
        },
      },
    },
    build: {
      target: 'es2020',
      chunkSizeWarningLimit: 900,
      rollupOptions: {
        output: {
          manualChunks(id: string) {
            if (!id.includes('node_modules')) return undefined;
            if (/[\\/]node_modules[\\/](react|react-dom|react-router|react-router-dom|scheduler)[\\/]/.test(id))
              return 'react';
            if (/[\\/]node_modules[\\/](leaflet|react-leaflet|@react-leaflet)[\\/]/.test(id)) return 'map';
            if (/[\\/]node_modules[\\/](recharts|d3-.*|victory-.*)[\\/]/.test(id)) return 'charts';
            return undefined;
          },
        },
      },
    },
  };
});
