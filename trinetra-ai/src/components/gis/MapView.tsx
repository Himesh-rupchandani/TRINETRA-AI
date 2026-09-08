import { useEffect, useMemo, useRef, useState } from 'react';
import {
  CircleMarker,
  MapContainer,
  Marker,
  Polyline,
  Popup,
  ScaleControl,
  TileLayer,
  useMap,
} from 'react-leaflet';
import MarkerClusterGroup from 'react-leaflet-cluster';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import 'leaflet.markercluster/dist/MarkerCluster.css';
import 'leaflet.markercluster/dist/MarkerCluster.Default.css';
import { Maximize, Minimize, Pause, Play, RotateCcw } from 'lucide-react';
import type { Camera, RoutePoint, VehicleEvent } from '@/types';
import { config, type BasemapId } from '@/lib/config';
import { cn } from '@/lib/utils';
import { useRoutePlayback } from '@/hooks/useRoutePlayback';
import { cameraIcon, eventIcon, playbackIcon, routeIcon } from './mapIcons';
import { CameraPopup, EventPopup, RoutePopup } from './MapPopups';

/** Transparent placeholder so a blocked tile server degrades gracefully. */
const ERROR_TILE =
  "data:image/svg+xml;charset=utf-8,%3Csvg xmlns='http://www.w3.org/2000/svg' width='256' height='256'%3E%3C/svg%3E";

/**
 * Re-fits the viewport whenever the plotted geometry changes.
 * Size is invalidated first: panels mount before layout settles, and a
 * fitBounds against a zero-height container would leave the map blank.
 */
function FitBounds({ points, enabled }: { points: [number, number][]; enabled: boolean }) {
  const map = useMap();
  useEffect(() => {
    if (!enabled || points.length === 0) return;
    const apply = () => {
      map.invalidateSize({ animate: false });
      if (points.length === 1) map.setView(points[0], Math.max(map.getZoom(), 15));
      else map.fitBounds(L.latLngBounds(points), { padding: [48, 48], maxZoom: 16 });
    };
    apply();
    const t = setTimeout(apply, 260);
    return () => clearTimeout(t);
  }, [map, enabled, JSON.stringify(points)]); // eslint-disable-line react-hooks/exhaustive-deps
  return null;
}

/** Imperatively pans to the externally-selected feature. */
function PanTo({ target }: { target?: [number, number] | null }) {
  const map = useMap();
  useEffect(() => {
    if (target) map.flyTo(target, Math.max(map.getZoom(), 15), { duration: 0.6 });
  }, [map, target?.[0], target?.[1]]); // eslint-disable-line react-hooks/exhaustive-deps
  return null;
}

/** Invalidates size after layout changes so tiles never render half-drawn. */
function ResizeGuard() {
  const map = useMap();
  useEffect(() => {
    const fix = () => map.invalidateSize({ animate: false });
    const raf = requestAnimationFrame(fix);
    const t = setTimeout(fix, 240);
    const ro = new ResizeObserver(fix);
    ro.observe(map.getContainer());
    return () => {
      cancelAnimationFrame(raf);
      clearTimeout(t);
      ro.disconnect();
    };
  }, [map]);
  return null;
}

export interface MapViewProps {
  cameras?: Camera[];
  events?: VehicleEvent[];
  route?: RoutePoint[];
  /** The plate the plotted route belongs to — powers popup deep-links. */
  routePlate?: string;
  selectedCameraId?: string | null;
  activeRouteSequence?: number | null;
  onSelectCamera?: (camera: Camera) => void;
  onSelectRoutePoint?: (point: RoutePoint) => void;
  onSelectEvent?: (event: VehicleEvent) => void;
  panTo?: [number, number] | null;
  fit?: boolean;
  zoom?: number;
  center?: [number, number];
  className?: string;
  /** Draw a coverage halo around each camera. */
  showCoverage?: boolean;
  /** Fired as the replay dot reaches each stop (timeline sync). */
  onPlaybackStop?: (point: RoutePoint) => void;
}

/**
 * Functional Leaflet map — camera network, detection points and
 * chronological vehicle routes. No faked map imagery anywhere.
 */
