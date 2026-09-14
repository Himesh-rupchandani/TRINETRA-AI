import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
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
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { Maximize, Minimize, Pause, Play, RotateCcw, X, ZoomIn, AlertTriangle } from 'lucide-react';
import type { Camera, RoutePoint, VehicleEvent } from '@/types';
import { config, type BasemapId } from '@/lib/config';
import { cn } from '@/lib/utils';
import { useRoutePlayback } from '@/hooks/useRoutePlayback';
import { cameraIcon, districtBubbleIcon, eventIcon, playbackIcon, routeIcon } from './mapIcons';
import { GujaratFocus, type GujaratFocusProps } from './GujaratFocus';
import { CameraPopup, EventPopup, RoutePopup } from './MapPopups';

/** Light gray placeholder so a blocked tile server degrades gracefully instead of blank. */
const ERROR_TILE =
  "data:image/svg+xml;charset=utf-8,%3Csvg xmlns='http://www.w3.org/2000/svg' width='256' height='256' viewBox='0 0 256 256'%3E%3Crect width='256' height='256' fill='%23f1f5f9'/%3E%3C/svg%3E";

/** Validate lat/lng — filters out 0,0 fallbacks, NaN, and obviously invalid coords. */
function isValidLatLng(lat: number, lng: number): boolean {
  if (!Number.isFinite(lat) || !Number.isFinite(lng)) return false;
  if (lat === 0 && lng === 0) return false;
  if (Math.abs(lat) < 0.0001 && Math.abs(lng) < 0.0001) return false;
  if (lat < -90 || lat > 90 || lng < -180 || lng > 180) return false;
  return true;
}

function pointsKey(points: [number, number][]): string {
  if (points.length === 0) return 'empty';
  if (points.length === 1) return `${points[0][0].toFixed(4)},${points[0][1].toFixed(4)}`;
  const first = points[0];
  const last = points[points.length - 1];
  return `${points.length}:${first[0].toFixed(3)},${first[1].toFixed(3)}-${last[0].toFixed(3)},${last[1].toFixed(3)}`;
}

function FitBounds({ points, enabled }: { points: [number, number][]; enabled: boolean }) {
  const map = useMap();
  const key = useMemo(() => pointsKey(points), [points]);
  useEffect(() => {
    if (!enabled || points.length === 0) return;
    const apply = () => {
      try {
        map.invalidateSize({ animate: false });
        const valid = points.filter(([lat, lng]) => isValidLatLng(lat, lng));
        if (valid.length === 0) return;
        if (valid.length === 1) map.setView(valid[0], Math.max(map.getZoom(), 15));
        else map.fitBounds(L.latLngBounds(valid), { padding: [48, 48], maxZoom: 16 });
      } catch {
        // Never crash map on fitBounds
      }
    };
    apply();
    const t = setTimeout(apply, 260);
    const t2 = setTimeout(apply, 800);
    return () => {
      clearTimeout(t);
      clearTimeout(t2);
    };
  }, [map, enabled, key]);
  return null;
}

function PanTo({ target }: { target?: [number, number] | null }) {
  const map = useMap();
  const targetKey = target ? `${target[0].toFixed(5)},${target[1].toFixed(5)}` : 'none';
  useEffect(() => {
    if (!target) return;
    if (!isValidLatLng(target[0], target[1])) return;
    try {
      map.flyTo(target, Math.max(map.getZoom(), 15), { duration: 0.6 });
    } catch {
      // ignore
    }
  }, [map, targetKey]);
  return null;
}

const DETECTION_ZOOM = 10;

function ZoomTracker({ onZoom }: { onZoom: (z: number) => void }) {
  const map = useMap();
  const onZoomRef = useRef(onZoom);
  onZoomRef.current = onZoom;
  useEffect(() => {
    const report = () => {
      try {
        onZoomRef.current(map.getZoom());
      } catch {
        // ignore
      }
    };
    report();
    map.on('zoomend', report);
    return () => {
      map.off('zoomend', report);
    };
  }, [map]);
  return null;
}

