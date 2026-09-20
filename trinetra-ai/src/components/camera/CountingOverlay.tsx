import { useId } from 'react';
import { countingGeometry } from '@/lib/traffic';
import type { CountingPreview } from '@/services/trafficService';

/** SVG meet uses the exact object-contain/letterbox geometry of the player. */
export function CountingOverlay({ preview, width, height }: { preview: CountingPreview; width: number; height: number }) {
  const arrowId = useId().replace(/:/g, '');
  const c = preview.config;
  const shape = countingGeometry(c, width, height);
  if (!shape) return null;
  const horizontal = c.axis === 'horizontal';
  const color = preview.draft ? '#fbbf24' : '#22d3ee';
  const centerX = c.mode === 'zone' ? (c.left+c.right)/2 : horizontal ? (c.span_start+c.span_end)/2 : c.position;
  const centerY = c.mode === 'zone' ? (c.top+c.bottom)/2 : horizontal ? c.position : (c.span_start+c.span_end)/2;
  const sign = c.direction === 'negative' ? -1 : 1;
  return (
    <svg className="pointer-events-none absolute inset-0 z-[6] h-full w-full" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="xMidYMid meet" aria-label={preview.draft ? 'Unsaved counting geometry preview' : 'Saved counting geometry'}>
      <defs><marker id={arrowId} markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto"><path d="M0,0 L6,3 L0,6Z" fill={color} /></marker></defs>
      {shape.kind === 'line' ? <line
        x1={shape.x1} y1={shape.y1} x2={shape.x2} y2={shape.y2}
        stroke={color} strokeWidth="2" strokeDasharray="9 5" vectorEffect="non-scaling-stroke" /> :
        <rect x={shape.x} y={shape.y} width={shape.width} height={shape.height}
          fill={color} fillOpacity=".08" stroke={color} strokeWidth="2" vectorEffect="non-scaling-stroke" />}
      {c.direction !== 'both' && <line
        x1={(centerX-(horizontal ? 0 : .045*sign))*width} y1={(centerY-(horizontal ? .045*sign : 0))*height}
        x2={(centerX+(horizontal ? 0 : .045*sign))*width} y2={(centerY+(horizontal ? .045*sign : 0))*height}
        stroke={color} strokeWidth="2" vectorEffect="non-scaling-stroke" markerEnd={`url(#${arrowId})`} />}
      <text x="12" y={height-34} fill={color} stroke="#000" strokeWidth=".8" paintOrder="stroke" fontSize={Math.max(12,width/90)}>
        {preview.draft ? 'UNSAVED PREVIEW' : 'COUNTING'} · {c.mode.toUpperCase()} · not a violation rule
      </text>
    </svg>
  );
}
