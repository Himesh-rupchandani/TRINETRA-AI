import { useEffect } from 'react';
import { GeoJSON, useMap } from 'react-leaflet';
import { gujaratDistricts } from '@/lib/geo/gujaratDistricts';
import { gujaratOutline } from '@/lib/geo/gujaratOutline';
import { gujaratMask } from '@/lib/geo/gujaratMask';

/**
 * Gujarat thematic overlay — the control-room “state map” look:
 *  - state outline drawn on every basemap (Mapbox / OSM / satellite alike),
 *  - an optional dark mask outside the state that dims the rest of the world,
 *  - optional district polygons with hover tooltips (Census 2011 boundaries),
 *    shaded by camera density and clickable to focus a district.
 *
 * Geometry is bundled (src/lib/geo/*.ts, generated from the data.gov.in
 * census shapefile by scripts/make_gujarat_geojson.py) — no tile service or
 * network round-trip involved, so it also works offline in the demo venue.
 */

const MASK_PANE = 'gujarat-mask';

/** Custom pane below the vector-overlay pane: the mask dims tiles, never the
 *  routes, markers, popups or the playback dot drawn above it. */
function EnsureMaskPane() {
  const map = useMap();
  useEffect(() => {
    if (!map.getPane(MASK_PANE)) {
      const p = map.createPane(MASK_PANE);
      p.style.zIndex = '350';
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
  /** When present (with `districts`), polygons shade by camera density. */
  counts?: Record<string, DistrictCount>;
  selected?: string | null;
  /** Fired on district click (same district re-clicked => null to clear). */
  onSelect?: (name: string | null) => void;
}

/** Quartile ramp of fill opacity keyed to max district camera count. */
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
  const densityKey = counts ? Object.values(counts).reduce((a, c) => a + c.cameras * 31 + c.events, 0) : 0;
  return (
    <>
      <EnsureMaskPane />
      {mask && (
        <GeoJSON
          pane={MASK_PANE}
          interactive={false}
          data={gujaratMask}
          style={{ stroke: false, fillColor: '#0b1220', fillOpacity: 0.55, fillRule: 'evenodd' }}
        />
      )}
      {boundary && (
        <>
          {/* dark casing for contrast on any basemap, then the brand line */}
          <GeoJSON
            pane={MASK_PANE}
            interactive={false}
            data={gujaratOutline}
            style={{ color: '#000000', opacity: 0.35, weight: 6, fill: false }}
          />
          <GeoJSON
            interactive={false}
            data={gujaratOutline}
            style={{ color: '#f97316', opacity: 0.95, weight: 2.5, fill: false }}
          />
        </>
      )}
      {districts && (
        // react-leaflet's GeoJSON styles once at mount — remount on data change
        // so density + selection stay in sync with the registry/events.
        <GeoJSON
          key={`dist-${densityKey}-${selected ?? ''}`}
          data={gujaratDistricts}
          style={(feature) => {
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
            };
          }}
          onEachFeature={(feature, layer) => {
            const name = String(feature?.properties?.name ?? 'District');
            const c = counts?.[name];
            const tip = c
              ? `${name} district · ${c.cameras} camera${c.cameras === 1 ? '' : 's'} · ${c.events} sighting${c.events === 1 ? '' : 's'}`
              : `${name} district · no cameras`;
            layer.bindTooltip(tip, { sticky: true, direction: 'top' });
            layer.on({
              mouseover: (e) => e.target.setStyle({ weight: 2, opacity: 1, fillOpacity: 0.28 }),
              mouseout: (e) => {
                const isSel = selected === name;
                e.target.setStyle(
                  isSel
                    ? { weight: 2.4, opacity: 1, fillOpacity: 0.22 }
                    : { weight: 1, opacity: 0.7, fillOpacity: densityFill(c?.cameras ?? 0, counts ? Math.max(1, ...Object.values(counts).map((x) => x.cameras)) : 1) },
                );
              },
            });
            if (onSelect) {
              layer.on('click', () => onSelect(selected === name ? null : name));
            }
          }}
        />
      )}
    </>
  );
}
