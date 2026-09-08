import { useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { Activity, ChevronLeft, Gauge, MapPin } from 'lucide-react';
import { useCamera } from '@/hooks/useCameras';
import { useLiveEvents } from '@/hooks/useLiveEvents';
import { Player } from '@/components/Player';
import { DetectionTable } from '@/components/DetectionTable';
import { MapCanvas } from '@/components/MapCanvas';
import { Evidence } from '@/components/Evidence';
import { Modal } from '@/ui/Modal';
import { CameraStatusBadge } from '@/ui/Badge';
import { Button, buttonClass } from '@/ui/Button';
import { Badge } from '@/ui/Badge';
import { Card, CardBody, CardFooter, CardHeader, SectionLabel } from '@/ui/Card';
import { EmptyState, KeyVal, LoadingRows, Skeleton } from '@/ui/Feedback';
import { PlateLink, Stat } from '@/ui/Links';
import { relativeTime } from '@/lib/utils';
import { formatDateTime } from '@/lib/uiHelpers';import { uploadService } from '@/services/uploadService';
import { useAsync } from '@/hooks/useAsync';

/**
 * Camera monitor — SOC layout: video primary and large, detections
 * and diagnostics supporting, evidence on demand. The overview strip
 * carries capture format facts; the AI panel only appears for
 * record-and-process cameras.
 */
export default function CameraDetail() {
  const { cameraId = '' } = useParams();
  const { data: camera, loading, error, refresh } = useCamera(cameraId);
  const { events } = useLiveEvents();
  const [evidence, setEvidence] = useState<string | null>(null);

  const uploadDetail = useAsync(
    () => uploadService.detail(cameraId),
    [cameraId],
    { enabled: Boolean(cameraId) },
  );
  const isUploadCamera =
    !uploadDetail.loading && !uploadDetail.error && uploadDetail.data != null;

  const history = useMemo(() => {
    const fromFeed = events.filter((e) => e.cameraId === cameraId);
    return fromFeed;
  }, [events, cameraId]);

  if (loading) {
    return (
      <div className="p-4 sm:p-6 lg:p-8">
        <Skeleton className="h-7 w-64" />
        <div className="mt-5 grid gap-6 xl:grid-cols-[1fr_340px]">
          <Skeleton className="aspect-video w-full rounded-xl" />
          <div className="space-y-4">
            <Skeleton className="h-40" />
            <Skeleton className="h-40" />
          </div>
        </div>
      </div>
    );
  }

  if (error || !camera) {
    return (
      <div className="p-4 sm:p-6 lg:p-8">
        <EmptyState
          title="Camera not found"
          detail={error ?? `No camera with ID “${cameraId}” is in the registry.`}
          action={
            <Link to="/cameras" className={buttonClass('secondary', 'sm')}>
              Back to cameras
            </Link>
          }
        />
      </div>
    );
  }

  const feed = history.length > 0 ? history : [];

  return (
    <div className="p-4 sm:p-6 lg:p-8">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-3">
          <Link
            to="/cameras"
            className="grid h-9 w-9 shrink-0 place-items-center rounded-lg text-ink-muted transition-all duration-150 hover:bg-surface-2 hover:text-ink active:scale-95"
            aria-label="Back to all cameras"
          >
            <ChevronLeft size={17} aria-hidden />
          </Link>
          <div className="min-w-0">
            <h2 className="mono flex flex-wrap items-center gap-x-3 gap-y-1 text-lg font-semibold text-ink">
              {camera.name}
              <CameraStatusBadge status={camera.status} />
            </h2>
            <p className="mt-0.5 flex items-center gap-1.5 text-xs text-ink-muted">
              <MapPin size={11} aria-hidden /> {camera.location}
              <span className="text-ink-faint">· {camera.department ?? '—'}</span>
              {camera.zone && <span className="text-ink-faint">· Zone {camera.zone}</span>}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="ghost" onClick={refresh}>
            <Activity size={13} aria-hidden /> Refresh
          </Button>
          <Link to={`/gis?focus=${camera.id}`} className={buttonClass('secondary', 'sm')}>
            <MapPin size={13} aria-hidden /> Show on map
          </Link>
        </div>
      </div>

      <div className="mt-5 grid min-h-0 gap-6 xl:grid-cols-[1fr_340px]">
        {/* Left: video + detections */}
        <div className="flex min-w-0 flex-col gap-6">
          <Player camera={camera} autoRequest />

          <Card>
            <CardHeader
              title="Detections at this camera"
              subtitle="Live feed rows appear instantly; the full log is in the Vehicle Log"
              actions={
                <Link to={`/events?cameraId=${camera.id}`} className={buttonClass('ghost', 'xs')}>
                  Full log →
                </Link>
              }
            />
            <CardBody>
              <DetectionTable events={feed} activeEventId={null} onViewEvidence={(ev) => setEvidence(ev.id)} />
            </CardBody>
          </Card>
        </div>

        {/* Right rail: capture facts, AI, location */}
        <aside className="flex min-w-0 flex-col gap-6">
          <Card>
            <CardHeader title="Capture" subtitle="Fixed installation facts" />
            <CardBody className="p-5">
              <dl className="grid grid-cols-2 gap-x-4 gap-y-4">
                <KeyVal label="Video format">
                  <Badge tone="neutral">{camera.codec ?? '—'}</Badge>
                </KeyVal>
                <KeyVal label="Stream type">{camera.streamType ?? '—'}</KeyVal>
                <KeyVal label="Resolution">
                  {camera.width ? `${camera.width} × ${camera.height}` : '—'}
                </KeyVal>
                <KeyVal label="Frame rate">{camera.fps ? `${camera.fps} fps` : '—'}</KeyVal>
                <KeyVal label="Installed">
                  {camera.installedAt ? formatDateTime(camera.installedAt) : '—'}
                </KeyVal>
                <KeyVal label="Last heartbeat">
                  {camera.lastSeen ? relativeTime(camera.lastSeen) : '—'}
                </KeyVal>
              </dl>
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="Today at this post" subtitle="Rolling 24-hour counters" />
            <CardBody className="grid grid-cols-2 divide-x divide-line">
              <Stat label="Vehicles seen" value={camera.eventCount24h ?? 0} />
              <Stat
                label="Last vehicle"
                value={camera.lastEventAt ? formatDateTime(camera.lastEventAt).split(', ')[1] ?? formatDateTime(camera.lastEventAt) : '—'}
                sub={camera.lastEventAt ? relativeTime(camera.lastEventAt) : undefined}
              />
            </CardBody>
            <CardFooter>
              <p className="flex items-center gap-2 text-xs text-ink-faint">
                <Gauge size={12} aria-hidden />
                Counters come from the ingest pipeline, not estimates.
              </p>
            </CardFooter>
          </Card>

          {isUploadCamera && (
            <Card>
              <CardHeader
                title="AI analysis job"
                subtitle="This camera is a record-and-process source"
                actions={<Badge tone="accent">{uploadDetail.data?.jobStatus ?? 'IDLE'}</Badge>}
              />
              <CardBody className="p-5">
                {uploadDetail.data?.jobStatus === 'PROCESSING' && (
                  <div className="mb-4">
                    <div className="h-1.5 overflow-hidden rounded-full bg-surface-3">
                      <div
                        className="h-full rounded-full bg-accent transition-[width] duration-500"
                        style={{ width: `${uploadDetail.data.progressPct ?? 0}%` }}
                      />
                    </div>
                    <p className="mono mt-1.5 text-[11px] text-ink-faint">
                      {uploadDetail.data.framesProcessed?.toLocaleString('en-IN')} /{' '}
                      {uploadDetail.data.framesTotal?.toLocaleString('en-IN')} frames ·{' '}
                      {uploadDetail.data.progressPct ?? 0}%
                    </p>
                  </div>
                )}
                <dl className="grid grid-cols-3 gap-3">
                  <KeyVal label="Vehicles seen">{uploadDetail.data?.vehiclesSeen ?? 0}</KeyVal>
                  <KeyVal label="Plates read">{uploadDetail.data?.platesRead ?? 0}</KeyVal>
                  <KeyVal label="Frames">{uploadDetail.data?.framesTotal?.toLocaleString('en-IN') ?? '—'}</KeyVal>
                </dl>
                {uploadDetail.data?.jobError && (
                  <p className="mt-3 rounded-lg border border-critical/25 bg-critical/[0.05] px-3 py-2 text-xs text-critical">
                    {uploadDetail.data.jobError}
                  </p>
                )}
                {(uploadDetail.data?.recentPlates?.length ?? 0) > 0 && (
                  <div className="mt-4 border-t border-line pt-3.5">
                    <SectionLabel>Recent plate reads</SectionLabel>
                    <ul className="mt-2 space-y-1.5">
                      {uploadDetail.data!.recentPlates.slice(0, 6).map((p) => (
                        <li key={p.id} className="flex items-center justify-between gap-2">
                          <PlateLink plate={p.plate} size="xs" />
                          <span className="mono text-[10.5px] text-ink-faint">{formatDateTime(p.timestamp)}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </CardBody>
            </Card>
          )}

          <Card className="overflow-hidden">
            <CardHeader title="Location" subtitle="Network map position" />
            <CardBody>
              <MapCanvas
                cameras={[camera]}
                fit={false}
                zoom={15}
                center={[camera.latitude, camera.longitude]}
                className="h-56 w-full"
              />
            </CardBody>
          </Card>
        </aside>
      </div>

      {/* Evidence modal */}
      <Modal
        open={Boolean(evidence)}
        onClose={() => setEvidence(null)}
        title="Detection evidence"
        size="lg"
      >
        {evidence &&
          (feed.find((e) => e.id === evidence) ? (
            <Evidence ev={feed.find((e) => e.id === evidence)!} dense />
          ) : (
            <LoadingRows label="Loading evidence" />
          ))}
      </Modal>
    </div>
  );
}
