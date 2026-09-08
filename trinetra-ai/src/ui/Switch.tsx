import { cn } from '@/lib/utils';

/**
 * Switch — 200 ms knob travel, generous 44px hit target, label + optional
 * description on the left. Settings read as a calm list, never as
 * tightly-packed checkboxes.
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
    <div className={cn('flex items-center justify-between gap-6 py-3', disabled && 'opacity-50', className)}>
      <span className="min-w-0">
        <span className="block text-sm font-medium text-ink">{label}</span>
        {description && <span className="mt-0.5 block text-xs leading-relaxed text-ink-faint">{description}</span>}
      </span>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        aria-label={label}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className={cn(
          'relative h-6 w-10 shrink-0 rounded-full border transition-all duration-200',
          'active:scale-95',
          checked ? 'border-accent bg-accent' : 'border-line-strong bg-surface-3 hover:bg-line/60',
        )}
      >
        <span
          aria-hidden
          className={cn(
            'absolute top-1/2 h-4 w-4 -translate-y-1/2 rounded-full bg-white shadow-sm transition-all duration-200',
            checked ? 'left-[20px]' : 'left-[2px]',
          )}
        />
      </button>
    </div>
  );
}

/** Compact chip-style toggle for toolbars and map legends. */
export function SwitchChip({
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
        'inline-flex h-8 cursor-pointer items-center gap-2 rounded-lg border px-3 text-xs font-medium transition-all duration-150 active:scale-[0.97]',
        checked
          ? 'border-accent/30 bg-accent-weak text-accent-strong'
          : 'border-line-strong/70 bg-surface-1 text-ink-muted hover:bg-surface-2 hover:text-ink',
        className,
      )}
    >
      <span
        aria-hidden
        className={cn(
          'relative h-3.5 w-6 shrink-0 rounded-full border transition-colors duration-200',
          checked ? 'border-accent bg-accent' : 'border-line-strong bg-surface-3',
        )}
      >
        <span
          className={cn(
            'absolute top-1/2 h-2.5 w-2.5 -translate-y-1/2 rounded-full bg-white shadow-sm transition-all duration-200',
            checked ? 'left-[12px]' : 'left-[1px]',
          )}
        />
      </span>
      {label}
    </button>
  );
}

/** A labelled settings group — sections related controls with a title. */
export function SettingsGroup({
  title,
  description,
  children,
  className,
}: {
  title: string;
  description?: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={cn('rounded-xl border border-line bg-surface-1 shadow-xs', className)}>
      <div className="border-b border-line px-5 py-3.5">
        <h3 className="text-sm font-semibold text-ink">{title}</h3>
        {description && <p className="mt-0.5 text-xs text-ink-faint">{description}</p>}
      </div>
      <div className="divide-y divide-line/70 px-5">{children}</div>
    </section>
  );
}
