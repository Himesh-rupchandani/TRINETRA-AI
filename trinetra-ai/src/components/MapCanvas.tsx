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
import { Link } from 'react-router-dom';
import type { Camera, RoutePoint, VehicleEvent } from '@/types';
import { config } from '@/lib/config';
import { cn, formatDateTime } from '@/lib/utils';
import { cameraStatusHex, severityTone } from '@/lib/uiHelpers';

/** Transparent placeholder so a blocked tile server degrades to the canvas. */
const ERROR_TILE =
  "data:image/svg+xml;charset=utf-8,%3Csvg xmlns='http://www.w3.org/2000/svg' width='256' height='256'%3E%3C/svg%3E";

/** Re-fits the viewport when plotted geometry changes. */
function FitBounds({ points, enabled }: { points: [number, number][]; enabled: boolean }) {
  const map = useMap();
  useEffect(() => {
    if (!enabled || points.length === 0) return;
    const apply = () => {
      map.invalidateSize({ animate: false });
      if (points.length === 1) map.setView(points[0], Math.max(map.getZoom(), 15));
      else map.fitBounds(L.latLngBounds(points), { padding: [52, 52], maxZoom: 16 });
    };
    apply();
    const t = setTimeout(apply, 260);
    return () => clearTimeout(t);
  }, [map, enabled, JSON.stringify(points)]); // eslint-disable-line react-hooks/exhaustive-deps
  return null;
}

function PanTo({ target }: { target?: [number, number] | null }) {
  const map = useMap();
  useEffect(() => {
    if (target) map.flyTo(target, Math.max(map.getZoom(), 15), { duration: 0.6 });
  }, [map, target?.[0], target?.[1]]); // eslint-disable-line react-hooks/exhaustive-deps
  return null;
}

/** Keeps Leaflet sized correctly when panels resize. */
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

function cameraIcon(status: string, selected = false): L.DivIcon {
  const color = cameraStatusHex[status] ?? '#64748b';
  const size = selected ? 18 : 13;
  return L.divIcon({
    className: 'trinetra-marker',
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
    popupAnchor: [0, -size / 2],
    html: `<div style="position:relative;width:${size}px;height:${size}px;">
      <div style="width:${size}px;height:${size}px;border-radius:50%;background:${color};
        border:2px solid rgb(255 255 255 / 0.9);box-shadow:0 1px 5px rgba(16,24,40,.35)"></div>
      ${selected ? `<div style="position:absolute;inset:-6px;border-radius:50%;border:2px solid ${color}"></div>` : ''}
    </div>`,
  });
}

function routeIcon(sequence: number, active = false): L.DivIcon {
  const fill = '#15803d';
  const size = active ? 28 : 23;
  return L.divIcon({
    className: 'trinetra-marker',
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
    popupAnchor: [0, -size / 2],
    html: `<div style="width:${size}px;height:${size}px;border-radius:50%;background:${fill};
      border:2px solid ${active ? '#ffffff' : 'rgba(255,255,255,.85)'};display:grid;place-items:center;
      box-shadow:0 2px 6px rgba(16,24,40,.35);font:600 ${size * 0.44}px/1 'IBM Plex Mono',monospace;color:#fff;">
      ${sequence}</div>`,
  });
}

function eventIcon(watchlist = false): L.DivIcon {
  const color = watchlist ? '#be123c' : '#15803d';
  return L.divIcon({
    className: 'trinetra-marker',
    iconSize: [12, 12],
    iconAnchor: [6, 6],
    popupAnchor: [0, -6],
    html: `<div style="width:12px;height:12px;border-radius:50%;background:${color};
      border:1.5px solid rgba(255,255,255,.85);box-shadow:0 1px 3px rgba(16,24,40,.35)"></div>`,
  });
}

function CameraPopup({ camera }: { camera: Camera }) {
  return (
    <div className="p-3.5">
      <p className="mono text-[13px] font-semibold text-ink">{camera.name}</p>
      <p className="mt-0.5 text-xs text-ink-muted">{camera.location}</p>
      <p className="mt-1.5 text-[11px] text-ink-faint">
        {camera.department ?? '—'} · {camera.status}
      </p>
      <Link
        to={`/cameras/${camera.id}`}
        className="mt-2.5 inline-flex text-xs font-semibold text-accent hover:underline"
      >
        Open camera →
      </Link>
    </div>
  );
}

function EventPopup({ event }: { event: VehicleEvent }) {
  return (
    <div className="p-3.5">
      <p className="plate text-[13px] font-semibold text-ink">{event.plate}</p>
      <p className="mt-0.5 text-xs text-ink-muted">
        {event.cameraName ?? event.cameraId.toUpperCase()} · {event.location}
      </p>
      <p className="mono mt-1 text-[11px] text-ink-faint">{formatDateTime(event.timestamp)}</p>
      {event.watchlistMatch && (
        <span className={`mt-1.5 inline-block rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide ${severityTone.CRITICAL.text} border-critical/30 bg-critical/[0.06]`}>
          Wanted match
        </span>
      )}
      <Link
        to={`/vehicles/${event.plate}?evidence=${event.id}`}
        className="mt-2.5 block text-xs font-semibold text-accent hover:underline"
      >
        Open investigation →
      </Link>
    </div>
  );
}

function RoutePopup({ point, plate }: { point: RoutePoint; plate?: string }) {
  return (
    <div className="p-3.5">
      <p className="text-[11px] font-semibold uppercase tracking-wider text-ink-faint">
        Sighting {point.sequence}
      </p>
      <p className="mono mt-0.5 text-[13px] font-semibold text-ink">{point.cameraName}</p>
      <p className="text-xs text-ink-muted">{point.location}</p>
      <p className="mono mt-1 text-[11px] text-ink-faint">
        {formatDateTime(point.timestamp)}
        {point.gapMinutes != null && ` · +${point.gapMinutes.toFixed(0)} min`}
        {point.distanceKm != null && ` · ${point.distanceKm.toFixed(1)} km`}
      </p>
      <Link
        to={`/vehicles/${plate ?? point.cameraId}?evidence=${point.eventId}`}
        className="mt-2.5 block text-xs font-semibold text-accent hover:underline"
      >
        Open investigation →
      </Link>
    </div>
  );
}

export interface MapCanvasProps {
  cameras?: Camera[];
  events?: VehicleEvent[];
  route?: RoutePoint[];
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
  showCoverage?: boolean;
}

/**
 * SENTINEL city map — camera network, sightings and chronological
 * routes over a light civic basemap. No faked imagery anywhere.
 */
export function MapCanvas({
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
}: MapCanvasProps) {
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
    // `isolate` confines Leaflet's high z-index panes to the map canvas.
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
                fillColor: cameraStatusHex[c.status] ?? '#64748b',
                fillOpacity: 0.08,
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
            <Polyline positions={routeLine} pathOptions={{ color: '#0f172a', weight: 7, opacity: 0.25 }} />
            <Polyline positions={routeLine} pathOptions={{ color: '#15803d', weight: 3.5, opacity: 0.95 }} />
          </>
        )}

        {route.map((p) => (
          <Marker
            key={`${p.eventId}-${p.sequence}`}
            position={[p.latitude, p.longitude]}
            icon={routeIcon(p.sequence, p.sequence === activeRouteSequence)}
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
