import { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Layers, Route as RouteIcon } from 'lucide-react';
import { useCameras } from '@/hooks/useCameras';
import { useEventSearch } from '@/hooks/useEvents';
import { useVehicleSearch } from '@/hooks/useVehicleSearch';
import { MapCanvas } from '@/components/MapCanvas';
import { MovementTimeline } from '@/components/Timeline';
import { Evidence } from '@/components/Evidence';
import { Badge } from '@/ui/Badge';
import type { CameraStatus } from '@/types';
import { Card, CardBody, CardHeader } from '@/ui/Card';
import { Boundary, EmptyState } from '@/ui/Feedback';
import { Modal } from '@/ui/Modal';
import { PlateLink } from '@/ui/Links';
import { SwitchChip } from '@/ui/Switch';
import { cn } from '@/lib/utils';
import { formatTime, severityTone } from '@/lib/uiHelpers';

/**
 * City Map — camera network with coverage halos, live sightings and
 * reconstructed routes for a traced plate. Layers are explicit toggles.
 */
export default function GIS() {
  const [params] = useSearchParams();
  const { cameras, loading: camsLoading } = useCameras();

  const [showCameras, setShowCameras] = useState(true);
  const [showCoverage, setShowCoverage] = useState(true);
  const [showEvents, setShowEvents] = useState(true);
  const [statusFilter, setStatusFilter] = useState<'ALL' | CameraStatus>('ALL');

  // Watchlist trace from URL (?plate=...&focus=camId)
  const tracePlate = params.get('plate')?.toUpperCase() ?? null;
  const focusCamera = params.get('focus');
  const { result, trace, searched } = useVehicleSearch();

  useEffect(() => {
    if (tracePlate) void trace(tracePlate);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tracePlate]);

  // Recent sightings for the live layer (latest page of the log).
  const { data: recentEvents, error: feedError } = useEventSearch({ watchlistOnly: false }, 1, 100);

  const filteredCameras = useMemo(
    () => (statusFilter === 'ALL' ? cameras : cameras.filter((c) => c.status === statusFilter)),
    [cameras, statusFilter],
  );

  const route = result?.route?.points ?? [];
  const [activeJourneyEvent, setActiveJourneyEvent] = useState<string | null>(null);
  const [panTo, setPanTo] = useState<[number, number] | null>(null);
  const [evidence, setEvidence] = useState<string | null>(null);

  // Focus a camera passed in the URL once cameras arrive.
  useEffect(() => {
    if (!focusCamera || cameras.length === 0) return;
    const cam = cameras.find((c) => c.id === focusCamera);
    if (cam) setPanTo([cam.latitude, cam.longitude]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusCamera, cameras.length]);

  const activeEvent = useMemo(
    () => recentEvents?.items.find((e) => e.id === evidence) ?? null,
    [recentEvents, evidence],
  );

  return (
    <div className="p-4 sm:p-6 lg:p-8">
      <div className="grid min-h-0 gap-5 xl:grid-cols-[1fr_330px]">
        {/* Map panel */}
        <Card className="overflow-hidden">
          <CardHeader
            title="City-wide operations map"
            subtitle="Camera network and live vehicle sightings on the civic basemap"
            actions={
              <div className="flex flex-wrap items-center gap-2">
                <SwitchChip checked={showCameras} onChange={setShowCameras} label="Cameras" />
                <SwitchChip checked={showCoverage} onChange={setShowCoverage} label="Coverage" title="100 m halo around each post" />
                <SwitchChip checked={showEvents} onChange={setShowEvents} label="Sightings" />
              </div>
            }
          />
          <CardBody>
            <div className="relative h-[calc(100vh-320px)] min-h-[420px] w-full">
              <MapCanvas
                cameras={showCameras ? filteredCameras : []}
                events={showEvents ? (recentEvents?.items ?? []).slice(0, 80) : []}
                route={route}
                routePlate={result?.plate}
                activeRouteSequence={
                  activeJourneyEvent ? route.find((p) => p.eventId === activeJourneyEvent)?.sequence ?? null : null
                }
                onSelectRoutePoint={(p) => {
                  setActiveJourneyEvent(p.eventId);
                  setEvidence(p.eventId);
                }}
                onSelectEvent={(e) => setEvidence(e.id)}
                panTo={panTo}
                showCoverage={showCoverage}
                className="h-full w-full"
              />
              {/* Status legend — part of the map chrome */}
              <div className="pointer-events-none absolute bottom-3 left-3 z-[500] flex items-center gap-3 rounded-lg border border-line bg-surface-1/95 px-3 py-2 shadow-xs">
                {(['ONLINE', 'DEGRADED', 'OFFLINE'] as const).map((s) => (
                  <button
                    key={s}
                    type="button"
                    onClick={() => setStatusFilter(statusFilter === s ? 'ALL' : s)}
                    className={cn(
                      'flex items-center gap-1.5 text-[11px] font-medium transition-opacity',
                      statusFilter !== 'ALL' && statusFilter !== s && 'opacity-40',
                    )}
                    aria-pressed={statusFilter === s}
                  >
                    <span
                      className={cn(
                        'h-2 w-2 rounded-full',
                        s === 'ONLINE' ? 'bg-online' : s === 'DEGRADED' ? 'bg-warn' : 'bg-offline',
                      )}
                      aria-hidden
                    />
                    {s[0] + s.slice(1).toLowerCase()}
                  </button>
                ))}
              </div>
            </div>
          </CardBody>
        </Card>

        {/* Rail */}
        <aside className="flex min-w-0 flex-col gap-5">
          {tracePlate && (
            <Card>
              <CardHeader
                title="Traced route"
                subtitle={searched && route.length === 0 ? 'No route on record for this plate' : `Sightings of ${tracePlate}`}
                actions={<Badge tone="accent"><RouteIcon size={10} className="mr-1" aria-hidden />{route.length} stops</Badge>}
              />
              <CardBody className="max-h-[420px] overflow-y-auto p-3">
                <Boundary loading={!!tracePlate && !searched} isEmpty={searched && route.length === 0} emptyTitle="No camera sightings for this plate">
                  <MovementTimeline
                    points={route}
                    activeEventId={activeJourneyEvent}
                    onSelect={(eventId) => {
                      setActiveJourneyEvent(eventId);
                      const pt = route.find((p) => p.eventId === eventId);
                      if (pt) {
                        setPanTo([pt.latitude, pt.longitude]);
                        setEvidence(pt.eventId);
                      }
                    }}
                  />
                </Boundary>
              </CardBody>
            </Card>
          )}

          <Card className="min-h-0 flex-1">
            <CardHeader
              title="Latest sightings"
              subtitle="Newest first — click to inspect"
              actions={<Layers size={13} className="text-ink-faint" aria-hidden />}
            />
            <CardBody className="max-h-[440px] overflow-y-auto">
              <Boundary
                loading={!recentEvents && !feedError}
                error={feedError}
                isEmpty={(recentEvents?.items.length ?? 0) === 0}
                emptyTitle="No sightings yet"
                emptyDetail="Live camera reads will stream into this list."
              >
                <ul className="divide-y divide-line/70">
                  {(recentEvents?.items ?? []).slice(0, 40).map((e) => (
                    <li key={e.id}>
                      <button
                        type="button"
                        onClick={() => {
                          setEvidence(e.id);
                          setPanTo([e.latitude, e.longitude]);
                        }}
                        className="flex w-full items-center gap-3 px-4 py-2.5 text-left transition-colors hover:bg-surface-2/70 active:bg-surface-3/60"
                      >
                        <span
                          className={cn('h-6 w-[3px] shrink-0 rounded-full', e.watchlistMatch ? severityTone.CRITICAL.bar : 'bg-accent/50')}
                          aria-hidden
                        />
                        <span className="min-w-0 flex-1">
                          <PlateLink plate={e.plate} size="xs" />
                          <span className="mono mt-0.5 block truncate text-[11px] text-ink-faint">
                            {e.cameraName ?? e.cameraId.toUpperCase()} · {formatTime(e.timestamp)}
                          </span>
                        </span>
                        {e.watchlistMatch && <Badge tone="danger">Wanted</Badge>}
                      </button>
                    </li>
                  ))}
                </ul>
              </Boundary>
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="Network snapshot" subtitle="Registry totals" />
            <CardBody className="grid grid-cols-3 divide-x divide-line">
              {([
                ['Online', camsLoading ? '—' : cameras.filter((c) => c.status === 'ONLINE').length],
                ['Degraded', camsLoading ? '—' : cameras.filter((c) => c.status === 'DEGRADED').length],
                ['Offline', camsLoading ? '—' : cameras.filter((c) => c.status === 'OFFLINE').length],
              ] as [string, number | string][]).map(([label, n]) => (
                <div key={label} className="px-4 py-3.5 text-center">
                  <p className="mono text-lg font-semibold text-ink">{n}</p>
                  <p className="mt-0.5 text-[11px] text-ink-faint">{label}</p>
                </div>
              ))}
            </CardBody>
          </Card>
        </aside>
      </div>

      <Modal
        open={Boolean(activeEvent)}
        onClose={() => setEvidence(null)}
        title="Sighting evidence"
        size="lg"
      >
        {activeEvent ? (
          <Evidence ev={activeEvent} />
        ) : (
          <EmptyState title="Evidence unavailable" detail="This sighting's imagery is not in the local archive." />
        )}
      </Modal>
    </div>
  );
}
