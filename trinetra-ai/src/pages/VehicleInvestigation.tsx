import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Car, FileImage, Map as MapIcon, Route, ScanLine, ShieldAlert, Table2 } from 'lucide-react';
import { InvestigationLayout } from '@/layouts/InvestigationLayout';
import { LazyMap } from '@/components/gis/LazyMap';
import { MapLegend } from '@/components/gis/MapLegend';
import { MovementTimeline } from '@/components/vehicle/MovementTimeline';
import { VehicleInfoPanel } from '@/components/vehicle/VehicleInfoPanel';
import { DetectionTable } from '@/components/vehicle/DetectionTable';
import { EvidencePanel } from '@/components/vehicle/EvidencePanel';
import { AlertCard } from '@/components/alerts/AlertCard';
import { Panel, EmptyState, LoadingState, ErrorState } from '@/components/common/Panel';
import { InvalidPlateNotice } from '@/components/vehicle/InvalidPlateNotice';
import { SeverityChip } from '@/components/common/Chips';
import { useVehicleSearch } from '@/hooks/useVehicleSearch';
import { useAlerts } from '@/hooks/useAlerts';
import type { RoutePoint, VehicleEvent } from '@/types';
import { formatDuration, isValidPlate, minutesBetween, prettyPlate } from '@/lib/utils';

/**
 * VEHICLE INVESTIGATION WORKSPACE
 * GIS route (left) · movement timeline (centre) · vehicle & watchlist (right)
 * · detection history + evidence (bottom).
 */
