import { Suspense, lazy, Component, type ReactNode } from 'react';
import type { MapViewProps } from './MapView';
import { LoadingState } from '@/components/common/Panel';

const MapView = lazy(() => import('./MapView').then((m) => ({ default: m.MapView })));

class MapErrorBoundary extends Component<{ children: ReactNode }, { hasError: boolean; error?: Error }> {
  state = { hasError: false, error: undefined as Error | undefined };
  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error };
  }
  componentDidCatch(error: Error, info: any) {
    console.error('[Map] Error boundary caught:', error, info);
  }
  render() {
    if (this.state.hasError) {
      return (
        <div className="grid h-full w-full place-items-center bg-surface-2 p-6 text-center">
          <div className="max-w-sm rounded-xl border border-line bg-surface-1 p-5 shadow-lg">
            <p className="text-sm font-semibold text-ink">Map failed to load</p>
            <p className="mt-2 text-2xs leading-relaxed text-ink-muted">
              {this.state.error?.message || 'An unexpected error occurred while rendering the map.'}
            </p>
            <button
              type="button"
              className="btn-primary btn-xs mt-4"
              onClick={() => this.setState({ hasError: false, error: undefined })}
            >
              Try again
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

/**
 * Leaflet is code-split: the map bundle only loads on screens that need it.
 * Wrapped in error boundary so a single tile/marker crash never blanks the whole page.
 */
export function LazyMap(props: MapViewProps) {
  return (
    <MapErrorBoundary>
      <Suspense
        fallback={
          <div className="h-full w-full bg-surface-2">
            <LoadingState label="Initialising GIS layer" rows={3} />
          </div>
        }
      >
        <MapView {...props} />
      </Suspense>
    </MapErrorBoundary>
  );
}
