import { Camera as CameraIcon, Cctv, CircleDot, Radio, Wifi } from 'lucide-react';
import { cameraStatusHex } from '@/lib/utils';

/** Map legend — colours match the dark-tuned marker set in mapIcons.ts. */
export function MapLegend({ showRoute = false }: { showRoute?: boolean }) {
  const items = [
    { color: '#22D3EE', label: 'Camera (live)', icon: Cctv },
    { color: cameraStatusHex.DEGRADED, label: 'Camera — poor quality', icon: Wifi },
    { color: cameraStatusHex.OFFLINE, label: 'Camera — not working', icon: Radio },
    { color: '#38BDF8', label: 'Vehicle sighting', icon: CircleDot },
    ...(showRoute
      ? [
          { color: '#22D3EE', label: 'Route start (oldest)', icon: CameraIcon },
          { color: '#F5A524', label: 'Route latest', icon: CameraIcon },
          { color: '#FF3B5C', label: 'Watchlist hit', icon: CameraIcon },
        ]
      : []),
  ];

  return (
    <ul className="pointer-events-none absolute bottom-3 left-3 z-[400] space-y-1.5 rounded-lg border border-line bg-surface-1/90 px-3 py-2 backdrop-blur">
      {items.map((i) => (
        <li key={i.label} className="flex items-center gap-1.5 text-[10px] text-ink-muted">
          <span className="h-2 w-2 rounded-full" style={{ background: i.color }} aria-hidden />
          {i.label}
        </li>
      ))}
    </ul>
  );
}
