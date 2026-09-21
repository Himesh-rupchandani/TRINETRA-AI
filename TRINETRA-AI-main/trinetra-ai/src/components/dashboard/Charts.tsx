import { memo, useMemo } from 'react';
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { VehicleEvent } from '@/types';

const AXIS = { fontSize: 10, fill: 'rgb(var(--ink-faint))' };

function tooltipStyle() {
  return {
    background: 'rgb(var(--surface-1))',
    border: '1px solid rgb(var(--line))',
    borderRadius: 4,
    fontSize: 11,
    color: 'rgb(var(--ink))',
    padding: '6px 8px',
  };
}

/** Detections per hour across the retained window. */
export const DetectionTrend = memo(function DetectionTrend({ events }: { events: VehicleEvent[] }) {
  const data = useMemo(() => {
    const buckets = new Map<number, number>();
    for (let h = 0; h < 24; h++) buckets.set(h, 0);
    events.forEach((e) => {
      const h = new Date(e.timestamp).getHours();
      buckets.set(h, (buckets.get(h) ?? 0) + 1);
    });
    return Array.from(buckets, ([hour, count]) => ({
      hour: `${String(hour).padStart(2, '0')}h`,
      count,
    }));
  }, [events]);

  return (
    <ResponsiveContainer width="100%" height="100%">
      <AreaChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -22 }}>
        <defs>
          <linearGradient id="detGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="rgb(var(--brand))" stopOpacity={0.45} />
            <stop offset="100%" stopColor="rgb(var(--brand))" stopOpacity={0.02} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke="rgb(var(--line))" strokeDasharray="2 3" vertical={false} />
        <XAxis dataKey="hour" tick={AXIS} tickLine={false} axisLine={false} interval={3} />
        <YAxis tick={AXIS} tickLine={false} axisLine={false} width={38} allowDecimals={false} />
        <Tooltip contentStyle={tooltipStyle()} cursor={{ stroke: 'rgb(var(--line-strong))' }} />
        <Area
          type="monotone"
          dataKey="count"
          name="Detections"
          stroke="rgb(var(--brand))"
          strokeWidth={1.6}
          fill="url(#detGrad)"
        />
      </AreaChart>
    </ResponsiveContainer>
  );
});

/** Busiest cameras by detection volume. */
export const CameraActivityChart = memo(function CameraActivityChart({
  events,
  limit = 8,
}: {
  events: VehicleEvent[];
  limit?: number;
}) {
  const data = useMemo(() => {
    const counts = new Map<string, number>();
    events.forEach((e) => {
      const key = e.cameraName ?? e.cameraId.toUpperCase();
      counts.set(key, (counts.get(key) ?? 0) + 1);
    });
    return Array.from(counts, ([camera, count]) => ({ camera, count }))
      .sort((a, b) => b.count - a.count)
      .slice(0, limit);
  }, [events, limit]);

  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={data} layout="vertical" margin={{ top: 4, right: 12, bottom: 0, left: 8 }}>
        <CartesianGrid stroke="rgb(var(--line))" strokeDasharray="2 3" horizontal={false} />
        <XAxis type="number" tick={AXIS} tickLine={false} axisLine={false} allowDecimals={false} />
        <YAxis
          type="category"
          dataKey="camera"
          tick={{ ...AXIS, fontFamily: 'monospace' }}
          tickLine={false}
          axisLine={false}
          width={58}
        />
        <Tooltip contentStyle={tooltipStyle()} cursor={{ fill: 'rgb(var(--surface-3))' }} />
        <Bar dataKey="count" name="Detections" fill="rgb(var(--brand))" radius={[0, 2, 2, 0]} barSize={11} />
      </BarChart>
    </ResponsiveContainer>
  );
});
