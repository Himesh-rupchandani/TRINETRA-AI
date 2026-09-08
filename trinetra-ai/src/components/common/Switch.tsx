import { cn } from '@/lib/utils';

/**
 * Accessible toggle switch with a generous hit area.
 *
 * Used as a labeled control row (label left, switch right) so related
 * settings read as a calm list with comfortable vertical rhythm — never
 * as tightly-packed checkboxes.
 */
export function Switch({
  checked,
  onChange,
  label,
  description,
  disabled = false,
  className,
}: {
  checked: boolean;
  onChange: (next: boolean) => void;
  label: string;
  description?: string;
  disabled?: boolean;
  className?: string;
}) {
  return (
    <label
      className={cn(
        'flex cursor-pointer items-center justify-between gap-6 rounded-lg py-2',
        disabled ? 'cursor-not-allowed opacity-45' : 'group',
        className,
      )}
    >
      <span className="min-w-0">
        <span className="block text-sm font-medium text-ink">{label}</span>
        {description && (
          <span className="mt-0.5 block text-2xs leading-snug text-ink-faint">{description}</span>
        )}
      </span>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        aria-label={label}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className={cn(
          'relative h-6 w-11 shrink-0 rounded-full border transition-colors',
          checked ? 'border-transparent bg-brand-strong' : 'border-line-strong bg-surface-3',
        )}
      >
        <span
          aria-hidden
          className={cn(
            'absolute top-1/2 -translate-y-1/2 rounded-full transition-all',
            checked ? 'left-[24px] bg-white' : 'left-[3px] bg-ink-faint',
          )}
          style={{ height: 18, width: 18 }}
        />
      </button>
    </label>
  );
}

/** Compact variant for tight surfaces (map legends, video OSD rows). */
export function SwitchCompact({
  checked,
  onChange,
  label,
  title,
  className,
}: {
  checked: boolean;
  onChange: (next: boolean) => void;
  label: string;
  title?: string;
  className?: string;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      title={title}
      onClick={() => onChange(!checked)}
      className={cn(
        'inline-flex min-h-8 cursor-pointer items-center gap-2.5 rounded-lg border px-3 text-xs font-medium transition-colors',
        checked
          ? 'border-brand/30 bg-brand/10 text-brand'
          : 'border-line bg-transparent text-ink-muted hover:bg-surface-2 hover:text-ink',
        className,
      )}
    >
      <span
        aria-hidden
        className={cn(
          'relative h-3.5 w-6 shrink-0 rounded-full border transition-colors',
          checked ? 'border-transparent bg-brand-strong' : 'border-line-strong bg-surface-3',
        )}
      >
        <span
          className={cn(
            'absolute top-1/2 h-2.5 w-2.5 -translate-y-1/2 rounded-full transition-all',
            checked ? 'left-[13px] bg-white' : 'left-[2px] bg-ink-faint',
          )}
        />
      </span>
      {label}
    </button>
  );
}
