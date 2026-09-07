import { Camera, FileImage, MapPin } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import type { VehicleEvent } from '@/types';
import { ConfidenceBar } from '@/components/common/Links';
import { EmptyState } from '@/components/common/Panel';
import { cn, formatDate, formatTime, formatVideoOffset, prettyVehicleClass } from '@/lib/utils';

/** Detection history table for a traced vehicle. */
export function DetectionTable({
  events,
  activeEventId,
  onViewEvidence,
  onViewOnMap,
  className,
}: {
  events: VehicleEvent[];
  activeEventId?: string | null;
  onViewEvidence?: (event: VehicleEvent) => void;
  onViewOnMap?: (event: VehicleEvent) => void;
  className?: string;
}) {
  const navigate = useNavigate();

  if (!events.length) {
    return <EmptyState title="No detections" detail="No camera has recorded this registration number." />;
  }

  return (
    <div className={cn('overflow-x-auto', className)}>
      <table className="data-table">
        <caption className="sr-only">Detection history</caption>
        <thead>
          <tr>
            <th scope="col">Date</th>
            <th scope="col">Time</th>
            <th scope="col">Camera</th>
            <th scope="col">Place</th>
            <th scope="col">Vehicle type</th>
            <th scope="col">Plate match</th>
            <th scope="col">Photo</th>
            <th scope="col" className="text-right">
              Actions
            </th>
          </tr>
        </thead>
        <tbody>
          {events.map((e) => (
            <tr key={e.id} className={cn(activeEventId === e.id && 'bg-high/10')}>
              <td className="font-mono text-2xs text-ink-faint">{formatDate(e.timestamp)}</td>
              <td className="font-mono tabular-nums text-ink">
                {formatTime(e.timestamp)}
                {e.videoOffsetSec != null && (
                  <span className="ml-1.5 text-2xs font-normal text-ink-faint">
                    · {formatVideoOffset(e.videoOffsetSec)}
                  </span>
                )}
              </td>
              <td className="font-mono text-ink-muted">{e.cameraName ?? e.cameraId.toUpperCase()}</td>
              <td className="max-w-[200px] truncate text-ink-muted">{e.location}</td>
              <td className="text-ink-muted">{prettyVehicleClass(e.vehicleClass)}</td>
              <td>
                <ConfidenceBar value={e.plateConfidence} />
              </td>
              <td className="font-mono text-2xs text-ink-faint">{e.evidenceRef ?? '—'}</td>
              <td>
                <div className="flex justify-end gap-1">
                  <button
                    type="button"
                    className="btn-ghost btn-xs"
                    onClick={() => navigate(`/cameras/${e.cameraId}`)}
                    aria-label={`View camera ${e.cameraName ?? e.cameraId}`}
                  >
                    <Camera size={11} aria-hidden /> Open camera
                  </button>
                  {onViewEvidence && (
                    <button
                      type="button"
                      className="btn-ghost btn-xs"
                      onClick={() => onViewEvidence(e)}
                      aria-label={`View evidence for detection at ${formatTime(e.timestamp)}`}
                    >
                      <FileImage size={11} aria-hidden /> See photo
                    </button>
                  )}
                  {onViewOnMap && (
                    <button
                      type="button"
                      className="btn-ghost btn-xs"
                      onClick={() => onViewOnMap(e)}
                      aria-label={`Show detection at ${formatTime(e.timestamp)} on map`}
                    >
                      <MapPin size={11} aria-hidden /> Show on map
                    </button>
                  )}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
