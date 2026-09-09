import { useEffect, useRef } from 'react';
import { NavLink } from 'react-router-dom';
import { Car, Cctv, ChevronRight, ListTree, Map, Video } from 'lucide-react';
import type { TileTone } from '@/components/common/IconTile';
import { cn } from '@/lib/utils';

interface TopNavItem {
  to: string;
  label: string;
  /** One line explaining what the page is for, shown under the label. */
  hint: string;
  icon: typeof Video;
  tone: TileTone;
}

/**
 * The core workflow, in exact investigation order. These five cards are
 * the primary navigation of the whole application:
 * Video Analysis → Live Cameras → Find Vehicle → Map → Vehicle Log.
 * (Supporting sections — Dashboard, Wanted List, Camera List,
 * System Status — live in the header bar above.)
 */
const PRIMARY: TopNavItem[] = [
  { to: '/video-analysis', label: 'Video Analysis', hint: 'Upload and analyse CCTV or video files', icon: Video, tone: 'blue' },
  { to: '/cameras', label: 'Live Cameras', hint: 'Watch live CCTV feeds', icon: Cctv, tone: 'green' },
  { to: '/vehicles', label: 'Find Vehicle', hint: 'Search by number plate', icon: Car, tone: 'sky' },
  { to: '/gis', label: 'Map', hint: 'Cameras & vehicles on the map', icon: Map, tone: 'orange' },
  { to: '/events', label: 'Vehicle Log', hint: 'Full vehicle history', icon: ListTree, tone: 'purple' },
];

/**
 * Per-card colour: flat pastel body, coloured line icon straight on the
 * tint, dark title, white arrow chip with a coloured chevron.
 */
const CARD_TONES: Record<
  TileTone,
  { idle: string; active: string; icon: string; arrow: string }
> = {
  blue: {
    idle: 'border-blue-200 bg-blue-100 hover:-translate-y-0.5 hover:border-blue-300 hover:shadow-md',
    active: 'border-blue-400 bg-blue-200/60 shadow-md ring-2 ring-blue-500/25',
    icon: 'text-blue-600',
    arrow: 'text-blue-600',
  },
  sky: {
    idle: 'border-sky-200 bg-sky-100 hover:-translate-y-0.5 hover:border-sky-300 hover:shadow-md',
    active: 'border-sky-400 bg-sky-200/60 shadow-md ring-2 ring-sky-500/25',
    icon: 'text-sky-600',
    arrow: 'text-sky-600',
  },
  green: {
    idle: 'border-emerald-200 bg-emerald-100 hover:-translate-y-0.5 hover:border-emerald-300 hover:shadow-md',
    active: 'border-emerald-400 bg-emerald-200/60 shadow-md ring-2 ring-emerald-500/25',
    icon: 'text-emerald-600',
    arrow: 'text-emerald-600',
  },
  orange: {
    idle: 'border-orange-200 bg-orange-100 hover:-translate-y-0.5 hover:border-orange-300 hover:shadow-md',
    active: 'border-orange-400 bg-orange-200/60 shadow-md ring-2 ring-orange-500/25',
    icon: 'text-orange-600',
    arrow: 'text-orange-600',
  },
  amber: {
    idle: 'border-amber-200 bg-amber-100 hover:-translate-y-0.5 hover:border-amber-300 hover:shadow-md',
    active: 'border-amber-400 bg-amber-200/60 shadow-md ring-2 ring-amber-500/25',
    icon: 'text-amber-600',
    arrow: 'text-amber-600',
  },
  purple: {
    idle: 'border-violet-200 bg-violet-100 hover:-translate-y-0.5 hover:border-violet-300 hover:shadow-md',
    active: 'border-violet-400 bg-violet-200/60 shadow-md ring-2 ring-violet-500/25',
    icon: 'text-violet-600',
    arrow: 'text-violet-600',
  },
  red: {
    idle: 'border-rose-200 bg-rose-100 hover:-translate-y-0.5 hover:border-rose-300 hover:shadow-md',
    active: 'border-rose-400 bg-rose-200/60 shadow-md ring-2 ring-rose-500/25',
    icon: 'text-rose-600',
    arrow: 'text-rose-600',
  },
  slate: {
    idle: 'border-slate-200 bg-slate-100 hover:-translate-y-0.5 hover:border-slate-300 hover:shadow-md',
    active: 'border-slate-400 bg-slate-200/60 shadow-md ring-2 ring-slate-500/25',
    icon: 'text-slate-600',
    arrow: 'text-slate-600',
  },
};

export function TopNav() {
  const navRef = useRef<HTMLElement>(null);

  // Card height varies with viewport width (hints wrap), so publish the
  // measured bar height for sticky content offsets (see .data-table-page).
  useEffect(() => {
    const el = navRef.current;
    if (!el) return;
    const write = () =>
      document.documentElement.style.setProperty('--trinetra-nav-h', `${el.offsetHeight}px`);
    write();
    const ro = new ResizeObserver(write);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  return (
    <nav ref={navRef} aria-label="Primary" className="sticky top-14 z-10 shrink-0 border-b border-line bg-surface-0">
      {/* Primary workflow cards — all five fit a single screen row. */}
      <ul className="no-scrollbar mx-auto flex max-w-[1600px] gap-2.5 overflow-x-auto px-3 py-2.5 sm:px-5">
        {PRIMARY.map((item) => {
          const Icon = item.icon;
          const tone = CARD_TONES[item.tone];
          return (
            <li key={item.to} className="min-w-[220px] flex-1">
              <NavLink
                to={item.to}
                end={false}
                title={`${item.label} — ${item.hint}`}
                className={({ isActive }) =>
                  cn(
                    'group flex h-full w-full items-center gap-2.5 rounded-2xl border p-3 shadow-sm transition-all duration-150',
                    isActive ? tone.active : tone.idle,
                  )
                }
              >
                <span className={cn('grid h-12 w-12 shrink-0 place-items-center', tone.icon)} aria-hidden>
                  <Icon size={28} strokeWidth={2.25} />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block text-[15px] font-extrabold leading-tight tracking-tight text-ink">
                    {item.label}
                  </span>
                  <span className="mt-0.5 block text-xs leading-snug text-ink-muted">{item.hint}</span>
                </span>
                <span
                  className={cn(
                    'grid h-10 w-10 shrink-0 place-items-center rounded-full bg-white/80 shadow-sm transition-transform duration-150 group-hover:translate-x-0.5',
                    tone.arrow,
                  )}
                  aria-hidden
                >
                  <ChevronRight size={20} />
                </span>
              </NavLink>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
