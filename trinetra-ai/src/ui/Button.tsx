import { forwardRef, type ButtonHTMLAttributes } from 'react';
import { Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger' | 'link';
type Size = 'xs' | 'sm' | 'md';

const VARIANTS: Record<Variant, string> = {
  // Institutional green fill — brightens a touch on hover, sinks on press.
  primary:
    'bg-accent text-white hover:bg-accent-strong',
  secondary:
    'border border-line-strong/80 bg-surface-1 text-ink hover:border-line-strong hover:bg-surface-2 active:bg-surface-3/70',
  ghost: 'text-ink-muted hover:bg-surface-2 hover:text-ink active:bg-surface-3/70',
  danger:
    'border border-critical/25 bg-critical/[0.06] text-critical hover:bg-critical/10 active:bg-critical/15',
  link: 'text-accent underline-offset-2 hover:underline px-0',
};

const SIZES: Record<Size, string> = {
  xs: 'h-7 gap-1.5 rounded-md px-2.5 text-xs',
  sm: 'h-8.5 gap-2 rounded-lg px-3.5 text-[13px]',
  md: 'h-10 gap-2 rounded-lg px-4.5 text-sm',
};

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
}

/**
 * SENTINEL button. Micro-interaction contract:
 * hover  — surface/border shift, 150 ms
 * press  — scale 0.98 (physical "push")
 * load   — inline spinner replaces the label rhythm
 */
export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = 'secondary', size = 'sm', loading = false, className, children, disabled, ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      disabled={disabled || loading}
      className={cn(
        'inline-select-none inline-flex select-none items-center justify-center whitespace-nowrap font-medium transition-all duration-150',
        'active:scale-[0.98]',
        'disabled:pointer-events-none disabled:opacity-45',
        VARIANTS[variant],
        SIZES[size],
        className,
      )}
      {...rest}
    >
      {loading && <Loader2 size={size === 'xs' ? 12 : 14} className="animate-spin" aria-hidden />}
      {children}
    </button>
  );
});

/** Class string for link-styled-as-button (react-router <Link>). */
export function buttonClass(variant: Variant = 'secondary', size: Size = 'sm', className?: string) {
  return cn(
    'inline-flex select-none items-center justify-center whitespace-nowrap font-medium transition-all duration-150',
    'active:scale-[0.98]',
    VARIANTS[variant],
    SIZES[size],
    className,
  );
}
