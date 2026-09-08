import L from 'leaflet';
import { cameraStatusHex, severityHex } from '@/lib/utils';
import type { CameraStatus, Severity } from '@/types';

/**
 * Marker factories. Uses Leaflet divIcons (inline SVG) so no external
 * image assets are required and colours follow the app's semantic tokens.
 * Dark-theme treatment: cameras are small cyan rings, watchlist hits pulse
 * red, route sightings are numbered navy discs with cyan rims.
 */

/** Camera position: a small cyan ring (status-tinted). */
export function cameraIcon(status: CameraStatus, selected = false): L.DivIcon {
  const color = status === 'ONLINE' ? '#22D3EE' : cameraStatusHex[status];
  const size = selected ? 20 : 14;
  const stroke = selected ? 2.5 : 2;
  return L.divIcon({
    className: 'trinetra-marker',
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
    popupAnchor: [0, -size / 2],
    html: `<div style="position:relative;width:${size}px;height:${size}px;">
      <div style="width:${size}px;height:${size}px;border-radius:50%;background:${color}22;
        border:${stroke}px solid ${color}"></div>
      ${selected ? `<div style="position:absolute;inset:-6px;border-radius:50%;border:2px solid ${color};opacity:.8"></div>` : ''}
    </div>`,
  });
}

/** Numbered route sighting: navy disc, cyan rim, mono numeral. */
export function routeIcon(
  sequence: number,
  severity: Severity = 'HIGH',
  active = false,
  color?: string,
): L.DivIcon {
  const fill = color ?? severityHex[severity];
  const size = active ? 30 : 24;
  return L.divIcon({
    className: 'trinetra-marker',
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
    popupAnchor: [0, -size / 2],
    html: `<div style="width:${size}px;height:${size}px;border-radius:50%;background:#0D1524;
      border:2px solid ${active ? '#F5A524' : fill};display:grid;place-items:center;
      box-shadow:0 2px 8px rgba(0,0,0,.6);font:700 ${Math.round(size * 0.46)}px/1 'JetBrains Mono',ui-monospace,monospace;
      color:${active ? '#F5A524' : '#E8EEF9'}">
      ${sequence}</div>`,
  });
}

/** Detection point; watchlist hits get the red pulse ring. */
export function eventIcon(watchlist = false): L.DivIcon {
  if (watchlist) {
    return L.divIcon({
      className: 'trinetra-marker trinetra-marker-pulse',
      iconSize: [12, 12],
      iconAnchor: [6, 6],
      popupAnchor: [0, -6],
      html: `<div style="width:12px;height:12px;border-radius:50%;background:${severityHex.CRITICAL};
        border:1.5px solid rgba(232,238,249,.85);box-shadow:0 1px 4px rgba(0,0,0,.6)"></div>`,
    });
  }
  return L.divIcon({
    className: 'trinetra-marker',
    iconSize: [10, 10],
    iconAnchor: [5, 5],
    popupAnchor: [0, -5],
    html: `<div style="width:10px;height:10px;border-radius:50%;background:#38BDF8;
      border:1.5px solid rgba(232,238,249,.8);box-shadow:0 1px 4px rgba(0,0,0,.6)"></div>`,
  });
}
