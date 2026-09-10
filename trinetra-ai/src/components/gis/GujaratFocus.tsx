import { useEffect } from 'react';
import { GeoJSON, useMap } from 'react-leaflet';
import { gujaratDistricts } from '@/lib/geo/gujaratDistricts';
import { gujaratOutline } from '@/lib/geo/gujaratOutline';
import { gujaratMask } from '@/lib/geo/gujaratMask';

/**
 * Gujarat thematic overlay — the control-room “state map” look:
 *  - state outline drawn on every basemap (Mapbox / OSM / satellite alike),
 *  - an optional dark mask outside the state that dims the rest of the world,
 *  - optional district polygons with hover tooltips (Census 2011 boundaries).
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

export interface GujaratFocusProps {
  boundary?: boolean;
  mask?: boolean;
  districts?: boolean;
}

export function GujaratFocus({ boundary = true, mask = false, districts = false }: GujaratFocusProps) {
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
        <GeoJSON
          data={gujaratDistricts}
          style={{
            color: '#fb923c',
            weight: 1,
            opacity: 0.7,
            fillColor: '#f97316',
            fillOpacity: 0.05,
            dashArray: '4 4',
          }}
          onEachFeature={(feature, layer) => {
            const name = String(feature?.properties?.name ?? 'District');
            layer.bindTooltip(`${name} district`, { sticky: true, direction: 'top' });
            layer.on({
              mouseover: (e) => e.target.setStyle({ weight: 2, opacity: 1, fillOpacity: 0.14 }),
              mouseout: (e) => e.target.setStyle({ weight: 1, opacity: 0.7, fillOpacity: 0.05 }),
            });
          }}
        />
      )}
    </>
  );
}
