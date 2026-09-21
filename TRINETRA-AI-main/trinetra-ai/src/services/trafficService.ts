import { get, post, put } from './api';

export interface TrafficConfig {
  mode: 'off' | 'line' | 'zone';
  axis: 'horizontal' | 'vertical';
  direction: 'both' | 'positive' | 'negative';
  position: number;
  span_start: number;
  span_end: number;
  left: number;
  top: number;
  right: number;
  bottom: number;
}
export interface TrafficSettings { camera_id: string; config: TrafficConfig; revision: string }
export interface TrafficSnapshot {
  session_id: string;
  started_at: string;
  reset_reason: string;
  config: TrafficConfig;
  config_revision: string;
  observed_tracks: number;
  visible_vehicles: number;
  crossings: number;
  forward: number;
  reverse: number;
  by_class: Record<string, number>;
  crossings_by_class: Record<string, number>;
  samples: number;
  sample_hz: number | null;
  input_limited: boolean;
  tracker: 'motion' | 'iou';
  max_tracked_vehicles: number;
  ocr_budget: number;
  configuration_error?: string | null;
}
export interface TrafficSession extends TrafficSnapshot {
  camera_id: string; camera_name: string; recorded: boolean; status: string; age_ms: number | null;
}
export interface CountingPreview { config: TrafficConfig; draft: boolean }
export const defaultTrafficConfig: TrafficConfig = {
  mode: 'off', axis: 'horizontal', direction: 'both', position: .5,
  span_start: .05, span_end: .95, left: .25, top: .25, right: .75, bottom: .75,
};
const cameraPath = (id: string) => `/cameras/${encodeURIComponent(id)}`;
export const trafficService = {
  settings: (id: string, signal?: AbortSignal) => get<TrafficSettings>(`${cameraPath(id)}/traffic-config`, { signal }),
  save: (id: string, config: TrafficConfig) => put<TrafficSettings>(`${cameraPath(id)}/traffic-config`, config),
  reset: (id: string) => post(`${cameraPath(id)}/traffic-reset`),
  sessions: (signal?: AbortSignal) => get<{ items: TrafficSession[] }>('/traffic/sessions', { signal, timeout: 8000 }),
};
