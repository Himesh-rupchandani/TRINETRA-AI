/**
 * Browser-safe runtime configuration.
 * Everything here is compiled into the public bundle — never place
 * passwords, private keys or Sentinel credentials in these variables.
 */
const env = import.meta.env;

export const config = {
  appName: 'TRINETRA AI',
  tagline: 'Intelligent Vision. Faster Response.',
  useMocks: (env.VITE_USE_MOCKS ?? 'true') !== 'false',
  apiBaseUrl: env.VITE_API_BASE_URL ?? '/api',
  // The backend serves both SSE (/api/stream) and WebSocket (/api/ws/events).
  // SSE is the default: it traverses reverse proxies cleanly and reconnects
  // natively in the browser.
  realtimeTransport: (env.VITE_REALTIME_TRANSPORT ?? 'sse') as 'sse' | 'ws' | 'off',
  /**
   * Same-origin path the UI posts WHEP offers to. A server-side proxy maps it
   * onto the Sentinel media gateway, so the browser never sees the gateway
   * origin and the bundle carries no credentials.
   */
  streamBasePath: env.VITE_STREAM_BASE_PATH ?? '/sentinel/stream',
  liveStreams: (env.VITE_LIVE_STREAMS ?? 'true') !== 'false',
  map: {
    center: [
      Number(env.VITE_MAP_CENTER_LAT ?? 22.3),
      Number(env.VITE_MAP_CENTER_LNG ?? 71.6),
    ] as [number, number],
    zoom: Number(env.VITE_MAP_DEFAULT_ZOOM ?? 7),
    /**
     * Standard OpenStreetMap carto basemap — the same light canvas with
     * yellow highways and baked-in labels that tracking consoles use.
     * Single layer (no separate reference overlay); ODbL attribution
     * is rendered by Leaflet's attribution control below.
     */
    tiles: {
      light: {
        base: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
      },
    },
    tileAttribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  },
  demo: {
    primaryPlate: 'GJ01AB1234',
  },
} as const;

export type AppConfig = typeof config;
