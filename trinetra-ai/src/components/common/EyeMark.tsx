import { cn } from '@/lib/utils';

/**
 * The Trinetra "third eye" — concentric radar rings around a pupil, with a
 * slow vertical scan sweep. The brand mark of the control room: many cameras,
 * one eye that never blinks. Decorative only (aria-hidden by default).
 */
export function EyeMark({
  size = 36,
  className,
  sweep = true,
}: {
  size?: number;
  className?: string;
  /** Enable the animated scan line (disable in reduced contexts / tiny sizes). */
  sweep?: boolean;
}) {
  return (
    <svg
      viewBox="0 0 48 48"
      width={size}
      height={size}
      className={cn('shrink-0', className)}
      aria-hidden
      focusable="false"
    >
      {/* Field */}
      <circle cx="24" cy="24" r="23" className="fill-brand/6" />
      {/* Concentric rings */}
      <circle cx="24" cy="24" r="21.5" className="stroke-brand/25" strokeWidth="1" fill="none" />
      <circle cx="24" cy="24" r="15.5" className="stroke-brand/45" strokeWidth="1" fill="none" />
      {/* Compass ticks */}
      <path
        d="M24 1.5v4M24 42.5v4M1.5 24h4M42.5 24h4"
        className="stroke-brand/40"
        strokeWidth="1.4"
        strokeLinecap="round"
      />
      {/* Iris + pupil */}
      <circle cx="24" cy="24" r="9" className="fill-brand/12 stroke-brand" strokeWidth="1.4" />
      <circle cx="24" cy="24" r="3.4" className="fill-brand" />
      {/* Scan sweep — horizontal line travelling through the iris */}
      {sweep && (
        <g className="eye-sweep">
          <rect x="12" y="23" width="24" height="1.6" rx="0.8" className="fill-brand/70" />
          <rect x="16" y="22.2" width="16" height="0.6" rx="0.3" className="fill-brand/35" />
        </g>
      )}
    </svg>
  );
}
