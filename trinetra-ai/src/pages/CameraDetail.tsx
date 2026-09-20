import { useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Activity, MapPin, ScanLine } from 'lucide-react';
import { InvestigationLayout } from '@/layouts/InvestigationLayout';
import { CameraPlayer } from '@/components/camera/CameraPlayer';
import { UploadedVideoPanel } from '@/components/camera/UploadedVideoPanel';
import { EvidencePanel } from '@/components/vehicle/EvidencePanel';
import { LazyMap } from '@/components/gis/LazyMap';
import { Panel, AsyncBoundary, KeyValue, ErrorState } from '@/components/common/Panel';
import { StatusChip } from '@/components/common/Chips';
import { PlateLink, ConfidenceBar } from '@/components/common/Links';
import { useCamera } from '@/hooks/useCameras';
import { useEventSearch } from '@/hooks/useEvents';
import type { VehicleEvent } from '@/types';
import { formatDateTime, formatTime, formatVideoOffset, relativeTime, prettyEventType, prettyVehicleClass } from '@/lib/utils';

export default function CameraDetail() {
  const { cameraId = '' } = useParams();
  const navigate = useNavigate();
  const { data: camera, loading, error, refresh } = useCamera(cameraId);
  const events = useEventSearch({ cameraId }, 1, 30);
  const [selected, setSelected] = useState<VehicleEvent | null>(null);
  const [watchlistOnly, setWatchlistOnly] = useState(false);

  const all = useMemo(() => events.data?.items ?? [], [events.data]);
  const list = useMemo(
    () => (watchlistOnly ? all.filter((e) => e.watchlistMatch) : all),
    [all, watchlistOnly],
  );
  const watchlistHits = useMemo(() => all.filter((e) => e.watchlistMatch).length, [all]);
  const activeEvidence = selected ?? list[0] ?? null;

  if (error) {
    return (
      <div className="p-6">
        <ErrorState message={`Camera "${cameraId}" could not be loaded. ${error}`} onRetry={refresh} />
      </div>
    );
  }

  return (
    <InvestigationLayout
      backTo="/cameras"
      backLabel="Back to cameras"
      title={
        <div className="flex items-baseline gap-2">
          <span className="font-mono text-sm font-bold text-ink">{camera?.name ?? cameraId.toUpperCase()}</span>
          <span className="truncate text-2xs text-ink-muted">{camera?.location}</span>
        </div>
      }
      status={camera && <StatusChip status={camera.status} />}
      meta={
        camera && (
          <>
            <span className="text-2xs text-ink-faint">
              {events.data?.total ?? '—'} logged sightings
            </span>
            <span className="text-2xs text-ink-faint">
              Picture quality{' '}
              <span className="font-mono text-ink-muted">
                {camera.width && camera.height && camera.width >= 1920
                  ? 'High (HD)'
                  : 'Standard'}
              </span>
            </span>
          </>
        )
      }
      actions={
        camera && (
          <button
            type="button"
            className="btn-ghost btn-xs"
            onClick={() => navigate(`/gis?focus=${camera.id}`)}
          >
            <MapPin size={11} aria-hidden /> View on Map
          </button>
        )
      }
    >
      <AsyncBoundary loading={loading || !camera} error={error} onRetry={refresh} loadingLabel="Loading camera">
        {camera && (
          <div className="grid gap-3 p-4 sm:gap-4 sm:p-5">
            {/* MAIN — player + recent AI events */}
            <div className="flex flex-col gap-3 sm:gap-4 xl:col-span-8">
              <CameraPlayer camera={camera} autoRequest />

              {camera.streamType === 'FILE' && <UploadedVideoPanel cameraId={camera.id} />}

              <Panel
                title="Vehicles seen by this camera"
                icon={ScanLine}
                actions={
                  <>
                    <button
                      type="button"
                      onClick={() => setWatchlistOnly((v) => !v)}
                      aria-pressed={watchlistOnly}
                      className={
                        watchlistOnly
                          ? 'chip border-critical/50 bg-critical/15 text-critical'
                          : 'chip border-line bg-surface-3 text-ink-muted hover:border-critical/40 hover:text-critical'
                      }
                    >
                      Wanted vehicles · {watchlistHits}
                    </button>
                    <span className="chip border-line bg-surface-3 text-ink-muted">
                      {list.length} recent
                    </span>
                  </>
                }
              >
                <AsyncBoundary
                  loading={events.loading}
                  error={events.error}
                  onRetry={events.refresh}
                  isEmpty={!list.length}
                  emptyTitle="No AI events"
                  emptyDetail="This camera has not produced detections in the retained window."
                  loadingLabel="Loading detections"
                >
                  <div className="max-h-[380px] overflow-auto">
                    <table className="data-table">
                      <thead>
                        <tr>
                          <th scope="col">Time</th>
                          <th scope="col">Plate</th>
                          <th scope="col">Vehicle type</th>
                          <th scope="col">Plate match</th>
                          <th scope="col">What happened</th>
                          <th scope="col" className="text-right">
                            Evidence
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        {list.map((e) => (
                          <tr key={e.id} data-event-id={e.id} className={activeEvidence?.id === e.id ? 'bg-brand/10' : undefined}>
                            <td className="font-mono tabular-nums text-ink">
                              {formatTime(e.timestamp)}
                              {e.videoOffsetSec != null && (
                                <span className="ml-1.5 text-2xs text-ink-faint">
                                  · {formatVideoOffset(e.videoOffsetSec)}
                                </span>
                              )}
                            </td>
                            <td>
                              <PlateLink plate={e.plate} size="xs" />
                              {e.plateStatus === 'LOW_CONFIDENCE' && <span className="ml-2 text-2xs text-degraded">Verify read</span>}
                              {e.plateStatus === 'SIMULATED' && <span className="ml-2 text-2xs text-degraded">Demo</span>}
                            </td>
                            <td className="text-ink-muted">{prettyVehicleClass(e.vehicleClass)}</td>
                            <td>
                              <ConfidenceBar value={e.plateConfidence} />
                            </td>
                            <td>
                              {e.watchlistMatch ? (
                                <span className="chip border-critical/45 bg-critical/10 text-critical">
                                  Watchlist
                                </span>
                              ) : (
                                <span className="text-2xs text-ink-faint">
                                  {prettyEventType(e.eventType)}
                                </span>
                              )}
                            </td>
                            <td className="text-right">
                              <button type="button" className="btn-ghost btn-xs" onClick={() => setSelected(e)}>
                                View
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </AsyncBoundary>
              </Panel>
            </div>

            {/* SIDE — metadata, location, evidence */}
            <div className="flex flex-col gap-3 sm:gap-4 xl:col-span-4">
              <Panel title="Camera details" icon={Activity}>
                <dl className="grid grid-cols-2 gap-x-4 gap-y-2.5 p-4">
                  <KeyValue label="Camera ID">
                    <span className="font-mono">{camera.id}</span>
                  </KeyValue>
                  <KeyValue label="Name">
                    <span className="font-mono">{camera.name}</span>
                  </KeyValue>
                  <KeyValue label="Status">
                    <StatusChip status={camera.status} />
                  </KeyValue>
                  <KeyValue label="Connection">
                    <span className="font-mono">{camera.streamType}</span>
                  </KeyValue>
                  <KeyValue label="Video format">
                    <span className="font-mono">{camera.codec}</span>
                  </KeyValue>
                  <KeyValue label="Resolution">
                    <span className="font-mono">
                      {camera.width}×{camera.height}
                    </span>
                  </KeyValue>
                  <KeyValue label="Frames per second">
                    <span className="font-mono">{camera.fps} fps</span>
                  </KeyValue>
                  <KeyValue label="Department">{camera.department}</KeyValue>
                  <KeyValue label="Zone">{camera.zone}</KeyValue>
                  <KeyValue label="Map position">
                    <span className="font-mono">
                      {camera.latitude.toFixed(5)}, {camera.longitude.toFixed(5)}
                    </span>
                  </KeyValue>
                  <KeyValue label="Last checked">{formatDateTime(camera.lastSeen)}</KeyValue>
                  <KeyValue label="Last vehicle seen">{relativeTime(camera.lastEventAt)}</KeyValue>
                </dl>
              </Panel>

              <Panel title="Where this camera is" icon={MapPin} className="min-h-[220px]" bodyClassName="relative isolate">
                <LazyMap
                  cameras={[camera]}
                  selectedCameraId={camera.id}
                  className="absolute inset-0"
                  zoom={15}
                  center={[camera.latitude, camera.longitude]}
                  fit={false}
                />
              </Panel>

              <Panel title="Photo evidence" icon={ScanLine}>
                <EvidencePanel event={activeEvidence} dense />
              </Panel>
            </div>
          </div>
        )}
      </AsyncBoundary>
    </InvestigationLayout>
  );
}
