import type { Alert } from '@/types';
import { journeyEvents, mockEvents } from './events';
import { watchlistByPlate } from './watchlist';
import { cameraById } from './cameras';

/**
 * DEMO / SYNTHETIC alerts. The first alert is the primary demo trace
 * (GJ01AB1234 · STOLEN VEHICLE) raised at its CAM04 first sighting.
 */
function fromEventId(id: string, overrides: Partial<Alert>, index: number): Alert {
  const ev = mockEvents.find((e) => e.id === id) ?? journeyEvents[0];
  const wl = watchlistByPlate(ev.plate);
  const cam = cameraById(ev.cameraId);
  return {
    id: `alr-${String(index).padStart(3, '0')}`,
    eventId: ev.id,
    plate: ev.plate,
    cameraId: ev.cameraId,
    cameraName: cam?.name ?? ev.cameraId.toUpperCase(),
    location: ev.location ?? cam?.location ?? '—',
    latitude: ev.latitude,
    longitude: ev.longitude,
    severity: wl?.severity ?? ev.severity ?? 'MEDIUM',
    status: 'NEW',
    category: wl?.category ?? 'WATCHLIST MATCH',
    createdAt: ev.timestamp,
    confidence: ev.plateConfidence,
    evidenceRef: ev.evidenceRef,
    ...overrides,
  };
}

const watchlistHits = mockEvents.filter(
  (e) => e.eventType === 'WATCHLIST_MATCH' && !e.id.startsWith('evt-j'),
);

export const mockAlerts: Alert[] = [
  // Primary demo alert — CAM04 first sighting of GJ01AB1234.
  fromEventId('evt-j1-1', { status: 'NEW' }, 1),
  // Latest hop of the same vehicle — shows escalation across cameras.
  fromEventId('evt-j1-4', { status: 'NEW' }, 2),
  // Critical wanted-suspect vehicle.
  fromEventId('evt-j2-5', { status: 'NEW' }, 3),
  // Blacklisted goods carrier.
  fromEventId('evt-j3-3', { status: 'ACKNOWLEDGED', acknowledgedBy: 'Ctrl. A. Desai' }, 4),
  // Ambient historical hits (acknowledged / resolved) for Alert History.
  ...watchlistHits.slice(0, 4).map((e, i) =>
    fromEventId(
      e.id,
      i % 2 === 0
        ? {
            status: 'ACKNOWLEDGED',
            acknowledgedBy: 'Ctrl. P. Solanki',
            acknowledgedAt: new Date(new Date(e.timestamp).getTime() + 120_000).toISOString(),
          }
        : {
            status: 'RESOLVED',
            acknowledgedBy: 'Ctrl. P. Solanki',
            acknowledgedAt: new Date(new Date(e.timestamp).getTime() + 90_000).toISOString(),
            resolvedAt: new Date(new Date(e.timestamp).getTime() + 15 * 60_000).toISOString(),
            note: 'Unit dispatched — vehicle intercepted and verified.',
          },
      5 + i,
    ),
  ),
].sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime());
