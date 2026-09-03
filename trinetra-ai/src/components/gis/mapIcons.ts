import L from 'leaflet';
import { cameraStatusHex, severityHex } from '@/lib/utils';
import type { CameraStatus, Severity } from '@/types';

/**
 * Marker factories. Uses Leaflet divIcons (inline SVG) so no external
 * image assets are required and colours follow the app's semantic tokens.
 */

export function cameraIcon(status: CameraStatus, selected = false): L.DivIcon {
  const color = cameraStatusHex[status];
  const size = selected ? 30 : 24;
  return L.divIcon({
    className: 'trinetra-marker',
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
    popupAnchor: [0, -size / 2],
    html: `<div style="width:${size}px;height:${size}px;display:grid;place-items:center;">
      <span style="position:absolute;width:${size}px;height:${size}px;border-radius:50%;background:${color};opacity:${selected ? 0.28 : 0.16};"></span>
      <svg width="${size * 0.62}" height="${size * 0.62}" viewBox="0 0 24 24" fill="none"
           stroke="${color}" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"
           style="position:relative;filter:drop-shadow(0 1px 2px rgba(0,0,0,.6))">
        <path d="M2 7.5 17 4l1.6 6.2L3.6 13.7 2 7.5Z"/><path d="M6 13.2V20h9"/><circle cx="19" cy="17" r="3"/>
      </svg>
      ${selected ? `<span style="position:absolute;width:${size + 10}px;height:${size + 10}px;border-radius:50%;border:2px solid ${color};"></span>` : ''}
    </div>`,
  });
}

export function routeIcon(sequence: number, severity: Severity = 'HIGH', active = false): L.DivIcon {
  const color = severityHex[severity];
  const size = active ? 30 : 25;
  return L.divIcon({
    className: 'trinetra-marker',
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
    popupAnchor: [0, -size / 2],
    html: `<div style="width:${size}px;height:${size}px;border-radius:50%;background:${color};
      border:2px solid ${active ? '#ffffff' : 'rgba(255,255,255,.75)'};display:grid;place-items:center;
      box-shadow:0 2px 6px rgba(0,0,0,.55);font:700 ${size * 0.46}px/1 ui-monospace,monospace;color:#0b0f14;">
      ${sequence}</div>`,
  });
}

export function eventIcon(watchlist = false): L.DivIcon {
  const color = watchlist ? severityHex.CRITICAL : '#38bdf8';
  return L.divIcon({
    className: 'trinetra-marker',
    iconSize: [12, 12],
    iconAnchor: [6, 6],
    popupAnchor: [0, -6],
    html: `<div style="width:12px;height:12px;border-radius:50%;background:${color};
      border:1.5px solid rgba(255,255,255,.8);box-shadow:0 1px 3px rgba(0,0,0,.5)"></div>`,
  });
}
