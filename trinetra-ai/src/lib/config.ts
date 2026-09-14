/**
 * Browser-safe runtime configuration.
 * Everything here is compiled into the public bundle — never place
 * passwords, private keys or Sentinel credentials in these variables.
 */
const env = import.meta.env;

export type BasemapId = 'street' | 'satellite' | 'mapbox' | 'mapbox-night' | 'mapbox-hybrid' | 'mapbox-satellite';

/**
 * Mapbox access token (public/scope-restricted token is fine — tile requests
 * are browser-side). Set VITE_MAPBOX_TOKEN in trinetra-ai/.env.local to fetch
 * the Mapbox basemaps; without it the Mapbox entries are hidden and the
 * keyless OSM/Esri pair is used as before.
 */
export const mapboxToken = (env.VITE_MAPBOX_TOKEN ?? '').trim();
export const mapboxEnabled = mapboxToken.length > 0;

const MAPBOX_ATTRIBUTION =
  '&copy; <a href="https://www.mapbox.com/about/maps/">Mapbox</a> &copy; <a href="http://www.openstreetmap.org/copyright">OpenStreetMap</a> <strong><a href="https://www.mapbox.com/map-feedback/">Improve this map</a></strong>';

const mapTiles: Record<BasemapId, { base: string; labels?: string; maxZoom?: number }> = {
  street: {
    base: 'https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png',
  },
  satellite: {
    base: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    labels:
      'https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}',
  },
  // Mapbox raster tiles (styles rendered server-side): streets keeps labels
  // baked in, satellite is pure imagery, hybrid is imagery + Mapbox labels,
  // night is the dark control-room style.
  mapbox: {
    base: `https://api.mapbox.com/styles/v1/mapbox/streets-v12/tiles/{z}/{x}/{y}@2x?access_token=${mapboxToken}`,
    maxZoom: 20,
  },
  'mapbox-night': {
    base: `https://api.mapbox.com/styles/v1/mapbox/dark-v11/tiles/{z}/{x}/{y}@2x?access_token=${mapboxToken}`,
    maxZoom: 20,
  },
  'mapbox-satellite': {
    base: `https://api.mapbox.com/v4/mapbox.satellite/{z}/{x}/{y}@2x.webp?access_token=${mapboxToken}`,
    maxZoom: 20,
  },
  'mapbox-hybrid': {
    base: `https://api.mapbox.com/styles/v1/mapbox/satellite-streets-v12/tiles/{z}/{x}/{y}@2x?access_token=${mapboxToken}`,
    maxZoom: 20,
  },
};

/** Basemaps actually available — Mapbox only shows when a token is configured. */
export const basemaps: { id: BasemapId; label: string }[] = [
  ...(mapboxEnabled
    ? ([
        { id: 'mapbox', label: 'Mapbox' },
        { id: 'mapbox-night', label: 'Night' },
        { id: 'mapbox-hybrid', label: 'Hybrid' },
        { id: 'mapbox-satellite', label: 'Satellite' },
      ] as { id: BasemapId; label: string }[])
    : []),
  { id: 'street', label: 'OSM Map' },
  { id: 'satellite', label: 'OSM Sat' },
];

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
     * When a Mapbox token is configured (VITE_MAPBOX_TOKEN) the Mapbox
     * Streets/Hybrid/Satellite styles join the toggle and become the default.
     */
    tiles: mapTiles,
    basemaps,
    defaultBasemap: (mapboxEnabled ? 'mapbox' : 'street') as BasemapId,
    attribution: {
      street: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
      satellite:
        'Imagery &copy; Esri, Maxar, Earthstar Geographics &mdash; Esri, HERE, Garmin, OpenStreetMap contributors',
      mapbox: MAPBOX_ATTRIBUTION,
      'mapbox-night': MAPBOX_ATTRIBUTION,
      'mapbox-satellite': MAPBOX_ATTRIBUTION,
      'mapbox-hybrid': MAPBOX_ATTRIBUTION,
    },
  },
  demo: {
    primaryPlate: 'GJ01AB1234',
  },
} as const;

export type AppConfig = typeof config;
