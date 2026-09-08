import { cn } from '@/lib/utils';

/**
 * Underline tabs — the active indicator is a 2px accent bar that
 * cross-fades as tabs change. Quiet, keyboard-accessible.
 */
export function Tabs<T extends string>({
  value,
  onChange,
  items,
  className,
}: {
  value: T;
  onChange: (next: T) => void;
  items: { value: T; label: string; count?: number }[];
  className?: string;
}) {
  return (
    <div role="tablist" className={cn('flex items-end gap-1 border-b border-line', className)}>
      {items.map((t) => {
        const active = t.value === value;
        return (
          <button
            key={t.value}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => onChange(t.value)}
            className={cn(
              'relative -mb-px flex h-9 items-center gap-2 border-b-2 px-3.5 text-[13px] font-medium transition-colors duration-150',
              active
                ? 'border-accent text-ink'
                : 'border-transparent text-ink-muted hover:border-line-strong hover:text-ink',
            )}
          >
            {t.label}
            {t.count != null && (
              <span
                className={cn(
                  'mono rounded-full px-1.5 text-[11px] leading-[18px]',
                  active ? 'bg-accent-weak text-accent-strong' : 'bg-surface-3 text-ink-faint',
                )}
              >
                {t.count}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
