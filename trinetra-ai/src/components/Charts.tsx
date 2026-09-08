import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { HourlyVolume } from '@/features/dashboard/derive';

/** 24-hour vehicle volume — single-series ink bars, no decoration. */
export function VolumeChart({ data }: { data: HourlyVolume[] }) {
  return (
    <div className="h-56 w-full" role="img" aria-label="Vehicles recorded over the last 24 hours, by hour">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 10, left: -14, bottom: 0 }}>
          <CartesianGrid stroke="rgb(228 231 234)" strokeDasharray="3 3" vertical={false} />
          <XAxis
            dataKey="hour"
            tickLine={false}
            axisLine={false}
            tick={{ fontSize: 10.5, fill: 'rgb(138 146 155)' }}
            tickFormatter={(h: number) => (h % 3 === 0 ? `${String(h).padStart(2, '0')}:00` : '')}
            interval={0}
          />
          <YAxis
            tickLine={false}
            axisLine={false}
            tick={{ fontSize: 10.5, fill: 'rgb(138 146 155)' }}
            width={44}
          />
          <Tooltip
            cursor={{ stroke: 'rgb(208 213 218)' }}
            contentStyle={{
              background: '#ffffff',
              border: '1px solid rgb(228 231 234)',
              borderRadius: 10,
              boxShadow: '0 6px 16px rgb(16 24 40 / 0.10)',
              fontSize: 12,
              padding: '8px 12px',
            }}
            labelFormatter={(h) => `${String(h).padStart(2, '0')}:00`}
            formatter={(v) => [`${v}`, 'Vehicles']}
          />
          <Line
            type="monotone"
            dataKey="count"
            stroke="rgb(21 128 61)"
            strokeWidth={1.8}
            dot={false}
            activeDot={{ r: 3.5, fill: 'rgb(21 128 61)' }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

/** Cameras by department — small horizontal bars for the attention panel. */
export function DeptChart({ data }: { data: { dept: string; count: number }[] }) {
  return (
    <div className="h-44 w-full" role="img" aria-label="Cameras per department">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} layout="vertical" margin={{ top: 4, right: 18, left: 8, bottom: 0 }}>
          <XAxis type="number" hide domain={[0, 'dataMax']} />
          <YAxis
            type="category"
            dataKey="dept"
            width={132}
            tickLine={false}
            axisLine={false}
            tick={{ fontSize: 11.5, fill: 'rgb(90 98 108)' }}
          />
          <Tooltip
            cursor={{ fill: 'rgb(244 246 247)' }}
            contentStyle={{
              background: '#ffffff',
              border: '1px solid rgb(228 231 234)',
              borderRadius: 10,
              boxShadow: '0 6px 16px rgb(16 24 40 / 0.10)',
              fontSize: 12,
              padding: '8px 12px',
            }}
            formatter={(v) => [`${v}`, 'Cameras']}
          />
          <Bar dataKey="count" fill="rgb(21 128 61)" radius={[0, 4, 4, 0]} barSize={13} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
