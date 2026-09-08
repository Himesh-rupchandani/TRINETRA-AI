import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  Car,
  Crosshair,
  FileImage,
  Gauge,
  Map as MapIcon,
  Route,
  ScanLine,
  ShieldAlert,
  Table2,
  UserRound,
} from 'lucide-react';
import { InvestigationLayout } from '@/layouts/InvestigationLayout';
import { LazyMap } from '@/components/gis/LazyMap';
import { MapLegend } from '@/components/gis/MapLegend';
import { MovementTimeline } from '@/components/vehicle/MovementTimeline';
import { VehicleInfoPanel } from '@/components/vehicle/VehicleInfoPanel';
import { DetectionTable } from '@/components/vehicle/DetectionTable';
import { EvidencePanel } from '@/components/vehicle/EvidencePanel';
import { AlertCard } from '@/components/alerts/AlertCard';
import { Panel, EmptyState, LoadingState, ErrorState } from '@/components/common/Panel';
import { useVehicleSearch } from '@/hooks/useVehicleSearch';
import { useAlerts } from '@/hooks/useAlerts';
import { useOfficer } from '@/features/officer/OfficerProvider';
import { useToast } from '@/features/system/ToastProvider';
import type { RoutePoint, VehicleEvent } from '@/types';
import { formatDuration, minutesBetween, prettyPlate } from '@/lib/utils';

/**
 * VEHICLE INVESTIGATION WORKSPACE
 * Plate hero (huge mono plate, colour, make/model, confidence, case officer)
 * → GIS route · movement timeline · vehicle & watchlist dossier
 * → detection history + evidence crops.
 */
