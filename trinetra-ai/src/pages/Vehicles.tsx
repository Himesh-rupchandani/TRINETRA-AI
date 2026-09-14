import { useEffect, useMemo } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { ArrowRight, Car, Images, MapPin, Route, Search as SearchIcon, ShieldAlert, ShieldCheck } from 'lucide-react';
import { PageHeader } from '@/components/layout/PageHeader';
import { TraceSearchBar } from '@/components/vehicle/TraceSearchBar';
import { Panel, EmptyState, LoadingState, ErrorState } from '@/components/common/Panel';
import { InvalidPlateNotice } from '@/components/vehicle/InvalidPlateNotice';
import { IconTile } from '@/components/common/IconTile';
import { SeverityChip } from '@/components/common/Chips';
import { PlateLink } from '@/components/common/Links';
import { useVehicleSearch } from '@/hooks/useVehicleSearch';
import { useAsync } from '@/hooks/useAsync';
import { vehicleService } from '@/services/vehicleService';
import { formatDateTime, formatTime, formatVideoOffset, isValidPlate, prettyPlate } from '@/lib/utils';
import { EvidenceThumbs, VehicleLogGallery } from '@/components/vehicle/VehicleLogGallery';

/**
 * VEHICLE SEARCH — the hero screen.
 * Registration number in, watchlist verdict + sightings out, one click to
 * the full investigation workspace.
 */
