import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { Layers, Map as MapIcon, Route, Search, X } from 'lucide-react';
import { PageHeader } from '@/components/layout/PageHeader';
import { LazyMap } from '@/components/gis/LazyMap';
import { MapLegend } from '@/components/gis/MapLegend';
import { Panel, EmptyState } from '@/components/common/Panel';
import { StatusChip } from '@/components/common/Chips';
import { CameraPlayer } from '@/components/camera/CameraPlayer';
import { MovementTimeline } from '@/components/vehicle/MovementTimeline';
import { useCameras } from '@/hooks/useCameras';
import { aggregateByDistrict, districtAt } from '@/lib/geo/districtIndex';
import { useLiveEvents } from '@/hooks/useLiveEvents';
import { useAlerts } from '@/hooks/useAlerts';
import { useVehicleSearch } from '@/hooks/useVehicleSearch';
import { useAsync } from '@/hooks/useAsync';
import { eventService } from '@/services/eventService';
import { normalisePlate } from '@/lib/utils';
import type { Camera, RoutePoint } from '@/types';

/** GIS — camera network, live detections and chronological vehicle routes. */
export default function GIS() {
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const { cameras } = useCameras();
  const { result, trace, loading, reset } = useVehicleSearch();
  const recent = useAsync(() => eventService.recent(150), []);
  const { events: liveEvents } = useLiveEvents();
  const { latestAlert } = useAlerts();

  const [plateInput, setPlateInput] = useState(params.get('plate') ?? '');
  const [showCameras, setShowCameras] = useState(true);
  const [showDetections, setShowDetections] = useState(true);
  const [showCoverage, setShowCoverage] = useState(false);
  // Gujarat thematic layers: state focus (dim outside) + district boundaries.
  const [gujaratFocus, setGujaratFocus] = useState(true);
  const [gujaratDistricts, setGujaratDistricts] = useState(true);
  /** District drill-down: pins/list narrowed to one district. */
  const [selectedDistrict, setSelectedDistrict] = useState<string | null>(null);
  const [activeSequence, setActiveSequence] = useState<number | null>(null);
  const [panTo, setPanTo] = useState<[number, number] | null>(null);
  /** Camera whose live feed is docked on the map (null = no player open). */
  const [liveCameraId, setLiveCameraId] = useState<string | null>(null);

  const focusCamera = params.get('focus');
  const plateParam = params.get('plate');

  // Resolve the id against the live registry so status changes flow to the player.
  const liveCamera = useMemo<Camera | null>(
    () => cameras.find((c) => c.id === liveCameraId) ?? null,
    [cameras, liveCameraId],
  );

  /** Marker/list click: pan to the camera and dock its live feed on the map. */
  const focusCameraOnMap = (c: Camera) => {
    setLiveCameraId(c.id);
    setPanTo([c.latitude, c.longitude]);
  };

  useEffect(() => {
    if (plateParam) void trace(plateParam);
    else reset();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [plateParam]);

  useEffect(() => {
    if (!focusCamera) return;
    const cam = cameras.find((c) => c.id === focusCamera);
    if (cam) setPanTo([cam.latitude, cam.longitude]);
  }, [focusCamera, cameras]);

  // When a new 60s notification arrives, automatically pan map to the new different location
  useEffect(() => {
    if (!latestAlert) return;
    const lat = latestAlert.latitude;
    const lng = latestAlert.longitude;
    if (lat && lng && isValidCoord(lat, lng)) {
      setPanTo([lat, lng]);
      if (latestAlert.cameraId) {
        setLiveCameraId(latestAlert.cameraId.toLowerCase());
      }
    }
  }, [latestAlert]);

  const points = useMemo(() => result?.route?.points ?? [], [result]);

  const isValidCoord = (lat: number, lng: number) => {
    if (!Number.isFinite(lat) || !Number.isFinite(lng)) return false;
    if (lat === 0 && lng === 0) return false;
    if (Math.abs(lat) < 0.0001 && Math.abs(lng) < 0.0001) return false;
    if (lat < -90 || lat > 90 || lng < -180 || lng > 180) return false;
    return true;
  };

  const detections = useMemo(() => {
    try {
      const list = [...liveEvents, ...(recent.data ?? [])]
        .filter((e, i, arr) => arr.findIndex((x) => x.id === e.id) === i)
        .filter((e) => isValidCoord(e.latitude, e.longitude))
        .sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());
      return showDetections ? list.filter((e) => e.plate !== '—').slice(0, 60) : [];
    } catch {
      return [];
    }
  }, [recent.data, liveEvents, showDetections]);

  // District membership for cameras + sightings: powers density shading,
  // clustering bubbles and the click-to-focus filter — all client-side.
  const { mapCameras, mapDetections, districtCounts, districtClusters } = useMemo(() => {
    try {
      const validCamerasList = cameras.filter((c) => isValidCoord(c.latitude, c.longitude));
      const camDistrict = new Map<string, string | null>();
      for (const c of validCamerasList) {
        try {
          camDistrict.set(c.id, districtAt(c.latitude, c.longitude));
        } catch {
          camDistrict.set(c.id, null);
        }
      }
      const detDistrict = new Map<string, string | null>();
      for (const e of detections) {
        try {
          detDistrict.set(e.id, districtAt(e.latitude, e.longitude));
        } catch {
          detDistrict.set(e.id, null);
        }
      }

      const fCameras = selectedDistrict
        ? validCamerasList.filter((c) => camDistrict.get(c.id) === selectedDistrict)
        : validCamerasList;
      const fDetections = selectedDistrict
        ? detections.filter((e) => detDistrict.get(e.id) === selectedDistrict)
        : detections;

      const agg = aggregateByDistrict(validCamerasList, detections);
      const counts = Object.fromEntries(
        [...agg.values()].map((a) => [a.name, { cameras: a.cameras, events: a.events }]),
      );
      const clusters = [...agg.values()]
        .filter((a) => a.cameras > 0 && a.centroid && isValidCoord(a.centroid[0], a.centroid[1]))
        .map((a) => ({
          name: a.name,
          centroid: a.centroid as [number, number],
          cameras: a.cameras,
          offline: a.offlineCameras,
          events: a.events,
          bounds: (a.bounds || []).filter(([lat, lng]) => isValidCoord(lat, lng)),
        }));
      return { mapCameras: fCameras, mapDetections: fDetections, districtCounts: counts, districtClusters: clusters };
    } catch {
      return { mapCameras: [], mapDetections: [], districtCounts: {}, districtClusters: [] };
    }
  }, [cameras, detections, selectedDistrict]);

  const selectPoint = (p: RoutePoint) => {
    setActiveSequence(p.sequence);
    setPanTo([p.latitude, p.longitude]);
    // Sighting stop → dock that camera's feed too, when the registry knows it.
    const cam = cameras.find((c) => c.id === p.cameraId.toLowerCase());
    if (cam) setLiveCameraId(cam.id);
  };

  return (
    <div className="flex h-full flex-col">
      <PageHeader
        title="Map"
        icon={MapIcon}
        tone="orange"
        subtitle={
          points.length
            ? `Where ${result?.plate} went: ${points.map((p) => p.cameraName).join(', then ')}`
            : `${cameras.length} cameras on the map · ${detections.length} recent vehicle sightings`
        }
        actions={
          <form
            className="flex items-center gap-1.5"
            onSubmit={(e) => {
              e.preventDefault();
              const p = normalisePlate(plateInput);
              setParams(p ? { plate: p } : {});
            }}
            role="search"
          >
            <label htmlFor="gis-plate" className="sr-only">
              Plot vehicle route
            </label>
            <div className="relative">
              <Search size={12} className="pointer-events-none absolute left-2 top-1/2 -translate-y-1/2 text-ink-faint" aria-hidden />
              <input
                id="gis-plate"
                className="input plate w-[170px] pl-7 uppercase"
                value={plateInput}
                onChange={(e) => setPlateInput(e.target.value.toUpperCase())}
                placeholder="Show a route — type a plate"
              />
            </div>
            <button type="submit" className="btn-primary" disabled={loading}>
              Show route
            </button>
            {plateParam && (
              <button
                type="button"
                className="btn-ghost"
                onClick={() => {
                  setPlateInput('');
                  setParams({});
                  setActiveSequence(null);
                  setLiveCameraId(null);
                }}
              >
                Clear
              </button>
            )}
          </form>
        }
      />

      <div className="grid min-h-0 flex-1 grid-cols-1 gap-3 p-4 sm:gap-4 sm:p-5">
        <Panel
          className="min-h-[420px] xl:col-span-9"
          bodyClassName="relative isolate"
          title="Network map"
          icon={Layers}
          actions={
            <div className="flex flex-wrap items-center gap-2.5 text-2xs text-ink-muted" data-tour="map-layers">
              <label className="flex cursor-pointer items-center gap-1">
                <input type="checkbox" className="h-3 w-3" checked={showCameras} onChange={(e) => setShowCameras(e.target.checked)} />
                Cameras
              </label>
              <label className="flex cursor-pointer items-center gap-1">
                <input type="checkbox" className="h-3 w-3" checked={showDetections} onChange={(e) => setShowDetections(e.target.checked)} />
                Vehicle sightings
              </label>
              <label className="flex cursor-pointer items-center gap-1">
                <input type="checkbox" className="h-3 w-3" checked={showCoverage} onChange={(e) => setShowCoverage(e.target.checked)} />
                Camera range
              </label>
              <label className="flex cursor-pointer items-center gap-1" title="Dim everything outside the Gujarat state border">
                <input type="checkbox" className="h-3 w-3" checked={gujaratFocus} onChange={(e) => setGujaratFocus(e.target.checked)} />
                State focus
              </label>
              <label className="flex cursor-pointer items-center gap-1" title="Draw Census-2011 district boundaries (hover for names)">
                <input type="checkbox" className="h-3 w-3" checked={gujaratDistricts} onChange={(e) => setGujaratDistricts(e.target.checked)} />
                Districts
              </label>
              {selectedDistrict && (
                <button
                  type="button"
                  onClick={() => setSelectedDistrict(null)}
                  className="flex items-center gap-1 rounded-full border border-brand/50 bg-brand/10 px-2 py-0.5 text-2xs font-bold text-brand hover:bg-brand/20"
                  title="Clear district focus"
                >
                  {selectedDistrict}
                  <X size={10} aria-hidden />
                </button>
              )}
            </div>
          }
        >
          <LazyMap
            cameras={showCameras ? mapCameras : []}
            events={mapDetections}
            route={points}
            routePlate={result?.plate}
            activeRouteSequence={activeSequence}
            selectedCameraId={liveCamera?.id ?? focusCamera}
            onSelectRoutePoint={selectPoint}
            onPlaybackStop={(pt) => setActiveSequence(pt.sequence)}
            onSelectCamera={focusCameraOnMap}
            onWatchCamera={(c) => setLiveCameraId(c.id)}
            gujarat={{ boundary: true, mask: gujaratFocus, districts: gujaratDistricts, counts: districtCounts, selected: selectedDistrict, onSelect: setSelectedDistrict }}
            districtClusters={showCameras ? districtClusters : []}
            selectedDistrict={selectedDistrict}
            onSelectDistrict={setSelectedDistrict}
            panTo={panTo}
            showCoverage={showCoverage}
            className="absolute inset-0"
            zoom={12}
          />
          <MapLegend showRoute={points.length > 0} density={gujaratDistricts} />

          {/* Live feed docked to the map: opens for the camera selected on the
              map (marker click / popup "Watch Live") or a route stop. */}
          {liveCamera && (
            <div className="absolute right-3 top-[104px] z-[1200] w-[360px] max-w-[calc(100%-1.5rem)] overflow-hidden rounded-xl border border-line bg-surface-1 shadow-2xl" data-tour="live-feed">
              <div className="flex items-center justify-between gap-2 border-b border-line bg-surface-2/60 px-3 py-1.5">
                <p className="min-w-0 truncate text-2xs font-bold text-ink">
                  <span className="font-mono">{liveCamera.id.toUpperCase()}</span>
                  <span className="text-ink-faint"> · {liveCamera.location}</span>
                </p>
                <div className="flex shrink-0 items-center gap-1">
                  <Link to={`/cameras/${liveCamera.id}`} className="btn-ghost btn-xs">
                    Full view
                  </Link>
                  <button
                    type="button"
                    onClick={() => setLiveCameraId(null)}
                    aria-label="Close live feed"
                    title="Close live feed"
                    className="grid h-6 w-6 place-items-center rounded-md text-ink-muted transition-colors hover:bg-surface-2 hover:text-ink"
                  >
                    <X size={13} aria-hidden />
                  </button>
                </div>
              </div>
              <CameraPlayer key={liveCamera.id} camera={liveCamera} autoRequest className="rounded-none border-0" />
            </div>
          )}
        </Panel>

        <div className="flex min-h-0 flex-col gap-3 sm:gap-4 xl:col-span-3" data-tour="camera-list">
          {points.length > 0 ? (
            <Panel
              title={`Route — ${result?.plate}`}
              icon={Route}
              className="min-h-0 flex-1"
              bodyClassName="overflow-y-auto"
              actions={
                <button
                  type="button"
                  className="btn-ghost btn-xs"
                  onClick={() => navigate(`/vehicles/${result?.plate}`)}
                >
                  Investigate
                </button>
              }
            >
              <MovementTimeline points={points} activeSequence={activeSequence} onSelect={selectPoint} />
            </Panel>
          ) : (
            <Panel
              title={selectedDistrict ? `Cameras — ${selectedDistrict}` : 'All cameras'}
              icon={MapIcon}
              className="min-h-0 flex-1"
              bodyClassName="overflow-y-auto"
            >
              {cameras.length === 0 ? (
                <EmptyState title={selectedDistrict ? 'No cameras in this district' : 'Loading network'} />
              ) : (
                <ul className="divide-y divide-line/60">
                  {mapCameras.map((c) => (
                    <li key={c.id}>
                      <button
                        type="button"
                        onClick={() => focusCameraOnMap(c)}
                        className="flex w-full items-center justify-between gap-2 px-3.5 py-2 text-left hover:bg-surface-2"
                      >
                        <span className="min-w-0">
                          <span className="block font-mono text-xs text-ink">{c.name}</span>
                          <span className="block truncate text-2xs text-ink-faint">{c.location}</span>
                        </span>
                        <StatusChip status={c.status} showDot={false} />
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </Panel>
          )}
        </div>
      </div>
    </div>
  );
}
