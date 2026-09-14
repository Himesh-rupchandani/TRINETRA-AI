import { useLive } from '@/features/alerts/LiveProvider';

/**
 * Live detection feed. Backed by the mock simulator today and by
 * WebSocket/SSE once the backend is connected — the hook contract is identical.
 */
export function useLiveEvents() {
  const { liveEvents, connection, paused, setPaused, eventsSeen } = useLive();
  return { events: liveEvents, connection, paused, setPaused, eventsSeen };
}