function ResizeGuard() {
  const map = useMap();
  useEffect(() => {
    let mounted = true;
    const fix = () => {
      if (!mounted) return;
      try {
        map.invalidateSize({ animate: false });
      } catch {
        // ignore
      }
    };
    const raf = requestAnimationFrame(fix);
    const t = setTimeout(fix, 240);
    const t2 = setTimeout(fix, 1000);
    let ro: ResizeObserver | null = null;
    try {
      ro = new ResizeObserver(fix);
      ro.observe(map.getContainer());
    } catch {
      // ResizeObserver not available
    }
    window.addEventListener('resize', fix);
    return () => {
      mounted = false;
      cancelAnimationFrame(raf);
      clearTimeout(t);
      clearTimeout(t2);
      window.removeEventListener('resize', fix);
      try {
        ro?.disconnect();
      } catch {
        // ignore
      }
    };
  }, [map]);
  return null;
}

export interface DistrictCluster {
  name: string;
  centroid: [number, number];
  cameras: number;
  offline: number;
  events: number;
  bounds: [number, number][];
}

function DistrictClusterLayer({
  clusters,
  selected,
  onSelect,
}: {
  clusters: DistrictCluster[];
  selected: string | null;
  onSelect?: (name: string | null) => void;
}) {
  const map = useMap();
  return (
    <>
      {clusters.map((c) => {
        if (!c.centroid || !isValidLatLng(c.centroid[0], c.centroid[1])) return null;
        const validBounds = (c.bounds || []).filter(([lat, lng]) => isValidLatLng(lat, lng));
        return (
          <Marker
            key={c.name}
            position={c.centroid}
            zIndexOffset={400}
            icon={districtBubbleIcon(c.cameras, c.offline, c.events, selected === c.name)}
            title={`${c.name} — ${c.cameras} camera${c.cameras === 1 ? '' : 's'} · ${c.events} sighting${c.events === 1 ? '' : 's'}`}
            eventHandlers={{
              click: () => {
                try {
                  if (selected === c.name) {
                    onSelect?.(null);
                    return;
                  }
                  onSelect?.(c.name);
                  if (validBounds.length > 1)
                    map.flyToBounds(L.latLngBounds(validBounds), { padding: [56, 56], maxZoom: 12, duration: 0.7 });
                  else if (validBounds[0]) map.flyTo(validBounds[0], Math.max(map.getZoom(), 12), { duration: 0.7 });
                } catch {
                  // ignore map errors
                }
              },
            }}
          />
        );
      })}
    </>
  );
}

