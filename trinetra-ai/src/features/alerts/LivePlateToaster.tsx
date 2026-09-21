import { useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useLive } from './LiveProvider';
import { useToast } from '@/features/system/ToastProvider';
import { PlateNotificationGate } from '@/lib/liveDetections';
import { isMockMode } from '@/services/api';

/** Ordinary plate reads are notifications, not police/watchlist alarms. */
export function LivePlateToaster() {
  const { plateNotifications } = useLive();
  const toast = useToast();
  const navigate = useNavigate();
  const gate = useRef(new PlateNotificationGate());

  useEffect(() => {
    if (isMockMode) return;
    // A single sample can find 3 vehicles. Iterate the buffer, not just its
    // newest item, so React batching cannot silently lose two notifications.
    for (const event of [...plateNotifications].reverse()) {
      if (!gate.current.accept(event)) continue;
      const tentative = event.plateStatus === 'LOW_CONFIDENCE';
      toast.push(tentative ? 'warning' : 'success',
        `Plate read · ${event.plate}${tentative ? ' · verify' : ''}`,
        `${event.cameraName ?? event.cameraId} · ${event.plateConfidence.toFixed(0)}% OCR · ${event.videoFile ? 'Recorded video' : 'Camera sighting'} · Saved to Vehicle Log`, {
          durationMs: 7000,
          action: {
            label: 'View in Vehicle Log',
            onClick: () => navigate(`/events?cameraId=${encodeURIComponent(event.cameraId)}&plate=${encodeURIComponent(event.plate)}`),
          },
        });
    }
  }, [plateNotifications, toast, navigate]);
  return null;
}
