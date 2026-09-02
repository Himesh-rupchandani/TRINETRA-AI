import { Suspense, lazy } from 'react';
import type { MapViewProps } from './MapView';
import { LoadingState } from '@/components/common/Panel';

const MapView = lazy(() => import('./MapView').then((m) => ({ default: m.MapView })));

/**
 * Leaflet is code-split: the map bundle only loads on screens that need it.
 */
export function LazyMap(props: MapViewProps) {
  return (
    <Suspense
      fallback={
        <div className="h-full w-full bg-surface-2">
          <LoadingState label="Initialising GIS layer" rows={3} />
        </div>
      }
    >
      <MapView {...props} />
    </Suspense>
  );
}
