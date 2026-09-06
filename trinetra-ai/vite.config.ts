import { defineConfig, loadEnv, type ProxyOptions } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';

// Control-room frontend.
//  - /api      -> our backend (VITE_API_BASE_URL); dev-proxied when BACKEND_ORIGIN is set.
//  - /sentinel -> Sentinel media gateway (WebRTC/WHEP signalling).
//
// The Sentinel origin and credentials live in NON-VITE_ variables so they are
// resolved by the dev server / reverse proxy and never compiled into the
// public bundle. Server-only values must be supplied through ignored
// trinetra-ai/.env.local (or the real shell environment, which wins); only
// VITE_-prefixed variables ever reach
// the browser. Proxying keeps the app same-origin: no mixed-content block
// when the UI is served over HTTPS, no CORS preflight failures, and the
// Sentinel gateway still authenticates every connection (integrator guide):
// the proxy adds the Authorization header server-side.

function sentinelProxy(env: Record<string, string | undefined>): ProxyOptions {
  const target = env.SENTINEL_WHEP_ORIGIN || 'http://103.250.160.189:8889';
  const email = (env.SENTINEL_EMAIL ?? '').trim();
  const password = (env.SENTINEL_PASSWORD ?? '').trim();
  // Sentinel WHEP authenticates with your registered email + access password
  // embedded in the URL (guide §0/§1) — equivalent to HTTP Basic auth. The
  // browser only ever talks to the same-origin /sentinel path, so the proxy
  // injects the Authorization header. No credential is compiled into the app.
  const basic =
    email && password
      ? `Basic ${Buffer.from(`${email}:${password}`).toString('base64')}`
      : null;

  if (!basic && /103\.250\.160\.189/.test(target)) {
    // eslint-disable-next-line no-console
    console.warn(
      '[vite] Sentinel WHEP credentials missing — the gateway requires them. ' +
        'Set SENTINEL_EMAIL and SENTINEL_PASSWORD in ignored trinetra-ai/.env.local (server-side only, no VITE_ prefix).',
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

export default defineConfig(({ mode }) => {
  // Read env files and shell values; Sentinel secrets are documented for the
  // ignored .env.local, never browser-exposed VITE_ configuration.
  const env: Record<string, string | undefined> = {
    ...loadEnv(mode, process.cwd(), ''),
    ...process.env,
  };
  const proxy = sentinelProxy(env);
  // These are deliberately non-VITE_ server settings. `loadEnv` is required
  // here so values kept in ignored .env.local work just like shell exports;
  // reading process.env alone skips Vite's local environment files.
  const backendOrigin = env.BACKEND_ORIGIN?.trim();
  const cvFeedOrigin = env.CV_FEED_ORIGIN?.trim() || 'http://localhost:8555';

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
        '/sentinel': proxy,
        // CV engine's annotated MJPEG preview (live detection boxes).
        '/cvfeed': {
          target: cvFeedOrigin,
          changeOrigin: true,
          secure: false,
        },
        ...(mode === 'development' && backendOrigin
          ? {
              '/api': {
                target: backendOrigin,
                changeOrigin: true,
                secure: false,
                // Also proxy WebSocket upgrades (/api/ws/events) when the
                // realtime transport is configured as `ws`.
                ws: true,
              },
            }
          : {}),
      },
    },
    preview: {
      host: '0.0.0.0',
      port: 4173,
      allowedHosts: true,
      proxy: {
        '/sentinel': proxy,
        '/cvfeed': {
          target: cvFeedOrigin,
          changeOrigin: true,
          secure: false,
        },
        // Serve the verified production build against a real backend: same-origin
        // /api so the browser never needs to know where the API lives.
        ...(backendOrigin
          ? {
              '/api': {
                target: backendOrigin,
                changeOrigin: true,
                ws: true,
              },
            }
          : {}),
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