export default function Vehicles() {
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const { result, loading, error, searched, trace } = useVehicleSearch();
  const watchlist = useAsync(() => vehicleService.watchlist(), []);
  const initial = params.get('plate') ?? '';

  useEffect(() => {
    if (initial) void trace(initial);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initial]);

  const onTrace = (plate: string) => {
    setParams({ plate });
    void trace(plate);
  };

  const wl = result?.profile?.watchlist;
  const sightings = useMemo(() => result?.events ?? [], [result]);

  return (
    <div className="flex h-full flex-col">
      <PageHeader
        title="Find a Vehicle"
        icon={Car}
        tone="sky"
        subtitle="Type a number plate to see everywhere it has been seen."
      />

      <div className="min-h-0 flex-1 overflow-auto">
        <div className="mx-auto max-w-5xl p-4 sm:p-6">
          <section className="panel p-5 sm:p-6">
            <div className="flex items-center gap-3">
              <IconTile tone="blue" size="lg">
                <SearchIcon size={20} aria-hidden />
              </IconTile>
              <h2 className="text-lg font-bold text-ink">Which vehicle are you looking for?</h2>
            </div>
            <p className="mt-2.5 text-sm leading-relaxed text-ink-muted">
              Enter the number plate. We will check all 30 cameras and show you every place it
              has been seen, in order, on a map.
            </p>
            <div className="mt-4">
              <TraceSearchBar initialValue={initial} onTrace={onTrace} loading={loading} size="lg" />
            </div>
          </section>

          {loading && (
            <div className="panel mt-4">
              <LoadingState label={`Checking all 30 cameras for ${initial || 'this vehicle'}…`} rows={5} />
            </div>
          )}

          {error && !loading && (
            <div className="panel mt-4">
              {!isValidPlate(initial || '') ? (
                <InvalidPlateNotice raw={initial} />
              ) : (
                <ErrorState message={error} />
              )}
            </div>
          )}

          {!loading && !error && searched && result && sightings.length === 0 && (
            <div className="panel mt-4">
              <EmptyState
                title={`No sightings for ${result.plate}`}
                detail="This registration number has not been recorded by any camera in the retained window. Check the format or widen the time range in the Event Explorer."
              />
            </div>
          )}

          {!loading && !error && result && sightings.length > 0 && (
            <>
              {/* Verdict card */}
              <section
                className={`panel mt-4 border-l-4 ${wl?.active ? 'border-l-critical' : 'border-l-online'}`}
              >
                <div className="flex flex-wrap items-center justify-between gap-4 p-4 sm:p-5">
                  <div>
                    <p className="plate text-2xl text-ink">{prettyPlate(result.plate)}</p>
                    <p className="mt-2 flex items-center gap-1.5 text-xs font-bold uppercase tracking-wide">
                      {wl?.active ? (
                        <span className="flex items-center gap-1.5 text-critical">
                          <ShieldAlert size={14} aria-hidden /> Watchlist Match
                        </span>
                      ) : (
                        <span className="flex items-center gap-1.5 text-online">
                          <ShieldCheck size={15} aria-hidden /> Not on the wanted list
                        </span>
                      )}
                    </p>
                  </div>

                  <dl className="grid grid-cols-2 gap-x-8 gap-y-2 sm:grid-cols-4">
                    <div>
                      <dt className="kv-label">Why it is wanted</dt>
                      <dd className="mt-1 text-sm font-semibold text-ink">{wl?.category ?? '—'}</dd>
                    </div>
                    <div>
                      <dt className="kv-label">Priority</dt>
                      <dd className="mt-1">
                        {wl ? <SeverityChip severity={wl.severity} /> : <span className="text-sm font-semibold text-ink">—</span>}
                      </dd>
                    </div>
                    <div>
                      <dt className="kv-label">Times seen</dt>
                      <dd className="mt-1 font-mono text-xl font-bold tabular-nums text-ink">{sightings.length}</dd>
                    </div>
                    <div>
                      <dt className="kv-label">Seen by</dt>
                      <dd className="mt-1 font-mono text-xl font-bold tabular-nums text-ink">
                        {result.route?.camerasTouched ?? 0}
                      </dd>
                    </div>
                  </dl>
                </div>

                {wl?.active && (
                  <p className="border-t border-line px-4 py-2.5 text-2xs text-ink-muted sm:px-5">
                    <span className="font-semibold text-ink">{wl.caseRef}</span> · {wl.reason} · Added by{' '}
                    {wl.addedBy} on {formatDateTime(wl.addedAt)}
                  </p>
                )}

                <div className="flex flex-wrap items-center gap-2.5 border-t border-line px-4 py-3 sm:px-5">
                  <button
                    type="button"
                    className="btn-solid"
                    onClick={() => navigate(`/vehicles/${result.plate}`)}
                  >
                    See where it went <ArrowRight size={14} aria-hidden />
                  </button>
                  <button
                    type="button"
                    className="btn-ghost"
                    onClick={() => navigate(`/gis?plate=${result.plate}`)}
                  >
                    <Route size={13} aria-hidden /> Show on map
                  </button>
                  <button
                    type="button"
                    className="btn-ghost"
                    onClick={() => navigate(`/events?plate=${result.plate}`)}
                  >
                    Every sighting
                  </button>
                  <span className="ml-auto text-2xs text-ink-faint">
                    First seen {formatDateTime(result.profile?.firstSeen)} · last seen{' '}
                    {formatDateTime(result.profile?.lastSeen)}
                  </span>
                </div>
              </section>

              {/* All provided images visible in Vehicle Log — primary request */}
              <VehicleLogGallery events={sightings} title={`All provided images — ${prettyPlate(result.plate)} in Vehicle Log`} className="mt-4" />

              {/* Sightings list with inline thumbnails so every row shows its photo without extra clicks */}
              <Panel
                title={`Sightings — ${sightings.length} records`}
                icon={MapPin}
                className="mt-4"
                actions={
                  <span className="chip border-line bg-surface-3 text-ink-muted">
                    {result.route?.totalDistanceKm ?? 0} km tracked
                  </span>
                }
              >
                <ol className="divide-y divide-line/60">
                  {sightings.map((e, i) => (
                    <li key={e.id} className="flex items-center gap-3 px-4 py-2.5 hover:bg-surface-2">
                      <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full border border-line bg-surface-3 font-mono text-2xs font-bold text-ink-muted">
                        {i + 1}
                      </span>
                      <time className="w-[74px] shrink-0 font-mono text-xs tabular-nums text-ink" dateTime={e.timestamp}>
                        {formatTime(e.timestamp)}
                        {e.videoOffsetSec != null && (
                          <span className="block text-2xs font-normal text-ink-faint">
                            {formatVideoOffset(e.videoOffsetSec)}
                          </span>
                        )}
                      </time>
                      <span className="w-[62px] shrink-0 font-mono text-xs text-ink-muted">
                        {e.cameraName ?? e.cameraId.toUpperCase()}
                      </span>
                      <span className="min-w-0 flex-1 truncate text-xs text-ink-muted">{e.location}</span>
                      <span className="hidden shrink-0 sm:block">
                        <EvidenceThumbs event={e} onClick={() => navigate(`/vehicles/${result.plate}`)} />
                      </span>
                      <span className="hidden font-mono text-2xs tabular-nums text-ink-faint sm:block">
                        {e.plateConfidence.toFixed(1)}%
                      </span>
                      <button
                        type="button"
                        className="btn-ghost btn-xs shrink-0"
                        onClick={() => navigate(`/cameras/${e.cameraId}`)}
                      >
                        Open camera
                      </button>
                      <button
                        type="button"
                        className="btn-ghost btn-xs shrink-0 sm:hidden"
                        onClick={() => navigate(`/vehicles/${result.plate}`)}
                      >
                        <Images size={11} aria-hidden /> Photos
                      </button>
                    </li>
                  ))}
                </ol>
              </Panel>
            </>
          )}

          {/* Watchlist shortcut */}
          {!result && !loading && (
            <Panel title="Vehicles being watched" icon={ShieldAlert} className="mt-4">
              {watchlist.loading ? (
                <LoadingState label="Loading watchlist" />
              ) : (
                <div className="overflow-x-auto">
                  <table className="data-table data-table-page">
                    <thead>
                      <tr>
                        <th scope="col">Plate</th>
                        <th scope="col">Why it is wanted</th>
                        <th scope="col">Priority</th>
                        <th scope="col">Case number</th>
                        <th scope="col">Added on</th>
                        <th scope="col" className="text-right">
                          Action
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {(watchlist.data ?? [])
                        .filter((w) => w.active)
                        .map((w) => (
                          <tr key={w.id}>
                            <td>
                              <PlateLink plate={w.plate} />
                            </td>
                            <td className="text-ink-muted">{w.category}</td>
                            <td>
                              <SeverityChip severity={w.severity} />
                            </td>
                            <td className="font-mono text-2xs text-ink-muted">{w.caseRef}</td>
                            <td className="text-2xs text-ink-faint">{formatDateTime(w.addedAt)}</td>
                            <td className="text-right">
                              <button
                                type="button"
                                className="btn-tint btn-xs"
                                onClick={() => onTrace(w.plate)}
                              >
                                Find it
                              </button>
                            </td>
                          </tr>
                        ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Panel>
          )}
        </div>
      </div>
    </div>
  );
}
