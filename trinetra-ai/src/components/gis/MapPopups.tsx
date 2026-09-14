import { Link } from 'react-router-dom';
import { Play } from 'lucide-react';
import type { Camera, RoutePoint, VehicleEvent } from '@/types';
import { formatDateTime, formatDuration, formatTime, prettyPlate, prettyVehicleClass } from '@/lib/utils';
import { useRoadLeg } from '@/hooks/useRoadLegs';
import { StatusChip } from '@/components/common/Chips';

/** Popups intentionally repeat the key investigative fields: camera, time, plate, confidence. */

export function CameraPopup({
  camera,
  onWatch,
}: {
  camera: Camera;
  /** Opens the camera's live feed on the map (floating player). */
  onWatch?: (camera: Camera) => void;
}) {
  return (
    <div className="min-w-[210px] p-2.5 text-ink">
      <div className="mb-1.5 flex items-center justify-between gap-2">
        <p className="font-mono text-xs font-bold">{camera.name}</p>
        <StatusChip status={camera.status} />
      </div>
      <p className="mb-2 text-2xs text-ink-muted">{camera.location}</p>
      <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-2xs">
        <dt className="text-ink-faint">Department</dt>
        <dd className="text-right">{camera.department ?? '—'}</dd>
        <dt className="text-ink-faint">Codec</dt>
        <dd className="text-right font-mono">{camera.codec ?? '—'}</dd>
        <dt className="text-ink-faint">Resolution</dt>
        <dd className="text-right font-mono">
          {camera.width ? `${camera.width}×${camera.height}` : '—'}
        </dd>
        <dt className="text-ink-faint">Events 24h</dt>
        <dd className="text-right font-mono">{camera.eventCount24h ?? 0}</dd>
        <dt className="text-ink-faint">Coordinates</dt>
        <dd className="text-right font-mono">
          {camera.latitude != null && camera.longitude != null
            ? `${camera.latitude.toFixed(4)}, ${camera.longitude.toFixed(4)}`
            : '—'}
        </dd>
      </dl>
      <div className="mt-2.5 grid grid-cols-2 gap-1.5">
        {onWatch && camera.status !== 'OFFLINE' ? (
          <button type="button" onClick={() => onWatch(camera)} className="btn-primary btn-xs">
            <Play size={10} aria-hidden /> Watch Live
          </button>
        ) : (
          <span className="btn-ghost btn-xs cursor-not-allowed justify-center opacity-50">
            {camera.status === 'OFFLINE' ? 'Camera offline' : 'No live stream'}
          </span>
        )}
        <Link to={`/cameras/${camera.id}`} className="btn-ghost btn-xs justify-center">
          Camera Detail
        </Link>
      </div>
    </div>
  );
}

export function EventPopup({ event }: { event: VehicleEvent }) {
  return (
    <div className="min-w-[210px] p-2.5 text-ink">
      <p className="plate text-sm">{prettyPlate(event.plate)}</p>
      <p className="mb-2 text-2xs text-ink-muted">
        {event.cameraName ?? event.cameraId.toUpperCase()} · {event.location}
      </p>
      <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-2xs">
        <dt className="text-ink-faint">Timestamp</dt>
        <dd className="text-right font-mono">{formatDateTime(event.timestamp)}</dd>
        <dt className="text-ink-faint">Event Type</dt>
        <dd className="text-right">{event.eventType.replace(/_/g, ' ')}</dd>
        <dt className="text-ink-faint">Confidence</dt>
        <dd className="text-right font-mono">{event.plateConfidence.toFixed(1)}%</dd>
        <dt className="text-ink-faint">Class</dt>
        <dd className="text-right">{prettyVehicleClass(event.vehicleClass)}</dd>
      </dl>
      <div className="mt-2.5 grid grid-cols-2 gap-1.5">
        <Link to={`/vehicles/${event.plate}`} className="btn-primary btn-xs">
          Investigate
        </Link>
        <Link to={`/cameras/${event.cameraId}`} className="btn-ghost btn-xs">
          Camera
        </Link>
      </div>
    </div>
  );
}

export function RoutePopup({
  point,
  prev,
  plate,
}: {
  point: RoutePoint;
  prev?: RoutePoint;
  plate?: string;
}) {
  const leg = useRoadLeg(prev, point);
  return (
    <div className="min-w-[210px] p-2.5 text-ink">
      <div className="mb-1.5 flex items-center gap-2">
        <span className="grid h-5 w-5 place-items-center rounded-full bg-high font-mono text-2xs font-bold text-black">
          {point.sequence}
        </span>
        <p className="font-mono text-xs font-bold">{point.cameraName}</p>
      </div>
      <p className="mb-2 text-2xs text-ink-muted">{point.location}</p>
      {plate && (
        <p className="mb-2 font-mono text-2xs font-semibold text-brand">{plate}</p>
      )}
      <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-2xs">
        <dt className="text-ink-faint">Sighting time</dt>
        <dd className="text-right font-mono">{formatTime(point.timestamp)}</dd>
        <dt className="text-ink-faint">Plate confidence</dt>
        <dd className="text-right font-mono">{point.plateConfidence.toFixed(1)}%</dd>
        {point.gapMinutes != null && (
          <>
            <dt className="text-ink-faint">Gap from previous</dt>
            <dd className="text-right font-mono">{point.gapMinutes.toFixed(0)} min</dd>
          </>
        )}
        {prev?.cameraId === point.cameraId ? (
          <>
            <dt className="text-ink-faint">Leg</dt>
            <dd className="text-right font-mono">Same camera</dd>
          </>
        ) : (
          <>
            {leg != null && (
              <>
                <dt className="text-ink-faint">Road distance</dt>
                <dd className="text-right font-mono">
                  {leg.roadKm >= 10 ? leg.roadKm.toFixed(0) : leg.roadKm.toFixed(1)} km
                </dd>
                <dt className="text-ink-faint">Typical drive</dt>
                <dd className="text-right font-mono">{formatDuration(leg.typicalMinutes)}</dd>
              </>
            )}
            {point.speedKmph != null && (point.gapMinutes ?? 0) >= 1 && (
              <>
                <dt className="text-ink-faint">Avg speed</dt>
                <dd className="text-right font-mono">{point.speedKmph} km/h</dd>
              </>
            )}
          </>
        )}
      </dl>
      <div className="mt-2.5 grid gap-1.5">
        {plate && (
          <Link to={`/vehicles/${plate}`} className="btn-primary btn-xs w-full">
            View vehicle &amp; evidence
          </Link>
        )}
        <Link to={`/cameras/${point.cameraId}`} className="btn-ghost btn-xs w-full">
          Open {point.cameraName}
        </Link>
      </div>
    </div>
  );
}
