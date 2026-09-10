/**
 * Browser-safe runtime configuration.
 * Everything here is compiled into the public bundle — never place
 * passwords, private keys or Sentinel credentials in these variables.
 */
const env = import.meta.env;

export type BasemapId = 'street' | 'satellite';

const mapTiles: Record<BasemapId, { base: string; labels?: string }> = {
  street: {
    base: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
  },
  satellite: {
    base: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    labels:
      'https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}',
  },
};

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
  autoLogin: (env.VITE_AUTO_LOGIN ?? 'true') !== 'false',
  // Default live camera to auto-show on dashboard when website runs
  defaultLiveCameraId: (env.VITE_DEFAULT_LIVE_CAMERA ?? 'cam04') as string,
  map: {
    center: [
      Number(env.VITE_MAP_CENTER_LAT ?? 22.3),
      Number(env.VITE_MAP_CENTER_LNG ?? 71.6),
    ] as [number, number],
    zoom: Number(env.VITE_MAP_DEFAULT_ZOOM ?? 7),
    /**
     * Switchable basemaps, tracking-console style. Street is the standard
     * OpenStreetMap carto layer (labels baked in); satellite pairs Esri
     * imagery with its boundaries-and-places reference overlay. Both are
     * keyless; attribution is rendered by Leaflet's attribution control.
     */
    tiles: mapTiles,
    attribution: {
      street: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
      satellite:
        'Imagery &copy; Esri, Maxar, Earthstar Geographics &mdash; Esri, HERE, Garmin, OpenStreetMap contributors',
    },
  },
  demo: {
    primaryPlate: 'GJ01AB1234',
  },
} as const;

export type AppConfig = typeof config;
