import { memo, useMemo } from 'react';
import { Link } from 'react-router-dom';
import { Activity, MapPin, Maximize2, Radio, Video } from 'lucide-react';
import type { Camera } from '@/types';
import { cn, formatTime, relativeTime } from '@/lib/utils';
import { config } from '@/lib/config';
import { cameraStill, hideBrokenImage } from '@/utils/mediaAssets';

interface Props {
  camera: Camera;
  onView?: (camera: Camera) => void;
  compact?: boolean;
  selected?: boolean;
  variant?: 'card' | 'list' | 'feed';
}

/** Deterministic demo latency for a camera (mock mode only, 60–160 ms). */
function demoLatencyMs(id: string): number {
  let h = 0;
  for (let i = 0; i < id.length; i++) h = (h * 31 + id.charCodeAt(i)) % 997;
  return 60 + (h % 100);
}

/** Detections per minute over the recent window we actually hold. */
function detectionsPerMinute(recentCount: number, windowMinutes: number): string {
  if (!recentCount && !windowMinutes) return '—';
  return (recentCount / Math.max(windowMinutes, 1)).toFixed(1);
}

const STATE_BADGE: Record<Camera['status'], { label: string; cls: string }> = {
  ONLINE: { label: 'LIVE', cls: 'text-online' },
  DEGRADED: { label: 'POOR', cls: 'text-degraded' },
  OFFLINE: { label: 'OFFLINE', cls: 'text-offline' },
};

/**
 * Registry card / mosaic feed tile. Deliberately does NOT mount a stream —
 * feeds are only loaded when an operator explicitly opens one (see
 * performance notes). Every tile carries the control-room HUD: camera ID,
 * location, frame rate / latency and detections-per-minute, over a scanline
 * surface with a slow radar sweep.
 */
