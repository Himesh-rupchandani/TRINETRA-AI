import { Camera as CameraIcon, Cctv, CircleDot, Radio, Wifi } from 'lucide-react';
import { cameraStatusHex } from '@/lib/utils';

export function MapLegend({ showRoute = false }: { showRoute?: boolean }) {
  const items = [
    { color: cameraStatusHex.ONLINE, label: 'Camera working', icon: Cctv },
    { color: cameraStatusHex.DEGRADED, label: 'Poor quality', icon: Wifi },
    { color: cameraStatusHex.OFFLINE, label: 'Not working', icon: Radio },
    { color: '#38bdf8', label: 'Vehicle was seen here', icon: CircleDot },
    ...(showRoute ? [{ color: '#f97316', label: 'Route, in order', icon: CameraIcon }] : []),
  ];

  return (
    <ul className="pointer-events-none absolute bottom-3 left-3 z-[400] space-y-1.5 rounded-xl border border-line bg-surface-1/92 px-3 py-2 backdrop-blur">
      {items.map((i) => (
        <li key={i.label} className="flex items-center gap-1.5 text-[10px] text-ink-muted">
          <span className="h-2 w-2 rounded-full" style={{ background: i.color }} aria-hidden />
          {i.label}
        </li>
      ))}
    </ul>
  );
}
