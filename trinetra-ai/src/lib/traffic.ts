import type { TrafficConfig } from '@/services/trafficService';

export function trafficConfigProblem(config: TrafficConfig): string | null {
  if (!['off', 'line', 'zone'].includes(config.mode) || !['horizontal', 'vertical'].includes(config.axis) || !['both', 'positive', 'negative'].includes(config.direction)) return 'Unsupported counting rule.';
  for (const key of ['position', 'span_start', 'span_end', 'left', 'right', 'top', 'bottom'] as const) {
    if (!Number.isFinite(config[key]) || config[key] < 0 || config[key] > 1) return 'Positions must be between 0% and 100%.';
  }
  if (config.span_end - config.span_start < .02 - 1e-9) return 'Line span end must be at least 2% after its start.';
  if (config.right - config.left < .02 - 1e-9 || config.bottom - config.top < .02 - 1e-9) return 'Zone right/bottom must be at least 2% after left/top.';
  return null;
}

export function countingGeometry(config: TrafficConfig, width: number, height: number) {
  if (trafficConfigProblem(config) || config.mode === 'off' || !(width > 0 && height > 0)) return null;
  const horizontal = config.axis === 'horizontal';
  if (config.mode === 'line') return {
    kind: 'line' as const,
    x1: (horizontal ? config.span_start : config.position) * width,
    y1: (horizontal ? config.position : config.span_start) * height,
    x2: (horizontal ? config.span_end : config.position) * width,
    y2: (horizontal ? config.position : config.span_end) * height,
  };
  return {
    kind: 'zone' as const,
    x: config.left * width, y: config.top * height,
    width: (config.right-config.left) * width, height: (config.bottom-config.top) * height,
  };
}