export default function VehicleInvestigation() {
  const { plate = '' } = useParams();
  const navigate = useNavigate();
  const { result, loading, error, trace } = useVehicleSearch();
  const { alerts, acknowledge, resolve } = useAlerts();
  const { current: officer } = useOfficer();
  const toast = useToast();
  const [activeSequence, setActiveSequence] = useState<number | null>(null);
  const [panTo, setPanTo] = useState<[number, number] | null>(null);
  const [evidenceEvent, setEvidenceEvent] = useState<VehicleEvent | null>(null);
  const [takingCase, setTakingCase] = useState(false);

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

  /** Best plate confidence across the sighting history. */
  const bestConfidence = useMemo(() => {
    const confs = events.map((e) => e.plateConfidence).filter((c): c is number => c != null);
    return confs.length ? Math.max(...confs) : null;
  }, [events]);

  /** Officer currently holding this vehicle's case (latest acknowledger). */
  const caseOfficer = useMemo(
    () =>
      vehicleAlerts.find((a) => a.acknowledgedBy)?.acknowledgedBy ??
      officer?.name ??
      'Unassigned',
    [vehicleAlerts, officer],
  );
  const openAlert = vehicleAlerts.find((a) => a.status === 'NEW');

  const takeCase = async () => {
    if (!openAlert) return;
    setTakingCase(true);
    try {
      await acknowledge(openAlert.id);
      toast.success('Case assigned', `${prettyPlate(plate)} is now with ${officer?.name ?? 'you'}`);
    } catch {
      toast.error('Could not assign the case');
    } finally {
      setTakingCase(false);
    }
  };

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
            Vehicle investigation
          </p>
          <p className="plate text-base leading-tight text-ink">{prettyPlate(plate)}</p>
        </div>
      }
      status={
        wl?.active ? (
          <span className="flex items-center gap-1.5">
            <span className="chip animate-pulse border-critical/50 bg-critical/10 text-critical">
              <ShieldAlert size={11} aria-hidden /> On the wanted list
            </span>
          </span>
        ) : (
          <span className="chip border-online/45 bg-online/10 text-online">No watchlist entry</span>
        )
      }
      meta={
        <>
          <span className="text-2xs text-ink-faint">
            Seen <span className="font-mono tabular-nums text-ink-muted">{events.length}</span> times
          </span>
          <span className="text-2xs text-ink-faint">
            By <span className="font-mono tabular-nums text-ink-muted">{result?.route?.camerasTouched ?? 0}</span> cameras
          </span>
          <span className="text-2xs text-ink-faint">
            Travelled <span className="font-mono tabular-nums text-ink-muted">{result?.route?.totalDistanceKm ?? 0} km</span>
          </span>
          <span className="text-2xs text-ink-faint">
            Over <span className="font-mono tabular-nums text-ink-muted">{journeyDuration}</span>
          </span>
        </>
      }
      actions={
        <>
          <button type="button" className="btn-tint btn-xs" onClick={() => navigate(`/gis?plate=${plate}`)}>
            <Crosshair size={12} aria-hidden /> Trace on map
          </button>
          <button type="button" className="btn-ghost btn-xs" onClick={() => navigate(`/events?plate=${plate}`)}>
            <Table2 size={12} aria-hidden /> All sightings
          </button>
        </>
      }
    >
      <div className="grid gap-3 p-3.5 sm:p-4">
        {/* PLATE HERO — identity at a glance */}
        <Panel className="xl:col-span-12" bodyClassName="p-4">
          <div className="flex flex-wrap items-center gap-x-6 gap-y-4">
            <div className="flex min-w-0 flex-wrap items-center gap-4">
              <span className="plate-chip text-2xl sm:text-3xl">{prettyPlate(plate)}</span>
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  {profile?.colour && (
                    <span className="chip border-line bg-surface-2 capitalize text-ink-muted">
                      <span
                        className="h-2.5 w-2.5 rounded-full border border-white/20"
                        style={{ background: colourHex(profile.colour) }}
                        aria-hidden
                      />
                      {profile.colour.toLowerCase()}
                    </span>
                  )}
                  <span className="chip border-line bg-surface-2 text-ink-muted">
                    {profile ? `${profile.make ?? 'Unknown make'} ${profile.model ?? ''}`.trim() : 'Profile pending'}
                  </span>
                  {profile?.registrationState && (
                    <span className="chip border-line bg-surface-2 font-mono text-ink-muted">
                      {profile.registrationState}
                    </span>
                  )}
                </div>
                <p className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-2xs text-ink-faint">
                  <span>
                    Plate confidence{' '}
                    <span className="font-mono font-semibold tabular-nums text-ink">
                      {bestConfidence != null ? `${bestConfidence.toFixed(1)}%` : '—'}
                    </span>{' '}
                    (best read)
                  </span>
                  <span className="inline-flex items-center gap-1">
                    <Gauge size={11} aria-hidden />
                    First seen{' '}
                    <span className="font-mono tabular-nums text-ink-muted">
                      {points[0] ? new Date(points[0].timestamp).toLocaleDateString('en-IN') : '—'}
                    </span>
                  </span>
                </p>
              </div>
            </div>

            {/* Officer assignment */}
            <div className="ml-auto flex items-center gap-3 rounded-lg border border-line bg-surface-2/60 px-3.5 py-2.5">
              {officer ? (
                <img
                  src={officer.photoUrl}
                  alt=""
                  className="h-9 w-9 rounded-full object-cover ring-1 ring-line-strong"
                  aria-hidden
                />
              ) : (
                <span className="grid h-9 w-9 place-items-center rounded-full bg-brand/10 text-brand" aria-hidden>
                  <UserRound size={16} />
                </span>
              )}
              <div className="min-w-0">
                <p className="section-label">Case officer</p>
                <p className="truncate text-xs font-semibold text-ink">{caseOfficer}</p>
              </div>
              {openAlert && (
                <button type="button" className="btn-tint btn-xs" onClick={takeCase} disabled={takingCase}>
                  {takingCase ? 'Assigning…' : 'Take this case'}
                </button>
              )}
            </div>
          </div>
        </Panel>

        {/* LEFT — GIS */}
        <Panel
          title="Route on the map"
          icon={MapIcon}
          className="min-h-[420px] xl:col-span-5"
          bodyClassName="relative"
          actions={
            <span className="chip border-high/45 bg-high/10 font-mono text-high">
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
        <div className="flex flex-col gap-3 xl:col-span-4">
          <Panel title="Vehicle details" icon={Car}>
            {profile ? (
              <VehicleInfoPanel profile={profile} />
            ) : (
              <EmptyState
                title="No vehicle profile"
                detail="The registry has no VAHAN record linked to this plate yet."
                action={
                  <button type="button" className="btn-tint btn-xs mt-1" onClick={() => navigate(`/events?plate=${plate}`)}>
                    Check sighting history
                  </button>
                }
              />
            )}
          </Panel>

          <Panel
            title={`Alerts for this vehicle (${vehicleAlerts.length})`}
            icon={ShieldAlert}
            bodyClassName="max-h-[320px] overflow-y-auto"
          >
            {vehicleAlerts.length === 0 ? (
              <EmptyState
                title="No alerts raised"
                detail="This vehicle has not triggered a watchlist alert."
                action={
                  <button type="button" className="btn-tint btn-xs mt-1" onClick={() => navigate('/watchlist')}>
                    Open wanted list
                  </button>
                }
              />
            ) : (
              <div className="space-y-2 p-2.5">
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
            <span className="chip border-line bg-surface-3 text-ink-muted">
              Seen <span className="font-mono tabular-nums">{events.length}</span> times
            </span>
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

/** Common Indian car colour names → a swatch hex (display only). */
function colourHex(name: string): string {
  const map: Record<string, string> = {
    white: '#E8ECEF',
    silver: '#B8C0C8',
    grey: '#7C8794',
    gray: '#7C8794',
    black: '#14181F',
    blue: '#2E6FD8',
    red: '#D63A3A',
    maroon: '#7A1F2B',
    green: '#2E7D4F',
    yellow: '#E7C04A',
    orange: '#E77E2E',
    brown: '#6B4A33',
    beige: '#D9CBB0',
    gold: '#C9A227',
  };
  const key = name.trim().toLowerCase();
  return map[key] ?? '#8B96A5';
}
