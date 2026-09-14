import { useEffect, useMemo } from 'react';
import { GeoJSON, useMap } from 'react-leaflet';
import { gujaratDistricts } from '@/lib/geo/gujaratDistricts';
import { gujaratOutline } from '@/lib/geo/gujaratOutline';
import { gujaratMask } from '@/lib/geo/gujaratMask';

const MASK_PANE = 'gujarat-mask';

function EnsureMaskPane() {
  const map = useMap();
  useEffect(() => {
    try {
      if (!map.getPane(MASK_PANE)) {
        const p = map.createPane(MASK_PANE);
        p.style.zIndex = '350';
      }
    } catch {
      // ignore pane creation errors
    }
  }, [map]);
  return null;
}

export interface DistrictCount {
  cameras: number;
  events: number;
}

export interface GujaratFocusProps {
  boundary?: boolean;
  mask?: boolean;
  districts?: boolean;
  counts?: Record<string, DistrictCount>;
  selected?: string | null;
  onSelect?: (name: string | null) => void;
}

function densityFill(n: number, max: number): number {
  if (n <= 0 || max <= 0) return 0.04;
  const t = n / max;
  return t >= 0.75 ? 0.5 : t >= 0.5 ? 0.34 : t >= 0.25 ? 0.2 : 0.1;
}

export function GujaratFocus({
  boundary = true,
  mask = false,
  districts = false,
  counts,
  selected = null,
  onSelect,
}: GujaratFocusProps) {
  // Stable key — avoid remounting on every render, only when counts or selection change significantly
  const densityKey = useMemo(() => {
    if (!counts) return 0;
    try {
      return Object.values(counts).reduce((a, c) => a + c.cameras * 31 + c.events, 0);
    } catch {
      return 0;
    }
  }, [counts]);

  // Validate geojson exists and is not empty
  const hasOutline = useMemo(() => {
    try {
      return Boolean(gujaratOutline && (gujaratOutline as any).type);
    } catch {
      return false;
    }
  }, []);
  const hasMask = useMemo(() => {
    try {
      return Boolean(gujaratMask && (gujaratMask as any).type);
    } catch {
      return false;
    }
  }, []);
  const hasDistricts = useMemo(() => {
    try {
      return Boolean(gujaratDistricts && (gujaratDistricts as any).features?.length);
    } catch {
      return false;
    }
  }, []);

  return (
    <>
      <EnsureMaskPane />
      {mask && hasMask && (
        <GeoJSON
          pane={MASK_PANE}
          interactive={false}
          data={gujaratMask as any}
          style={{ stroke: false, fillColor: '#0b1220', fillOpacity: 0.55, fillRule: 'evenodd' as any }}
        />
      )}
      {boundary && hasOutline && (
        <>
          <GeoJSON
            pane={MASK_PANE}
            interactive={false}
            data={gujaratOutline as any}
            style={{ color: '#000000', opacity: 0.35, weight: 6, fill: false } as any}
          />
          <GeoJSON
            interactive={false}
            data={gujaratOutline as any}
            style={{ color: '#f97316', opacity: 0.95, weight: 2.5, fill: false } as any}
          />
        </>
      )}
      {districts && hasDistricts && (
        <GeoJSON
          key={`dist-${densityKey}-${selected ?? ''}`}
          data={gujaratDistricts as any}
          style={(feature) => {
            try {
              const name = String(feature?.properties?.name ?? '');
              const n = counts?.[name]?.cameras ?? 0;
              const max = counts ? Math.max(1, ...Object.values(counts).map((c) => c.cameras)) : 1;
              const isSel = selected === name;
              return {
                color: isSel ? '#f97316' : '#fb923c',
                weight: isSel ? 2.4 : 1,
                opacity: isSel ? 1 : 0.7,
                fillColor: '#f97316',
                fillOpacity: isSel ? 0.22 : densityFill(n, max),
                dashArray: isSel ? undefined : '4 4',
              } as any;
            } catch {
              return { color: '#fb923c', weight: 1, opacity: 0.5, fillOpacity: 0.05 } as any;
            }
          }}
          onEachFeature={(feature, layer) => {
            try {
              const name = String(feature?.properties?.name ?? 'District');
              const c = counts?.[name];
              const tip = c
                ? `${name} district · ${c.cameras} camera${c.cameras === 1 ? '' : 's'} · ${c.events} sighting${c.events === 1 ? '' : 's'}`
                : `${name} district · no cameras`;
              (layer as any).bindTooltip(tip, { sticky: true, direction: 'top' });
              (layer as any).on({
                mouseover: (e: any) => {
                  try {
                    e.target.setStyle({ weight: 2, opacity: 1, fillOpacity: 0.28 });
                  } catch {
                    // ignore
                  }
                },
                mouseout: (e: any) => {
                  try {
                    const isSel = selected === name;
                    const maxCameras = counts ? Math.max(1, ...Object.values(counts).map((x) => x.cameras)) : 1;
                    e.target.setStyle(
                      isSel
                        ? { weight: 2.4, opacity: 1, fillOpacity: 0.22 }
                        : {
                            weight: 1,
                            opacity: 0.7,
                            fillOpacity: densityFill(c?.cameras ?? 0, maxCameras),
                          },
                    );
                  } catch {
                    // ignore
                  }
                },
              });
              if (onSelect) {
                (layer as any).on('click', () => {
                  try {
                    onSelect(selected === name ? null : name);
                  } catch {
                    // ignore
                  }
                });
              }
            } catch {
              // ignore feature errors
            }
          }}
        />
      )}
    </>
  );
}
