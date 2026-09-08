import { useMemo } from 'react';
import type { Alert, Camera, Severity, VehicleEvent } from '@/types';
import type { HourlyVolume } from './derive';

const SEVERITY_RANK: Record<Severity, number> = {
  CRITICAL: 0,
  HIGH: 1,
  MEDIUM: 2,
  LOW: 3,
  INFO: 4,
};

const STATUS_RANK: Record<Camera['status'], number> = { ONLINE: 0, DEGRADED: 1, OFFLINE: 2 };

/** Order the camera wall: online first, then by freshest activity. */
function wallOrder(cameras: Camera[]): Camera[] {
  return [...cameras].sort((a, b) => {
    const r = STATUS_RANK[a.status] - STATUS_RANK[b.status];
    if (r !== 0) return r;
    return (b.lastEventAt ? Date.parse(b.lastEventAt) : 0) - (a.lastEventAt ? Date.parse(a.lastEventAt) : 0);
  });
}

export interface WatchSighting {
  plate: string;
  count: number;
  lastAt: string | null;
  severity: Severity;
}

/**
 * Dashboard aggregation — one memo so the page renders from a single
 * consistent snapshot of alerts + cameras + the live feed.
 */
export function useDashboardData({
  alerts,
  cameras,
  liveEvents,
}: {
  alerts: Alert[];
  cameras: Camera[];
  liveEvents: VehicleEvent[];
}): {
  attention: Alert[];
  cameraWall: Camera[];
  volume24h: HourlyVolume[];
  deptBars: { dept: string; count: number }[];
  watchlistToday: WatchSighting[];
} {
  return useMemo(() => {
    // Attention: open alerts, most severe first, capped for the pane.
    const attention = [...alerts]
      .sort((a, b) => SEVERITY_RANK[a.severity] - SEVERITY_RANK[b.severity])
      .slice(0, 4);

    // Camera wall: network health at a glance, top 6.
    const cameraWall = wallOrder(cameras).slice(0, 6);

    // 24h volume from the live feed when it has data; otherwise an
    // honest flat series (no invented history).
    const now = Date.now();
    const volume24h: HourlyVolume[] = Array.from({ length: 24 }, (_, i) => ({
      hour: (new Date(now).getHours() - 23 + i + 24) % 24,
      count: 0,
    }));
    for (const e of liveEvents) {
      const t = Date.parse(e.timestamp);
      const hoursAgo = (now - t) / 3_600_000;
      if (hoursAgo >= 0 && hoursAgo < 24) {
        const slot = 23 - Math.floor(hoursAgo);
        if (slot >= 0 && slot < 24) volume24h[slot].count += 1;
      }
    }

    // Department bars from the registry itself.
    const byDept = new Map<string, number>();
    for (const c of cameras) {
      const d = c.department ?? 'Unassigned';
      byDept.set(d, (byDept.get(d) ?? 0) + 1);
    }
    const deptBars = [...byDept.entries()]
      .map(([dept, count]) => ({ dept, count }))
      .sort((a, b) => b.count - a.count)
      .slice(0, 6);

    // Wanted plates seen recently (open alerts + live wanted matches).
    const wanted = new Map<string, WatchSighting>();
    const bump = (plate: string, at: string, severity: Severity) => {
      const cur = wanted.get(plate);
      if (!cur) wanted.set(plate, { plate, count: 1, lastAt: at, severity });
      else {
        cur.count += 1;
        if (!cur.lastAt || Date.parse(at) > Date.parse(cur.lastAt)) cur.lastAt = at;
        if (SEVERITY_RANK[severity] < SEVERITY_RANK[cur.severity]) cur.severity = severity;
      }
    };
    for (const a of alerts) bump(a.plate, a.createdAt, a.severity);
    for (const e of liveEvents) if (e.watchlistMatch) bump(e.plate, e.timestamp, 'CRITICAL');
    const watchlistToday = [...wanted.values()]
      .sort(
        (a, b) =>
          SEVERITY_RANK[a.severity] - SEVERITY_RANK[b.severity] ||
          Date.parse(b.lastAt ?? '0') - Date.parse(a.lastAt ?? '0'),
      )
      .slice(0, 6);

    return { attention, cameraWall, volume24h, deptBars, watchlistToday };
  }, [alerts, cameras, liveEvents]);
}