export default function VehicleInvestigation() {
  const { plate = '' } = useParams();
  const navigate = useNavigate();
  const { result, loading, error, trace } = useVehicleSearch();
  const { alerts, acknowledge, resolve } = useAlerts();
  const [activeSequence, setActiveSequence] = useState<number | null>(null);
  const [panTo, setPanTo] = useState<[number, number] | null>(null);
  const [evidenceEvent, setEvidenceEvent] = useState<VehicleEvent | null>(null);

  useEffect(() => {
    if (plate) void trace(plate);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [plate]);

  const events = useMemo(() => result?.events ?? [], [result]);
  const points = useMemo(() => result?.route?.points ?? [], [result]);
  const profile = result?.profile ?? null;
  const wl = profile?.watchlist;

  const vehicleAlerts = useMemo(
    () => alerts.filter((a) => a.plate === plate.toUpperCase()),
    [alerts, plate],
  );

  const activeEvent = useMemo(() => {
    if (!activeSequence) return evidenceEvent ?? events[events.length - 1] ?? null;
    const p = points.find((x) => x.sequence === activeSequence);
    return events.find((e) => e.id === p?.eventId) ?? null;
  }, [activeSequence, points, events, evidenceEvent]);

  const selectPoint = (p: RoutePoint) => {
    setActiveSequence(p.sequence);
    setPanTo([p.latitude, p.longitude]);
    const ev = events.find((e) => e.id === p.eventId);
    if (ev) setEvidenceEvent(ev);
  };

  const journeyDuration =
    points.length > 1
      ? formatDuration(minutesBetween(points[0].timestamp, points[points.length - 1].timestamp))
      : '—';

  if (loading) {
    return (
      <div className="p-4">
        <div className="panel">
          <LoadingState label={`Reconstructing movement history for ${plate}`} rows={6} />
        </div>
      </div>
    );
  }

  if (error) {
    if (!isValidPlate(plate)) {
      return (
        <div className="p-4">
          <div className="panel">
            <InvalidPlateNotice raw={plate} />
          </div>
        </div>
      );
    }
    return (
      <div className="p-4">
        <div className="panel">
          <ErrorState message={error} onRetry={() => trace(plate)} />
        </div>
      </div>
    );
  }

  if (!events.length) {
    return (
      <InvestigationLayout
        backTo="/vehicles"
        backLabel="Back to search"
        title={<span className="plate text-sm text-ink">{prettyPlate(plate)}</span>}
      >
        <div className="p-4">
          <div className="panel">
            <EmptyState
              icon={Car}
              title={`No sightings recorded for ${plate}`}
              detail="No camera in the network has detected this registration number in the retained window."
              action={
                <button type="button" className="btn-primary mt-2" onClick={() => navigate('/vehicles')}>
                  Trace another vehicle
                </button>
              }
            />
          </div>
        </div>
      </InvestigationLayout>
    );
  }

  return (
    <InvestigationLayout
      backTo="/vehicles"
      backLabel="Back to search"
      title={
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-ink-faint">
            Vehicle
          </p>
          <p className="plate text-base leading-tight text-ink">{prettyPlate(plate)}</p>
        </div>
      }
      status={
        wl?.active ? (
          <span className="flex items-center gap-1.5">
            <span className="chip border-critical/50 bg-critical/12 text-critical">
              <ShieldAlert size={11} aria-hidden /> On the wanted list
            </span>
            <SeverityChip severity={wl.severity} />
          </span>
        ) : (
          <span className="chip border-online/45 bg-online/10 text-online">No watchlist entry</span>
        )
      }
      meta={
        <>
          <span className="text-2xs text-ink-faint">
            Seen <span className="font-mono text-ink-muted">{events.length}</span> times
          </span>
          <span className="text-2xs text-ink-faint">
            By <span className="font-mono text-ink-muted">{result?.route?.camerasTouched ?? 0}</span> cameras
          </span>
          <span className="text-2xs text-ink-faint">
            Travelled <span className="font-mono text-ink-muted">{result?.route?.totalDistanceKm ?? 0} km</span>
          </span>
          <span className="text-2xs text-ink-faint">
            Over <span className="font-mono text-ink-muted">{journeyDuration}</span>
          </span>
        </>
      }
      actions={
        <>
          <button type="button" className="btn-ghost btn-xs" onClick={() => navigate(`/gis?plate=${plate}`)}>
            <MapIcon size={12} aria-hidden /> Open big map
          </button>
          <button type="button" className="btn-ghost btn-xs" onClick={() => navigate(`/events?plate=${plate}`)}>
            <Table2 size={12} aria-hidden /> All sightings
          </button>
        </>
      }
    >
      <div className="grid gap-3 p-4 sm:gap-4 sm:p-5" data-tour="trace">
        {/* LEFT — GIS */}
        <Panel
          title="Route on the map"
          icon={MapIcon}
          className="min-h-[420px] xl:col-span-5"
          bodyClassName="relative isolate"
          actions={
            <span className="chip border-high/45 bg-high/10 text-high">
              {points.map((p) => p.cameraName).join(' → ') || 'No route'}
            </span>
          }
        >
          <LazyMap
            route={points}
            routePlate={result?.plate}
            cameras={[]}
            activeRouteSequence={activeSequence}
            onSelectRoutePoint={selectPoint}
            panTo={panTo}
            className="absolute inset-0"
          />
          <MapLegend showRoute />
        </Panel>

        {/* CENTRE — timeline */}
        <Panel
          title="Where it went"
          icon={Route}
          className="min-h-[420px] xl:col-span-3"
          bodyClassName="overflow-y-auto"
        >
          <MovementTimeline points={points} activeSequence={activeSequence} onSelect={selectPoint} />
        </Panel>

        {/* RIGHT — vehicle + watchlist + alerts */}
        <div className="flex flex-col gap-3 sm:gap-4 xl:col-span-4">
          <Panel title="Vehicle details" icon={Car}>
            {profile ? (
              <VehicleInfoPanel profile={profile} />
            ) : (
              <EmptyState title="No vehicle profile" />
            )}
          </Panel>

          <Panel
            title={`Alerts for this vehicle (${vehicleAlerts.length})`}
            icon={ShieldAlert}
            bodyClassName="max-h-[320px] overflow-y-auto"
          >
            {vehicleAlerts.length === 0 ? (
              <EmptyState title="No alerts raised" detail="This vehicle has not triggered a watchlist alert." />
            ) : (
              <div className="space-y-3 p-3">
                {vehicleAlerts.map((a) => (
                  <AlertCard key={a.id} alert={a} onAcknowledge={acknowledge} onResolve={resolve} compact />
                ))}
              </div>
            )}
          </Panel>
        </div>

        {/* BOTTOM — detection history + evidence */}
        <Panel
          title="Every time it was seen"
          icon={ScanLine}
          className="xl:col-span-8"
          actions={
            <span className="chip border-line bg-surface-3 text-ink-muted">Seen {events.length} times</span>
          }
        >
          <DetectionTable
            events={events}
            activeEventId={activeEvent?.id}
            onViewEvidence={(e) => {
              setEvidenceEvent(e);
              const p = points.find((x) => x.eventId === e.id);
              if (p) setActiveSequence(p.sequence);
            }}
            onViewOnMap={(e) => {
              const p = points.find((x) => x.eventId === e.id);
              if (p) selectPoint(p);
            }}
          />
        </Panel>

        <Panel title="Photo evidence" icon={FileImage} className="xl:col-span-4">
          <EvidencePanel event={activeEvent} />
        </Panel>
      </div>
    </InvestigationLayout>
  );
}
