import L from 'leaflet';
import { cameraStatusHex, severityHex } from '@/lib/utils';
import type { CameraStatus, Severity } from '@/types';

/**
 * Marker factories. Uses Leaflet divIcons (inline SVG) so no external
 * image assets are required and colours follow the app's semantic tokens.
 */

export function cameraIcon(status: CameraStatus, selected = false): L.DivIcon {
  const color = cameraStatusHex[status];
  const size = selected ? 18 : 14;
  return L.divIcon({
    className: 'trinetra-marker',
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
    popupAnchor: [0, -size / 2],
    html: `<div style="position:relative;width:${size}px;height:${size}px;">
      <div style="width:${size}px;height:${size}px;border-radius:50%;background:${color};
        border:2px solid rgb(255 255 255 / 0.85);box-shadow:0 1px 5px rgba(0,0,0,.45)"></div>
      ${selected ? `<div style="position:absolute;inset:-6px;border-radius:50%;border:2px solid ${color}"></div>` : ''}
    </div>`,
  });
}

export function routeIcon(
  sequence: number,
  severity: Severity = 'HIGH',
  active = false,
  color?: string,
): L.DivIcon {
  const fill = color ?? severityHex[severity];
  const size = active ? 30 : 25;
  return L.divIcon({
    className: 'trinetra-marker',
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
    popupAnchor: [0, -size / 2],
    html: `<div style="width:${size}px;height:${size}px;border-radius:50%;background:${fill};
      border:2px solid ${active ? '#ffffff' : 'rgba(255,255,255,.7)'};display:grid;place-items:center;
      box-shadow:0 2px 6px rgba(0,0,0,.55);font:700 ${size * 0.46}px/1 ui-monospace,monospace;color:#0b0f14;">
      ${sequence}</div>`,
  });
}

export function eventIcon(watchlist = false): L.DivIcon {
  const color = watchlist ? severityHex.CRITICAL : '#46ccb8';
  return L.divIcon({
    className: 'trinetra-marker',
    iconSize: [12, 12],
    iconAnchor: [6, 6],
    popupAnchor: [0, -6],
    html: `<div style="width:12px;height:12px;border-radius:50%;background:${color};
      border:1.5px solid rgba(255,255,255,.8);box-shadow:0 1px 3px rgba(0,0,0,.5)"></div>`,
  });
}
