import { useEffect, useMemo } from 'react';
import {
  CircleMarker,
  MapContainer,
  Marker,
  Polyline,
  Popup,
  TileLayer,
  useMap,
} from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import type { Camera, RoutePoint, VehicleEvent } from '@/types';
import { config } from '@/lib/config';
import { cn } from '@/lib/utils';
import { cameraIcon, eventIcon, routeIcon } from './mapIcons';
import { CameraPopup, EventPopup, RoutePopup } from './MapPopups';

/** Transparent placeholder so a blocked tile server degrades to the dark canvas. */
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
}: MapViewProps) {
  const tiles = config.map.tiles.light;
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
    <div className={cn('isolate overflow-hidden', className ?? 'h-full w-full')}>
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
          url={tiles.base}
          attribution={config.map.tileAttribution}
          maxZoom={18}
          errorTileUrl={ERROR_TILE}
        />
        <TileLayer url={tiles.labels} maxZoom={18} errorTileUrl={ERROR_TILE} />
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

        {route.map((p) => (
          <Marker
            key={`${p.eventId}-${p.sequence}`}
            position={[p.latitude, p.longitude]}
            icon={routeIcon(p.sequence, 'HIGH', p.sequence === activeRouteSequence, '#2563eb')}
            eventHandlers={{ click: () => onSelectRoutePoint?.(p) }}
            zIndexOffset={500}
            title={`Sighting ${p.sequence} — ${p.cameraName}`}
          >
            <Popup>
              <RoutePopup point={p} plate={routePlate} />
            </Popup>
          </Marker>
        ))}
      </MapContainer>
    </div>
  );
}
