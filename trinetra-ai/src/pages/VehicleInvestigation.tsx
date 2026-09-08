import { useEffect, useMemo, useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { Clock3, Map as MapIcon, Route } from 'lucide-react';
import { useVehicleSearch } from '@/hooks/useVehicleSearch';
import type { RoutePoint } from '@/types';
import { InvestigationLayout } from '@/components/InvestigationLayout';
import { VehicleInfoPanel, WantedBanner } from '@/components/VehicleInfo';
import { DetectionTable } from '@/components/DetectionTable';
import { Evidence } from '@/components/Evidence';
import { MovementTimeline } from '@/components/Timeline';
import { MapCanvas } from '@/components/MapCanvas';
import { Button, buttonClass } from '@/ui/Button';
import { Badge } from '@/ui/Badge';
import { Card, CardBody, CardHeader, SectionLabel } from '@/ui/Card';
import { EmptyState, LoadingRows } from '@/ui/Feedback';
import { Modal } from '@/ui/Modal';
import { Tabs } from '@/ui/Tabs';
import { formatDateTime } from '@/lib/uiHelpers';

type Tab = 'journey' | 'sightings';

/** Straight-line totals for the reconstructed journey. */
function RouteSummary({ route }: { route: RoutePoint[] }) {
  const distanceKm = route.reduce((s, p) => s + (p.distanceKm ?? 0), 0);
  const minutes =
    route.length > 1
      ? Math.max(0, Math.round((Date.parse(route[route.length - 1].timestamp) - Date.parse(route[0].timestamp)) / 60000))
      : null;
  const fastest = Math.max(...route.map((p) => p.speedKmph ?? 0));

  const cells: [string, string][] = [
    ['Cameras passed', String(route.length)],
    ['Total distance', distanceKm > 0 ? `${distanceKm.toFixed(1)} km` : '—'],
    ['Time on road', minutes != null ? `${minutes} min` : '—'],
    ['Fastest leg', fastest > 0 ? `${fastest.toFixed(0)} km/h` : '—'],
  ];

  return (
    <Card>
      <CardHeader title="Route in numbers" subtitle="Straight-line join between camera stops" />
      <CardBody className="grid grid-cols-2 divide-line sm:grid-cols-4 sm:divide-x">
        {cells.map(([label, value]) => (
          <div key={label} className="px-5 py-4">
            <p className="text-xs text-ink-muted">{label}</p>
            <p className="mono mt-1 text-lg font-semibold text-ink">{value}</p>
          </div>
        ))}
      </CardBody>
    </Card>
  );
}

/**
 * Vehicle case file — dossier, journey map, full sighting history and
 * per-sighting evidence. Tabbed so the page stays scannable; the map
 * and timeline stay in sync with the selected stop.
 */
export default function VehicleInvestigation() {
  const { plateSlug = '' } = useParams();
  const plate = decodeURIComponent(plateSlug).toUpperCase();
  const [params, setParams] = useSearchParams();

  const { result, loading, error, searched, trace } = useVehicleSearch();

  useEffect(() => {
    if (plate) void trace(plate);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [plate]);

  const [tab, setTab] = useState<Tab>('journey');
  const [activeJourneyEvent, setActiveJourneyEvent] = useState<string | null>(null);
  const [evidenceId, setEvidenceId] = useState<string | null>(params.get('evidence'));
  const [mapFocus, setMapFocus] = useState<[number, number] | null>(null);

  const events = result?.events ?? [];
  const route = result?.route?.points ?? [];

  // Preselect the wanted sighting (from ?evidence=) once data lands.
  useEffect(() => {
    if (!result || !evidenceId) return;
    const ev = events.find((e) => e.id === evidenceId);
    if (ev) {
      setActiveJourneyEvent(ev.id);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [result]);

  const activeEvent = useMemo(
    () => events.find((e) => e.id === evidenceId) ?? null,
    [events, evidenceId],
  );

  const activeRoutePoint = useMemo(
    () => route.find((p) => p.eventId === activeJourneyEvent) ?? null,
    [route, activeJourneyEvent],
  );

  if (loading || (!searched && plate)) {
    return (
      <div className="mx-auto max-w-6xl p-4 sm:p-6 lg:p-8">
        <LoadingRows label={`Pulling the record for ${plate}`} rows={6} />
      </div>
    );
  }

  if (error || !result) {
    return (
      <div className="p-4 sm:p-6 lg:p-8">
        <EmptyState
          title={error ? 'Could not load this vehicle' : 'No record for this plate'}
          detail={error ?? `${plate} has never been recognised by a camera in this network.`}
          action={
            <div className="flex gap-2.5">
              <Link to="/vehicles" className={buttonClass('primary', 'sm')}>
                Search another plate
              </Link>
              <Link to="/events" className={buttonClass('secondary', 'sm')}>
                Browse the vehicle log
              </Link>
            </div>
          }
        />
      </div>
    );
  }

  const firstSeen = events.length > 0 ? events[events.length - 1] : null;
  const lastSeen = events[0] ?? null;

  return (
    <InvestigationLayout
      backTo="/vehicles"
      backLabel="Find a Vehicle"
      title={<span className="plate text-xl">{result.plate}</span>}
      status={
        result.profile?.watchlist ? (
          <Badge tone="danger">Wanted{result.profile.watchlist.caseRef ? ` · ${result.profile.watchlist.caseRef}` : ''}</Badge>
        ) : (
          <Badge tone="success">No flags</Badge>
        )
      }
      meta={
        events.length > 0 && (
          <span>
            {events.length} sightings · {firstSeen ? `${formatDateTime(firstSeen.timestamp)} → ${formatDateTime(lastSeen!.timestamp)}` : ''}
          </span>
        )
      }
      actions={
        <Button variant="ghost" onClick={() => window.print()}>
          Print case file
        </Button>
      }
    >
      <div className="space-y-6">
        {result.profile?.watchlist && <WantedBanner profile={result.profile} />}

        {/* Dossier */}
        <Card>
          <CardHeader title="Vehicle record" subtitle="Registered details as held by the RTO record" />
          <CardBody className="p-5">{result.profile && <VehicleInfoPanel profile={result.profile} />}</CardBody>
        </Card>

        {/* Journey + sightings */}
        <Card>
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-5 pb-0 pt-1">
            <Tabs
              value={tab}
              onChange={setTab}
              items={[
                { value: 'journey', label: 'Journey', count: route.length },
                { value: 'sightings', label: 'Sighting log', count: events.length },
              ]}
              className="border-b-0"
            />
            {tab === 'journey' && route.length > 1 && (
              <p className="pb-2 text-xs text-ink-faint">
                <Route size={11} className="mr-1 inline" aria-hidden />
                Stops in order · click a stop to focus it on the map
              </p>
            )}
          </div>

          {tab === 'journey' ? (
            <div className="grid min-h-0 lg:grid-cols-[1fr_360px]">
              <div className="min-h-[320px] lg:min-h-[440px]">
                <MapCanvas
                  route={route}
                  routePlate={result.plate}
                  activeRouteSequence={activeRoutePoint?.sequence ?? null}
                  onSelectRoutePoint={(p) => {
                    setActiveJourneyEvent(p.eventId);
                    setMapFocus([p.latitude, p.longitude]);
                  }}
                  panTo={mapFocus}
                  className="h-full min-h-[320px] w-full lg:min-h-[440px]"
                />
              </div>
              <div className="flex min-h-0 flex-col border-t border-line lg:border-l lg:border-t-0">
                <div className="flex items-center gap-2 border-b border-line px-4 py-2.5">
                  <Clock3 size={13} className="text-ink-faint" aria-hidden />
                  <SectionLabel>Timeline</SectionLabel>
                </div>
                <div className="min-h-0 flex-1 overflow-y-auto p-3">
                  <MovementTimeline
                    points={route}
                    activeEventId={activeJourneyEvent}
                    onSelect={(eventId) => {
                      setActiveJourneyEvent(eventId);
                      const pt = route.find((p) => p.eventId === eventId);
                      if (pt) setMapFocus([pt.latitude, pt.longitude]);
                    }}
                  />
                </div>
              </div>
            </div>
          ) : (
            <CardBody>
              <DetectionTable
                events={events}
                activeEventId={evidenceId}
                onViewEvidence={(ev) => {
                  setEvidenceId(ev.id);
                  setParams({ evidence: ev.id }, { replace: true });
                }}
                onViewOnMap={() => setTab('journey')}
              />
            </CardBody>
          )}
        </Card>

        {/* Route summary strip */}
        {route.length > 1 && <RouteSummary route={route} />}
      </div>

      {/* Evidence dialog */}
      <Modal
        open={Boolean(activeEvent)}
        onClose={() => {
          setEvidenceId(null);
          setParams({}, { replace: true });
        }}
        title="Sighting evidence"
        subtitle={activeEvent ? `${activeEvent.cameraName ?? activeEvent.cameraId} · ${formatDateTime(activeEvent.timestamp)}` : undefined}
        size="xl"
        footer={
          activeEvent && (
            <Button
              variant="secondary"
              onClick={() => {
                const pt = route.find((p) => p.eventId === activeEvent.id);
                setEvidenceId(null);
                setParams({}, { replace: true });
                if (pt) {
                  setTab('journey');
                  setActiveJourneyEvent(pt.eventId);
                  setMapFocus([pt.latitude, pt.longitude]);
                }
              }}
            >
              <MapIcon size={13} aria-hidden /> Show in journey
            </Button>
          )
        }
      >
        {activeEvent ? <Evidence ev={activeEvent} /> : <LoadingRows label="Loading evidence" />}
      </Modal>
    </InvestigationLayout>
  );
}
