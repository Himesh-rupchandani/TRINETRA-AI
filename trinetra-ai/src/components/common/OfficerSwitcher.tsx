import { useEffect, useRef, useState } from 'react';
import { Check } from 'lucide-react';
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
 * The officer photo doubles as the control room's officer selector. Clicking
 * it opens a panel listing the current officer plus the rest of the roster;
 * picking one makes it active everywhere (sidebar, header, Profile page).
 */
export function OfficerSwitcher({
  size = 36,
  placement = 'bottom-start',
  avatarClassName,
  className,
}: {
  size?: number;
  placement?: Placement;
  avatarClassName?: string;
  className?: string;
}) {
  const { current, roster } = useOfficerState();
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);

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
    <div ref={wrapRef} className={cn('relative shrink-0', className)}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={current ? `Signed in as ${current.name} — switch officer` : 'Switch officer'}
        title="Switch officer"
        className="block rounded-full outline-none ring-brand/40 transition-shadow hover:ring-2 focus-visible:ring-2"
      >
        <OfficerAvatar size={size} className={avatarClassName} />
      </button>

      {open && (
        <div
          role="menu"
          aria-label="Select officer"
          className={cn('panel absolute z-50 w-72 overflow-hidden p-0 shadow-xl', PLACEMENT[placement])}
        >
          {current && (
            <div className="border-b border-line bg-surface-2/60 p-3">
              <p className="kv-label pb-2">Current Officer</p>
              <div className="flex items-center gap-2.5 rounded-xl border border-brand/30 bg-brand/10 p-2.5">
                <OfficerAvatar officer={current} size={40} />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-[13px] font-semibold leading-tight text-brand">{current.name}</p>
                  <p className="truncate text-2xs text-ink-muted">{current.position}</p>
                </div>
                <Check size={15} className="shrink-0 text-brand" aria-hidden />
              </div>
            </div>
          )}

          {others.length > 0 && (
            <div className="p-3">
              <p className="kv-label pb-2">Other Officers</p>
              <ul className="max-h-64 space-y-1 overflow-y-auto">
                {others.map((officer) => (
                  <li key={officer.officerId}>
                    <button
                      type="button"
                      role="menuitem"
                      onClick={() => {
                        setCurrentOfficer(officer);
                        setOpen(false);
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
            </div>
          )}
        </div>
      )}
    </div>
  );
}
