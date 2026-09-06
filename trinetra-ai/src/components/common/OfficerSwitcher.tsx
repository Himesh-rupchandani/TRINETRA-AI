import { useEffect, useRef, useState, type ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import { OfficerAvatar } from '@/components/common/OfficerAvatar';
import { cn } from '@/lib/utils';
import { setCurrentOfficer, useOfficerState } from '@/hooks/useCurrentOfficer';

type Placement = 'bottom-start' | 'bottom-end' | 'top-start';

const PLACEMENT: Record<Placement, string> = {
  'bottom-start': 'left-0 top-full mt-2',
  'bottom-end': 'right-0 top-full mt-2',
  'top-start': 'bottom-full left-0 mb-2',
};

/**
 * OFFICER SWITCHER
 * ----------------
 * The profile area shows only the active officer. Clicking it reveals the
 * other officers; picking one makes that officer active everywhere and opens
 * their Profile page.
 */
export function OfficerSwitcher({
  placement = 'bottom-start',
  className,
  buttonClassName,
  onSelected,
  children,
}: {
  placement?: Placement;
  className?: string;
  buttonClassName?: string;
  /** Called after an officer is picked (e.g. to close the mobile drawer). */
  onSelected?: () => void;
  /** Trigger content — the profile area that is always visible. */
  children?: ReactNode;
}) {
  const { current, roster } = useOfficerState();
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (e: MouseEvent | TouchEvent) => {
      if (!wrapRef.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', onPointerDown);
    document.addEventListener('touchstart', onPointerDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onPointerDown);
      document.removeEventListener('touchstart', onPointerDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  const others = roster.filter((o) => o.officerId !== current?.officerId);

  return (
    <div ref={wrapRef} className={cn('relative', className)}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={current ? `${current.name} — select another officer` : 'Select officer'}
        title="Select another officer"
        className={buttonClassName}
      >
        {children ?? <OfficerAvatar size={36} />}
      </button>

      {open && (
        <div
          role="menu"
          aria-label="Other officers"
          className={cn('panel absolute z-50 w-72 overflow-hidden p-3 shadow-xl', PLACEMENT[placement])}
        >
          <p className="kv-label pb-2">Other Officers</p>
          {others.length ? (
            <ul className="max-h-72 space-y-1 overflow-y-auto">
              {others.map((officer) => (
                <li key={officer.officerId}>
                  <button
                    type="button"
                    role="menuitem"
                    onClick={() => {
                      setCurrentOfficer(officer);
                      setOpen(false);
                      onSelected?.();
                      navigate('/profile');
                    }}
                    className="flex w-full items-center gap-2.5 rounded-xl p-2 text-left transition-colors hover:bg-surface-2"
                  >
                    <OfficerAvatar officer={officer} size={36} />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[13px] font-semibold leading-tight text-ink">
                        {officer.name}
                      </span>
                      <span className="block truncate text-2xs text-ink-faint">{officer.position}</span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="px-2 py-3 text-2xs text-ink-faint">No other officers available.</p>
          )}
        </div>
      )}
    </div>
  );
}
