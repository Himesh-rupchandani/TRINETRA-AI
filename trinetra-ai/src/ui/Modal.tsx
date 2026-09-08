import { useEffect, useRef, type ReactNode } from 'react';
import { X } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Button } from './Button';

/**
 * Dialog — overlay fades, panel rises and settles (170 ms).
 * Esc closes, backdrop click closes, focus moves in on open.
 */
export function Modal({
  open,
  onClose,
  title,
  subtitle,
  children,
  footer,
  size = 'md',
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  subtitle?: string;
  children: ReactNode;
  footer?: ReactNode;
  size?: 'sm' | 'md' | 'lg' | 'xl';
}) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKey);
    ref.current?.focus();
    return () => document.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open) return null;

  const widths = { sm: 'max-w-md', md: 'max-w-xl', lg: 'max-w-3xl', xl: 'max-w-5xl' };

  return (
    <div
      className="overlay-in fixed inset-0 z-[1100] flex items-center justify-center bg-ink/45 p-4 backdrop-blur-[2px] sm:p-6"
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}
    >
      <div
        ref={ref}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className={cn(
          'dialog-in flex max-h-[92vh] w-full flex-col rounded-lg border border-line bg-surface-1 shadow-lg outline-none',
          widths[size],
        )}
      >
        <header className="flex shrink-0 items-start justify-between gap-4 border-b border-line px-5 py-4">
          <div className="min-w-0">
            <h2 className="text-base font-semibold text-ink">{title}</h2>
            {subtitle && <p className="mt-0.5 text-xs text-ink-faint">{subtitle}</p>}
          </div>
          <Button variant="ghost" size="xs" onClick={onClose} aria-label="Close dialog" className="-mr-1 px-1.5">
            <X size={15} aria-hidden />
          </Button>
        </header>
        <div className="min-h-0 flex-1 overflow-auto p-5">{children}</div>
        {footer && (
          <footer className="flex shrink-0 flex-wrap justify-end gap-2.5 border-t border-line px-5 py-3.5">
            {footer}
          </footer>
        )}
      </div>
    </div>
  );
}