export const CameraCard = memo(function CameraCard({
  camera,
  onView,
  compact,
  selected,
  variant = 'card',
  recentCount,
  windowMinutes = 15,
}: Props & { recentCount?: number; windowMinutes?: number }) {
  const preview = useMemo(
    () => (config.useMocks ? cameraStill(camera.id) : null),
    [camera.id],
  );

  const dpm = detectionsPerMinute(recentCount ?? camera.eventCount24h ?? 0, recentCount != null ? windowMinutes : 1440);
  const fps = camera.fps ? camera.fps.toFixed(0) : '—';
  const state = STATE_BADGE[camera.status];

  /* ---------------- Mosaic feed tile (dashboard camera wall) ---------------- */
  if (variant === 'feed') {
    return (
      <Link
        to={`/cameras/${camera.id}`}
        className={cn(
          'card-hover group relative block overflow-hidden rounded-lg border border-line bg-surface-2',
          'aspect-video focus-visible:rounded-lg',
          selected && 'border-brand/60 ring-1 ring-brand/30',
        )}
        aria-label={`${camera.name} — ${camera.location}. Open camera.`}
      >
        {/* Poster / placeholder */}
        <span className="grid h-full w-full place-items-center text-ink-faint" aria-hidden>
          <Video size={18} />
        </span>
        {preview && (
          <img
            src={preview}
            alt=""
            onError={hideBrokenImage}
            className="absolute inset-0 h-full w-full object-cover"
            loading="lazy"
          />
        )}

        {/* CRT scanlines + radar sweep */}
        <span className="scanline pointer-events-none absolute inset-0" aria-hidden />
        <span className="scan-sweep" aria-hidden />

        {/* HUD — top row: camera ID + state */}
        <span className="hud-chip absolute left-1.5 top-1.5 text-brand">{camera.name}</span>
        <span className={cn('hud-chip absolute right-1.5 top-1.5', state.cls)}>
          <span
            className={cn(
              'h-1.5 w-1.5 rounded-full bg-current',
              camera.status === 'ONLINE' && 'live-dot',
            )}
            aria-hidden
          />
          {state.label}
        </span>

        {/* HUD — bottom bar: location + fps/latency + detections/min */}
        <span className="absolute inset-x-1.5 bottom-1.5 flex items-center gap-1.5">
          <span className="hud-chip min-w-0 flex-1 justify-start text-white/75">
            <MapPin size={9} className="shrink-0" aria-hidden />
            <span className="truncate">{camera.location}</span>
          </span>
          <span className="hud-chip shrink-0 tabular-nums text-white/85">
            {fps} FPS{config.useMocks && ` · ${demoLatencyMs(camera.id)} MS`}
          </span>
          <span className="hud-chip shrink-0 tabular-nums text-accent">{dpm}/MIN</span>
        </span>

        {preview && (
          <span className="hud-chip absolute left-1.5 top-9 text-accent/90">DEMO</span>
        )}
      </Link>
    );
  }

  /* ---------------- Compact list row ---------------- */
  if (variant === 'list') {
    return (
      <Link
        to={`/cameras/${camera.id}`}
        className={cn(
          'card-hover flex items-center gap-3 rounded-lg border border-line bg-surface-1 p-2.5',
          selected && 'border-brand/50 ring-1 ring-brand/20',
        )}
      >
        <span className="scanline relative grid h-12 w-[76px] shrink-0 place-items-center overflow-hidden rounded-md border border-line bg-surface-2 text-ink-faint">
          <Video size={16} aria-hidden />
          {preview && (
            <img
              src={preview}
              alt=""
              onError={hideBrokenImage}
              className="absolute inset-0 h-full w-full object-cover"
              loading="lazy"
            />
          )}
        </span>
        <div className="min-w-0 flex-1">
          <p className="truncate font-mono text-xs font-bold text-ink">{camera.name}</p>
          <p className="mt-0.5 flex items-center gap-1 truncate text-2xs text-ink-faint">
            <MapPin size={10} className="shrink-0" aria-hidden />
            {camera.location}
          </p>
        </div>
        <span className="flex flex-col items-end gap-0.5">
          <span className="font-mono text-2xs tabular-nums text-ink-faint">{dpm}/min</span>
          <span className={cn('font-mono text-2xs font-semibold', state.cls)}>{state.label}</span>
        </span>
      </Link>
    );
  }

  /* ---------------- Registry card ---------------- */
  return (
    <article
      className={cn(
        'panel card-hover group flex flex-col overflow-hidden hover:shadow-cardHover',
        selected && 'border-brand/60 ring-1 ring-brand/30',
      )}
    >
      {!compact && (
        <div className="relative">
          <div className="grid aspect-video w-full place-items-center border-b border-line bg-surface-2 text-ink-faint">
            <Video size={18} aria-hidden />
          </div>
          {preview && (
            <img
              src={preview}
              alt=""
              onError={hideBrokenImage}
              className="absolute inset-0 aspect-video w-full border-b border-line object-cover"
              loading="lazy"
            />
          )}
          {/* HUD */}
          <span className="hud-chip absolute left-1.5 top-1.5 text-brand">{camera.name}</span>
          <span className={cn('hud-chip absolute right-1.5 top-1.5', state.cls)}>
            <span
              className={cn(
                'h-1.5 w-1.5 rounded-full bg-current',
                camera.status === 'ONLINE' && 'live-dot',
              )}
              aria-hidden
            />
            {state.label}
          </span>
          <span className="hud-chip absolute bottom-1.5 right-1.5 tabular-nums text-white/85">
            {fps} FPS · {dpm}/MIN
          </span>
          <span className="scanline pointer-events-none absolute inset-0" aria-hidden />
          <span className="scan-sweep" aria-hidden />
          {preview && (
            <span className="hud-chip absolute bottom-1.5 left-1.5 text-accent/90">DEMO</span>
          )}
        </div>
      )}

      <div className="flex items-start justify-between gap-2.5 px-4 py-3">
        <div className="min-w-0">
          <div className="flex items-center gap-1.5">
            <Video size={14} className="shrink-0 text-ink-faint" aria-hidden />
            <h3 className="truncate font-mono text-sm font-bold text-ink">{camera.name}</h3>
          </div>
          <p className="mt-1 flex items-center gap-1 truncate text-2xs text-ink-muted">
            <MapPin size={10} className="shrink-0" aria-hidden />
            {camera.location}
          </p>
        </div>
        <span className={cn('flex items-center gap-1.5 font-mono text-2xs font-semibold', state.cls)}>
          <Radio size={11} aria-hidden />
          {state.label}
        </span>
      </div>

      {!compact && (
        <dl className="grid grid-cols-2 gap-x-3 gap-y-2 px-4 pb-3 text-2xs">
          <dt className="text-ink-faint">Department</dt>
          <dd className="truncate text-right text-ink-muted">{camera.department ?? '—'}</dd>
          <dt className="text-ink-faint">Video format</dt>
          <dd className="text-right font-mono text-ink-muted">{camera.codec ?? '—'}</dd>
          <dt className="text-ink-faint">Picture size</dt>
          <dd className="text-right font-mono tabular-nums text-ink-muted">
            {camera.width ? `${camera.width}×${camera.height}` : '—'}
          </dd>
          <dt className="text-ink-faint">Last vehicle</dt>
          <dd className="text-right font-mono tabular-nums text-ink-muted">
            {camera.lastEventAt ? formatTime(camera.lastEventAt) : '—'}
          </dd>
        </dl>
      )}

      <div className="mt-auto flex flex-wrap items-center justify-between gap-x-2.5 gap-y-2 border-t border-line/70 px-4 py-2.5">
        <span
          className="flex items-center gap-1.5 whitespace-nowrap text-2xs text-ink-faint"
          title="Vehicles seen by this camera in the last 24 hours"
        >
          <Activity size={12} aria-hidden />
          <span className="font-mono tabular-nums">{camera.eventCount24h ?? 0}</span> · {relativeTime(camera.lastEventAt)}
        </span>
        <div className="ml-auto flex items-center gap-2">
          {onView && (
            <button
              type="button"
              className="btn-ghost btn-xs"
              onClick={() => onView(camera)}
              title="Quick look without leaving this page"
            >
              <Maximize2 size={12} aria-hidden /> Quick look
            </button>
          )}
          <Link to={`/cameras/${camera.id}`} className="btn-tint btn-xs">
            Open camera
          </Link>
        </div>
      </div>
    </article>
  );
});
