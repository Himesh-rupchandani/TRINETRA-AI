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
        border:2px solid #ffffff;box-shadow:0 1px 5px rgba(0,0,0,.45)"></div>
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
      border:2px solid ${active ? '#ffffff' : 'rgba(255,255,255,.75)'};display:grid;place-items:center;
      box-shadow:0 2px 6px rgba(0,0,0,.55);font:700 ${size * 0.46}px/1 ui-monospace,monospace;color:#0b0f14;">
      ${sequence}</div>`,
  });
}

export function playbackIcon(): L.DivIcon {
  return L.divIcon({
    className: 'trinetra-marker',
    iconSize: [20, 20],
    iconAnchor: [10, 10],
    html: '<div class="trinetra-playback-dot"></div>',
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

/**
 * District clustering bubble (state-level overview): camera count in a
 * translucent brand disc, tiny status pip, event count underneath.
 */
export function districtBubbleIcon(
  cameras: number,
  offline: number,
  events: number,
  selected = false,
): L.DivIcon {
  const size = Math.max(34, Math.min(52, 28 + cameras * 2.5));
  const pip = offline > 0 ? '#f59e0b' : cameras > 0 ? '#22c55e' : '#64748b';
  return L.divIcon({
    className: 'trinetra-marker',
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
    popupAnchor: [0, -size / 2],
    html: `<div style="position:relative;width:${size}px;height:${size}px;cursor:pointer;">
      <div style="width:100%;height:100%;border-radius:50%;background:rgba(249,115,22,.20);
        border:2px solid ${selected ? '#f97316' : 'rgba(249,115,22,.85)'};display:grid;place-items:center;
        box-shadow:0 2px 10px rgba(0,0,0,.45);backdrop-filter:blur(1px);">
        <span style="font:700 ${Math.round(size * 0.42)}px/1 ui-sans-serif,system-ui;color:#ea580c;
          text-shadow:0 0 6px rgba(255,255,255,.9)">${cameras}</span>
      </div>
      <span style="position:absolute;right:-2px;top:-2px;width:9px;height:9px;border-radius:50%;
        background:${pip};border:1.5px solid #fff;box-shadow:0 1px 3px rgba(0,0,0,.5)"></span>
      ${
        events > 0
          ? `<span style="position:absolute;left:50%;bottom:-13px;transform:translateX(-50%);white-space:nowrap;
              font:600 9px/1 ui-monospace,monospace;color:#0284c7;background:rgba(255,255,255,.85);
              border:1px solid rgba(2,132,199,.35);border-radius:7px;padding:1px 5px;
              box-shadow:0 1px 3px rgba(0,0,0,.3)">${events} seen</span>`
          : ''
      }
    </div>`,
  });
}