export function MapView({
  cameras = [],
  events = [],
  route = [],
  routePlate,
  selectedCameraId,
  activeRouteSequence,
  onSelectCamera,
  onSelectRoutePoint,
  onSelectEvent,
  panTo,
  fit = true,
  zoom = config.map.zoom,
  center = config.map.center,
  className,
  showCoverage = false,
  onPlaybackStop,
}: MapViewProps) {
  const [basemap, setBasemap] = useState<BasemapId>('street');
  const tiles = config.map.tiles[basemap];
  const [fullscreen, setFullscreen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const playback = useRoutePlayback(route, onPlaybackStop);

  useEffect(() => {
    const onFs = () => setFullscreen(document.fullscreenElement != null);
    document.addEventListener('fullscreenchange', onFs);
    return () => document.removeEventListener('fullscreenchange', onFs);
  }, []);

  const toggleFullscreen = () => {
    if (document.fullscreenElement) void document.exitFullscreen().catch(() => {});
    else rootRef.current?.requestFullscreen().catch(() => {});
  };
  const routeLine = useMemo(
    () => route.map((p) => [p.latitude, p.longitude] as [number, number]),
    [route],
  );

  const fitPoints = useMemo(() => {
    if (routeLine.length) return routeLine;
    if (cameras.length) return cameras.map((c) => [c.latitude, c.longitude] as [number, number]);
    return events.map((e) => [e.latitude, e.longitude] as [number, number]);
  }, [routeLine, cameras, events]);

  return (
    // `isolate` creates a fresh stacking context so Leaflet's high z-index panes
    // (tiles/markers/controls, z-index up to 1000) are confined to the map and
    // never paint over the panel content above or below it. `overflow-hidden`
    // additionally guarantees the map stays boxed inside its container.
    <div ref={rootRef} className={cn('isolate overflow-hidden', className ?? 'relative h-full w-full')}>
      <MapContainer
        center={center}
        zoom={zoom}
        scrollWheelZoom
        preferCanvas
        zoomControl
        style={{ height: '100%', width: '100%' }}
        attributionControl
      >
        <TileLayer
          key={basemap}
          url={tiles.base}
          attribution={config.map.attribution[basemap]}
          maxZoom={19}
          errorTileUrl={ERROR_TILE}
        />
        {tiles.labels && <TileLayer url={tiles.labels} maxZoom={19} errorTileUrl={ERROR_TILE} />}
        <ScaleControl position="bottomright" imperial={false} />
        <ResizeGuard />
        <FitBounds points={fitPoints} enabled={fit} />
        <PanTo target={panTo} />

        {showCoverage &&
          cameras.map((c) => (
            <CircleMarker
              key={`cov-${c.id}`}
              center={[c.latitude, c.longitude]}
              radius={16}
              pathOptions={{
                color: 'transparent',
                fillColor: c.status === 'ONLINE' ? '#16a34a' : c.status === 'DEGRADED' ? '#d97706' : '#dc2626',
                fillOpacity: 0.09,
              }}
              interactive={false}
            />
          ))}

        <MarkerClusterGroup chunkedLoading maxClusterRadius={48} showCoverageOnHover={false}>
        {cameras.map((c) => (
          <Marker
            key={c.id}
            position={[c.latitude, c.longitude]}
            icon={cameraIcon(c.status, c.id === selectedCameraId)}
            eventHandlers={{ click: () => onSelectCamera?.(c) }}
            keyboard
            title={`${c.name} — ${c.location}`}
          >
            <Popup>
              <CameraPopup camera={c} />
            </Popup>
          </Marker>
        ))}
        </MarkerClusterGroup>

        <MarkerClusterGroup chunkedLoading maxClusterRadius={48} showCoverageOnHover={false}>
        {events.map((e) => (
          <Marker
            key={e.id}
            position={[e.latitude, e.longitude]}
            icon={eventIcon(e.watchlistMatch)}
            eventHandlers={{ click: () => onSelectEvent?.(e) }}
            title={`${e.plate} — ${e.cameraName ?? e.cameraId}`}
          >
            <Popup>
              <EventPopup event={e} />
            </Popup>
          </Marker>
        ))}
        </MarkerClusterGroup>

        {routeLine.length > 1 && (
          <>
            {/* Casing for contrast over any basemap */}
            <Polyline positions={routeLine} pathOptions={{ color: '#000000', weight: 7, opacity: 0.35 }} />
            <Polyline
              positions={routeLine}
              pathOptions={{ color: '#f97316', weight: 3.5, opacity: 0.95, dashArray: '1 0' }}
            />
          </>
        )}

        {route.map((p, i) => (
          <Marker
            key={`${p.eventId}-${p.sequence}`}
            position={[p.latitude, p.longitude]}
            icon={routeIcon(p.sequence, 'HIGH', p.sequence === activeRouteSequence, '#2563eb')}
            eventHandlers={{ click: () => onSelectRoutePoint?.(p) }}
            zIndexOffset={500}
            title={`Sighting ${p.sequence} — ${p.cameraName}`}
          >
            <Popup>
              <RoutePopup point={p} prev={i > 0 ? route[i - 1] : undefined} plate={routePlate} />
            </Popup>
          </Marker>
        ))}
        {playback.started && route.length > 1 && (
          <Marker
            ref={playback.markerRef}
            position={[route[0].latitude, route[0].longitude]}
            icon={playbackIcon()}
            interactive={false}
            keyboard={false}
            zIndexOffset={1000}
          />
        )}
      </MapContainer>
      <div className="absolute right-3 top-3 z-[1001] flex flex-col items-end gap-2">
        <div
          className="flex overflow-hidden rounded-lg border border-line bg-surface-1/95 shadow-md backdrop-blur"
          role="group"
          aria-label="Basemap style"
        >
          <button
            type="button"
            onClick={() => setBasemap('street')}
            aria-pressed={basemap === 'street'}
            className={cn(
              'px-2.5 py-1.5 text-2xs font-semibold transition-colors',
              basemap === 'street' ? 'bg-brand text-white' : 'text-ink-muted hover:bg-surface-2 hover:text-ink',
            )}
          >
            Map
          </button>
          <button
            type="button"
            onClick={() => setBasemap('satellite')}
            aria-pressed={basemap === 'satellite'}
            className={cn(
              'px-2.5 py-1.5 text-2xs font-semibold transition-colors',
              basemap === 'satellite' ? 'bg-brand text-white' : 'text-ink-muted hover:bg-surface-2 hover:text-ink',
            )}
          >
            Satellite
          </button>
        </div>
        <button
          type="button"
          onClick={toggleFullscreen}
          aria-label={fullscreen ? 'Exit fullscreen map' : 'Fullscreen map'}
          title={fullscreen ? 'Exit fullscreen' : 'Fullscreen'}
          className="grid h-8 w-8 place-items-center rounded-lg border border-line bg-surface-1/95 text-ink-muted shadow-md backdrop-blur transition-colors hover:text-ink"
        >
          {fullscreen ? <Minimize size={14} aria-hidden /> : <Maximize size={14} aria-hidden />}
        </button>
      </div>
      {route.length > 1 && (
        <div className="absolute bottom-3 left-1/2 z-[1001] -translate-x-1/2">
          <div className="flex items-center gap-2 rounded-full border border-line bg-surface-1/95 py-1.5 pl-1.5 pr-3 shadow-lg backdrop-blur">
            <button
              type="button"
              onClick={playback.toggle}
              aria-label={playback.playing ? 'Pause route replay' : 'Replay route'}
              title={playback.playing ? 'Pause' : 'Replay route'}
              className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-brand text-white shadow transition-transform hover:scale-105"
            >
              {playback.playing ? (
                <Pause size={14} aria-hidden />
              ) : (
                <Play size={14} className="ml-0.5" aria-hidden />
              )}
            </button>
            {playback.started && (
              <button
                type="button"
                onClick={playback.reset}
                aria-label="Reset replay"
                title="Reset"
                className="grid h-7 w-7 shrink-0 place-items-center rounded-full text-ink-muted transition-colors hover:bg-surface-2 hover:text-ink"
              >
                <RotateCcw size={13} aria-hidden />
              </button>
            )}
            <div className="min-w-[120px]">
              <p className="whitespace-nowrap font-mono text-[10px] font-semibold text-ink">
                {playback.started
                  ? `Stop ${playback.stopIndex + 1} of ${route.length} \u00b7 ${route[playback.stopIndex]?.cameraName ?? ''}`
                  : `Replay ${route.length} stops`}
              </p>
              <div className="mt-1 h-1 overflow-hidden rounded-full bg-slate-500/20">
                <div ref={playback.barRef} className="h-full w-0 rounded-full bg-brand" />
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
