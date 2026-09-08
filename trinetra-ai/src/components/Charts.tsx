import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { HourlyVolume } from '@/features/dashboard/derive';

/**
 * The dashboard's single trend chart — 24-hour vehicle volume.
 * One teal series, warm tooltip, no decoration.
 */
export function VolumeChart({ data }: { data: HourlyVolume[] }) {
  return (
    <div className="h-52 w-full" role="img" aria-label="Vehicles recorded over the last 24 hours, by hour">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 10, left: -14, bottom: 0 }}>
          <CartesianGrid stroke="rgb(228 228 224)" strokeDasharray="3 3" vertical={false} />
          <XAxis
            dataKey="hour"
            tickLine={false}
            axisLine={false}
            tick={{ fontSize: 10.5, fill: 'rgb(138 138 131)' }}
            tickFormatter={(h: number) => (h % 3 === 0 ? `${String(h).padStart(2, '0')}:00` : '')}
            interval={0}
          />
          <YAxis
            tickLine={false}
            axisLine={false}
            tick={{ fontSize: 10.5, fill: 'rgb(138 138 131)' }}
            width={44}
            allowDecimals={false}
          />
          <Tooltip
            cursor={{ stroke: 'rgb(207 207 201)' }}
            contentStyle={{
              background: '#ffffff',
              border: '1px solid rgb(228 228 224)',
              borderRadius: 8,
              boxShadow: '0 6px 16px rgb(28 28 26 / 0.12)',
              fontSize: 12,
              padding: '8px 12px',
            }}
            labelFormatter={(h) => `${String(h).padStart(2, '0')}:00`}
            formatter={(v) => [`${v}`, 'Vehicles']}
          />
          <Line
            type="monotone"
            dataKey="count"
            stroke="rgb(15 118 110)"
            strokeWidth={1.8}
            dot={false}
            activeDot={{ r: 3.5, fill: 'rgb(15 118 110)' }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