export interface MapViewProps {
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
  onPlaybackStop?: (point: RoutePoint) => void;
  onWatchCamera?: (camera: Camera) => void;
  gujarat?: GujaratFocusProps;
  districtClusters?: DistrictCluster[];
  selectedDistrict?: string | null;
  onSelectDistrict?: (name: string | null) => void;
}

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
  onWatchCamera,
  gujarat,
  districtClusters = [],
  selectedDistrict = null,
  onSelectDistrict,
}: MapViewProps) {
  const [basemap, setBasemap] = useState<BasemapId>(config.map.defaultBasemap);
  const [mapZoom, setMapZoom] = useState(zoom);
  const tiles = config.map.tiles[basemap];
  const [fsMode, setFsMode] = useState<'native' | 'fake' | null>(null);
  const [fsPortalEl, setFsPortalEl] = useState<HTMLDivElement | null>(null);
  const fullscreen = fsMode != null;
  const rootRef = useRef<HTMLDivElement>(null);
  const playback = useRoutePlayback(route, onPlaybackStop);

  const enterFake = useCallback(() => {
    try {
      const el = document.createElement('div');
      el.className = 'fixed inset-0 z-[9999] bg-white';
      el.setAttribute('role', 'dialog');
      el.setAttribute('aria-label', 'Fullscreen map');
      document.body.appendChild(el);
      setFsPortalEl(el);
      setFsMode('fake');
      // Invalidate after portal mount
      setTimeout(() => {
        try {
          const mapEl = el.querySelector('.leaflet-container') as any;
          if (mapEl && mapEl._leaflet_map) mapEl._leaflet_map.invalidateSize({ animate: false });
        } catch {
          // ignore
        }
      }, 100);
    } catch {
      // ignore
    }
  }, []);

  const exitFake = useCallback(() => {
    try {
      fsPortalEl?.remove();
    } catch {
      // ignore
    }
    setFsPortalEl(null);
    setFsMode(null);
  }, [fsPortalEl]);

  useEffect(() => {
    const onFs = () => {
      if (document.fullscreenElement) setFsMode('native');
      else setFsMode((m) => (m === 'native' ? null : m));
    };
    document.addEventListener('fullscreenchange', onFs);
    return () => document.removeEventListener('fullscreenchange', onFs);
  }, []);

  useEffect(
    () => () => {
      try {
        fsPortalEl?.remove();
      } catch {
        // ignore
      }
    },
    [fsPortalEl],
  );

  useEffect(() => {
    if (fsMode !== 'fake') return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        try {
          fsPortalEl?.remove();
        } catch {
          // ignore
        }
        setFsPortalEl(null);
        setFsMode(null);
      }
    };
    document.addEventListener('keydown', onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', onKey);
      document.body.style.overflow = prev;
    };
  }, [fsMode, fsPortalEl]);

  const toggleFullscreen = useCallback(() => {
    if (fsMode === 'fake') {
      exitFake();
      return;
    }
    if (document.fullscreenElement) {
      document.exitFullscreen().catch(() => {});
      return;
    }
    const el = rootRef.current;
    if (el?.requestFullscreen) {
      el.requestFullscreen().then(
        () => {},
        () => enterFake(),
      );
    } else {
      enterFake();
    }
  }, [fsMode, exitFake, enterFake]);

  const [tileErrors, setTileErrors] = useState(0);
  const handleTileError = useCallback(() => {
    setTileErrors((c) => c + 1);
  }, []);
  useEffect(() => {
    if (tileErrors > 12 && basemap !== 'street') {
      setBasemap('street');
      setTileErrors(0);
    }
  }, [tileErrors, basemap]);

  const clustered = useMemo(
    () => districtClusters.length > 0 && mapZoom < DETECTION_ZOOM && !selectedDistrict,
    [districtClusters.length, mapZoom, selectedDistrict],
  );

  const validCameras = useMemo(
    () => cameras.filter((c) => isValidLatLng(c.latitude, c.longitude)),
    [cameras],
  );
  const validEvents = useMemo(
    () => events.filter((e) => isValidLatLng(e.latitude, e.longitude)),
    [events],
  );
  const validRoute = useMemo(
    () => route.filter((p) => isValidLatLng(p.latitude, p.longitude)),
    [route],
  );

  const validClusters = useMemo(
    () => districtClusters.filter((c) => c.centroid && isValidLatLng(c.centroid[0], c.centroid[1])),
    [districtClusters],
  );

  const routeLine = useMemo(
    () => validRoute.map((p) => [p.latitude, p.longitude] as [number, number]),
    [validRoute],
  );

  const fitPoints = useMemo(() => {
    if (routeLine.length) return routeLine;
    if (validCameras.length) return validCameras.map((c) => [c.latitude, c.longitude] as [number, number]);
    return validEvents.map((e) => [e.latitude, e.longitude] as [number, number]);
  }, [routeLine, validCameras, validEvents]);

  const mapInner = (
    <>
      <MapContainer
        center={center}
        zoom={zoom}
        maxZoom={20}
        minZoom={5}
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
          maxZoom={tiles.maxZoom ?? 19}
          minZoom={5}
          errorTileUrl={ERROR_TILE}
          eventHandlers={{ tileerror: handleTileError }}
        />
        {tiles.labels && (
          <TileLayer
            url={tiles.labels}
            maxZoom={tiles.maxZoom ?? 19}
            minZoom={5}
            errorTileUrl={ERROR_TILE}
            eventHandlers={{ tileerror: handleTileError }}
          />
        )}
        <GujaratFocus {...(gujarat ?? { boundary: true })} />
        <ScaleControl position="bottomright" imperial={false} />
        <ResizeGuard />
        <ZoomTracker onZoom={setMapZoom} />
        <FitBounds points={fitPoints} enabled={fit} />
        <PanTo target={panTo} />

        {showCoverage &&
          validCameras.map((c) => (
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

        {clustered ? (
          <DistrictClusterLayer clusters={validClusters} selected={selectedDistrict} onSelect={onSelectDistrict} />
        ) : (
          validCameras.map((c) => (
            <Marker
              key={c.id}
              position={[c.latitude, c.longitude]}
              icon={cameraIcon(c.status, c.id === selectedCameraId)}
              eventHandlers={{ click: () => onSelectCamera?.(c) }}
              keyboard
              title={`${c.name} — ${c.location}`}
            >
              <Popup maxWidth={320} minWidth={240}>
                <CameraPopup camera={c} onWatch={onWatchCamera} />
              </Popup>
            </Marker>
          ))
        )}

        {mapZoom >= DETECTION_ZOOM &&
          validEvents.map((e) => (
            <Marker
              key={e.id}
              position={[e.latitude, e.longitude]}
              icon={eventIcon(e.watchlistMatch)}
              eventHandlers={{ click: () => onSelectEvent?.(e) }}
              title={`${e.plate} — ${e.cameraName ?? e.cameraId}`}
            >
              <Popup maxWidth={320} minWidth={240}>
                <EventPopup event={e} />
              </Popup>
            </Marker>
          ))}

        {routeLine.length > 1 && (
          <>
            <Polyline positions={routeLine} pathOptions={{ color: '#000000', weight: 7, opacity: 0.35 }} />
            <Polyline
              positions={routeLine}
              pathOptions={{ color: '#f97316', weight: 3.5, opacity: 0.95, dashArray: '1 0' }}
            />
          </>
        )}

        {validRoute.map((p, i) => (
          <Marker
            key={`${p.eventId}-${p.sequence}`}
            position={[p.latitude, p.longitude]}
            icon={routeIcon(p.sequence, 'HIGH', p.sequence === activeRouteSequence, '#2563eb')}
            eventHandlers={{ click: () => onSelectRoutePoint?.(p) }}
            zIndexOffset={500}
            title={`Sighting ${p.sequence} — ${p.cameraName}`}
          >
            <Popup maxWidth={340} minWidth={260}>
              <RoutePopup point={p} prev={i > 0 ? validRoute[i - 1] : undefined} plate={routePlate} />
            </Popup>
          </Marker>
        ))}
        {playback.started && validRoute.length > 1 && (
          <Marker
            ref={playback.markerRef}
            position={[validRoute[0].latitude, validRoute[0].longitude]}
            icon={playbackIcon()}
            interactive={false}
            keyboard={false}
            zIndexOffset={1000}
          />
        )}
      </MapContainer>
      {validEvents.length > 0 && mapZoom < DETECTION_ZOOM && (
        <div className="absolute left-3 top-[76px] z-[1001] flex items-center gap-1.5 rounded-full border border-line bg-surface-1/95 px-3 py-1.5 text-2xs font-semibold text-ink-muted shadow-md backdrop-blur">
          <ZoomIn size={12} aria-hidden />
          Zoom in to see {validEvents.length} sighting{validEvents.length === 1 ? '' : 's'}
        </div>
      )}
      {clustered && validClusters.length > 0 && (
        <div className="absolute bottom-3 right-3 z-[1001] rounded-full border border-brand/40 bg-brand/10 px-3 py-1.5 text-2xs font-semibold text-brand shadow-md backdrop-blur">
          Grouped by district — click a bubble to focus
        </div>
      )}
      {tileErrors > 8 && (
        <div className="absolute left-1/2 top-12 z-[1002] flex -translate-x-1/2 items-center gap-2 rounded-full border border-amber-300 bg-amber-50 px-3 py-1.5 text-2xs font-semibold text-amber-800 shadow-md">
          <AlertTriangle size={12} aria-hidden />
          Map tiles loading slowly — switching to fallback
        </div>
      )}
      {validCameras.length === 0 && validEvents.length === 0 && validRoute.length === 0 && (
        <div className="absolute inset-0 z-[500] grid place-items-center bg-surface-0/80 p-6 text-center backdrop-blur-sm">
          <div className="max-w-sm rounded-xl border border-line bg-surface-1 p-5 shadow-lg">
            <p className="text-sm font-semibold text-ink">No map data to show</p>
            <p className="mt-1 text-2xs leading-relaxed text-ink-muted">
              {cameras.length === 0 && events.length === 0 && route.length === 0
                ? 'No cameras or sightings available. Check backend connection.'
                : 'All cameras have invalid coordinates (0,0). They were filtered to keep the map usable.'}
            </p>
          </div>
        </div>
      )}
      <div className="absolute right-3 top-3 z-[1001] flex flex-col items-end gap-2">
        <div
          className="flex overflow-hidden rounded-lg border border-line bg-surface-1/95 shadow-md backdrop-blur"
          role="group"
          aria-label="Basemap style"
        >
          {config.map.basemaps.map((b, i) => (
            <button
              key={b.id}
              type="button"
              onClick={() => {
                setBasemap(b.id);
                setTileErrors(0);
              }}
              aria-pressed={basemap === b.id}
              className={cn(
                'px-2.5 py-1.5 text-2xs font-semibold transition-colors',
                i > 0 && 'border-l border-line',
                basemap === b.id ? 'bg-brand text-white' : 'text-ink-muted hover:bg-surface-2 hover:text-ink',
              )}
            >
              {b.label}
            </button>
          ))}
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
      {validRoute.length > 1 && (
        <div className="absolute bottom-3 left-1/2 z-[1001] -translate-x-1/2">
          <div className="flex items-center gap-2 rounded-full border border-line bg-surface-1/95 py-1.5 pl-1.5 pr-3 shadow-lg backdrop-blur">
            <button
              type="button"
              onClick={playback.toggle}
              aria-label={playback.playing ? 'Pause route replay' : 'Replay route'}
              title={playback.playing ? 'Pause' : 'Replay route'}
              className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-brand text-white shadow transition-transform hover:scale-105"
            >
              {playback.playing ? <Pause size={14} aria-hidden /> : <Play size={14} className="ml-0.5" aria-hidden />}
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
                  ? `Stop ${playback.stopIndex + 1} of ${validRoute.length} \\u00b7 ${validRoute[playback.stopIndex]?.cameraName ?? ''}`
                  : `Replay ${validRoute.length} stops`}
              </p>
              <div className="mt-1 h-1 overflow-hidden rounded-full bg-slate-500/20">
                <div ref={playback.barRef} className="h-full w-0 rounded-full bg-brand" />
              </div>
            </div>
          </div>
        </div>
      )}
      {fullscreen && (
        <button
          type="button"
          onClick={toggleFullscreen}
          className="absolute left-1/2 top-3 z-[1001] flex -translate-x-1/2 items-center gap-1.5 rounded-full border border-white/15 bg-black/85 px-3.5 py-2 text-xs font-semibold text-white shadow-xl backdrop-blur transition-transform hover:scale-105"
        >
          <X size={14} aria-hidden />
          Exit fullscreen
        </button>
      )}
    </>
  );

  if (fsMode === 'fake' && fsPortalEl) {
    return createPortal(<div className="h-full w-full">{mapInner}</div>, fsPortalEl);
  }

  return (
    <div ref={rootRef} data-tour="gis-map" className={cn('isolate overflow-hidden', className ?? 'relative h-full w-full')}>
      {mapInner}
    </div>
  );
}
