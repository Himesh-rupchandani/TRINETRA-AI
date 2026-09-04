import { defineConfig, type ProxyOptions } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';

// Control-room frontend.
//  - /api      -> our backend (VITE_API_BASE_URL); dev-proxied when BACKEND_ORIGIN is set.
//  - /sentinel -> Sentinel media gateway (WebRTC/WHEP signalling).
//
// The Sentinel origin lives in a NON-VITE_ variable so it is resolved by the dev
// server / reverse proxy and never compiled into the public bundle. Proxying also
// keeps the app same-origin: no mixed-content block when the UI is served over
// HTTPS, and no CORS preflight failures against the media gateway.
const SENTINEL_WHEP_ORIGIN = process.env.SENTINEL_WHEP_ORIGIN ?? 'http://103.250.160.189:8889';

const sentinelProxy: ProxyOptions = {
  target: SENTINEL_WHEP_ORIGIN,
  changeOrigin: true,
  secure: false,
  rewrite: (p) => p.replace(/^\/sentinel/, ''),
  configure(proxy) {
    // WHEP replies 201 + Location: the session resource the client DELETEs on
    // teardown. Rewrite it onto our origin so the browser never has to talk to
    // the gateway directly (no mixed content, no CORS).
    proxy.on('proxyRes', (proxyRes) => {
      const loc = proxyRes.headers.location;
      if (typeof loc === 'string' && !loc.startsWith('/sentinel')) {
        proxyRes.headers.location = `/sentinel${loc.startsWith('/') ? '' : '/'}${loc}`;
      }
    });
  },
};

export default defineConfig(({ mode }) => ({
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
      '/sentinel': sentinelProxy,
      ...(mode === 'development' && process.env.BACKEND_ORIGIN
        ? {
            '/api': {
              target: process.env.BACKEND_ORIGIN,
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
    proxy: { '/sentinel': sentinelProxy },
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
}));
