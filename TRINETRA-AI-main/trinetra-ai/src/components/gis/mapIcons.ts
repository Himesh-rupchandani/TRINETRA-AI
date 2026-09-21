import L from 'leaflet';
import { cameraStatusHex, severityHex } from '@/lib/utils';
import type { CameraStatus, Severity } from '@/types';

/**
 * Marker factories. Uses Leaflet divIcons (inline SVG) so no external
 * image assets are required and colours follow the app's semantic tokens.
 * All factories are wrapped in try/catch so a single bad icon never crashes the map.
 */

export function cameraIcon(status: CameraStatus, selected = false): L.DivIcon {
  const color = (cameraStatusHex as any)[status] || cameraStatusHex.OFFLINE || '#dc2626';
  const size = selected ? 18 : 14;
  try {
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
  } catch {
    return L.divIcon({
      className: 'trinetra-marker',
      iconSize: [12, 12],
      iconAnchor: [6, 6],
      html: `<div style="width:12px;height:12px;border-radius:50%;background:${color};border:2px solid #fff"></div>`,
    });
  }
}

export function routeIcon(
  sequence: number,
  severity: Severity = 'HIGH',
  active = false,
  color?: string,
): L.DivIcon {
  const fill = color ?? (severityHex as any)[severity] ?? '#2563eb';
  const size = active ? 30 : 25;
  try {
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
  } catch {
    return L.divIcon({
      className: 'trinetra-marker',
      iconSize: [20, 20],
      iconAnchor: [10, 10],
      html: `<div style="width:20px;height:20px;border-radius:50%;background:${fill};display:grid;place-items:center;color:#000;font-weight:700">${sequence}</div>`,
    });
  }
}

export function playbackIcon(): L.DivIcon {
  try {
    return L.divIcon({
      className: 'trinetra-marker',
      iconSize: [20, 20],
      iconAnchor: [10, 10],
      html: '<div class="trinetra-playback-dot"></div>',
    });
  } catch {
    return L.divIcon({
      className: 'trinetra-marker',
      iconSize: [12, 12],
      iconAnchor: [6, 6],
      html: '<div style="width:12px;height:12px;border-radius:50%;background:#2563eb;border:2px solid #fff"></div>',
    });
  }
}

export function eventIcon(watchlist = false): L.DivIcon {
  const color = watchlist ? severityHex.CRITICAL : '#38bdf8';
  try {
    return L.divIcon({
      className: 'trinetra-marker',
      iconSize: [12, 12],
      iconAnchor: [6, 6],
      popupAnchor: [0, -6],
      html: `<div style="width:12px;height:12px;border-radius:50%;background:${color};
      border:1.5px solid rgba(255,255,255,.8);box-shadow:0 1px 3px rgba(0,0,0,.5)"></div>`,
    });
  } catch {
    return L.divIcon({
      className: 'trinetra-marker',
      iconSize: [10, 10],
      iconAnchor: [5, 5],
      html: `<div style="width:10px;height:10px;border-radius:50%;background:${color}"></div>`,
    });
  }
}

export function alertEventIcon(): L.DivIcon {
  try {
    return L.divIcon({
      className: 'trinetra-alert-marker',
      iconSize: [28, 28],
      iconAnchor: [14, 14],
      popupAnchor: [0, -14],
      html: `<div style="position:relative;width:28px;height:28px;display:flex;align-items:center;justify-content:center;">
        <span style="position:absolute;width:100%;height:100%;border-radius:50%;background:rgba(239,68,68,0.45);animation:ping 1.5s cubic-bezier(0,0,0.2,1) infinite;"></span>
        <span style="position:absolute;width:22px;height:22px;border-radius:50%;background:rgba(239,68,68,0.25);"></span>
        <div style="position:relative;width:14px;height:14px;border-radius:50%;background:#dc2626;border:2.5px solid #ffffff;box-shadow:0 0 10px rgba(220,38,38,0.9);"></div>
      </div>`,
    });
  } catch {
    return L.divIcon({
      className: 'trinetra-marker',
      iconSize: [16, 16],
      iconAnchor: [8, 8],
      html: `<div style="width:16px;height:16px;border-radius:50%;background:#dc2626;border:2px solid #fff"></div>`,
    });
  }
}

export function districtBubbleIcon(
  cameras: number,
  offline: number,
  events: number,
  selected = false,
): L.DivIcon {
  const size = Math.max(34, Math.min(52, 28 + cameras * 2.5));
  const pip = offline > 0 ? '#f59e0b' : cameras > 0 ? '#22c55e' : '#64748b';
  try {
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
  } catch {
    return L.divIcon({
      className: 'trinetra-marker',
      iconSize: [34, 34],
      iconAnchor: [17, 17],
      html: `<div style="width:34px;height:34px;border-radius:50%;background:rgba(249,115,22,.3);border:2px solid #f97316;display:grid;place-items:center;color:#ea580c;font-weight:700">${cameras}</div>`,
    });
  }
}
