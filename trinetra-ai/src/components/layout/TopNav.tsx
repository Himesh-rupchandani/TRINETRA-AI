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
 * Per-card colour: soft gradient body, solid top accent bar, glossy
 * gradient icon tile + arrow button, coloured title when active.
 */
const CARD_TONES: Record<
  TileTone,
  { idle: string; active: string; bar: string; solid: string; title: string }
> = {
  blue: {
    idle: 'border-blue-200 bg-gradient-to-br from-blue-100/80 via-blue-50 to-white hover:-translate-y-0.5 hover:border-blue-400 hover:shadow-cardHover',
    active: 'border-blue-500 bg-gradient-to-br from-blue-200/70 via-blue-100 to-blue-50 shadow-cardHover',
    bar: 'border-t-blue-500',
    solid: 'bg-gradient-to-br from-blue-500 to-blue-700',
    title: 'text-blue-700',
  },
  sky: {
    idle: 'border-sky-200 bg-gradient-to-br from-sky-100/80 via-sky-50 to-white hover:-translate-y-0.5 hover:border-sky-400 hover:shadow-cardHover',
    active: 'border-sky-500 bg-gradient-to-br from-sky-200/70 via-sky-100 to-sky-50 shadow-cardHover',
    bar: 'border-t-sky-500',
    solid: 'bg-gradient-to-br from-sky-500 to-sky-700',
    title: 'text-sky-700',
  },
  green: {
    idle: 'border-emerald-200 bg-gradient-to-br from-emerald-100/80 via-emerald-50 to-white hover:-translate-y-0.5 hover:border-emerald-400 hover:shadow-cardHover',
    active: 'border-emerald-500 bg-gradient-to-br from-emerald-200/70 via-emerald-100 to-emerald-50 shadow-cardHover',
    bar: 'border-t-emerald-500',
    solid: 'bg-gradient-to-br from-emerald-500 to-emerald-700',
    title: 'text-emerald-700',
  },
  orange: {
    idle: 'border-orange-200 bg-gradient-to-br from-orange-100/80 via-orange-50 to-white hover:-translate-y-0.5 hover:border-orange-400 hover:shadow-cardHover',
    active: 'border-orange-500 bg-gradient-to-br from-orange-200/70 via-orange-100 to-orange-50 shadow-cardHover',
    bar: 'border-t-orange-500',
    solid: 'bg-gradient-to-br from-orange-500 to-orange-700',
    title: 'text-orange-700',
  },
  amber: {
    idle: 'border-amber-200 bg-gradient-to-br from-amber-100/80 via-amber-50 to-white hover:-translate-y-0.5 hover:border-amber-400 hover:shadow-cardHover',
    active: 'border-amber-500 bg-gradient-to-br from-amber-200/70 via-amber-100 to-amber-50 shadow-cardHover',
    bar: 'border-t-amber-500',
    solid: 'bg-gradient-to-br from-amber-500 to-amber-700',
    title: 'text-amber-700',
  },
  purple: {
    idle: 'border-violet-200 bg-gradient-to-br from-violet-100/80 via-violet-50 to-white hover:-translate-y-0.5 hover:border-violet-400 hover:shadow-cardHover',
    active: 'border-violet-500 bg-gradient-to-br from-violet-200/70 via-violet-100 to-violet-50 shadow-cardHover',
    bar: 'border-t-violet-500',
    solid: 'bg-gradient-to-br from-violet-500 to-violet-700',
    title: 'text-violet-700',
  },
  red: {
    idle: 'border-rose-200 bg-gradient-to-br from-rose-100/80 via-rose-50 to-white hover:-translate-y-0.5 hover:border-rose-400 hover:shadow-cardHover',
    active: 'border-rose-500 bg-gradient-to-br from-rose-200/70 via-rose-100 to-rose-50 shadow-cardHover',
    bar: 'border-t-rose-500',
    solid: 'bg-gradient-to-br from-rose-500 to-rose-700',
    title: 'text-rose-700',
  },
  slate: {
    idle: 'border-slate-200 bg-gradient-to-br from-slate-100/80 via-slate-50 to-white hover:-translate-y-0.5 hover:border-slate-400 hover:shadow-cardHover',
    active: 'border-slate-500 bg-gradient-to-br from-slate-200/70 via-slate-100 to-slate-50 shadow-cardHover',
    bar: 'border-t-slate-500',
    solid: 'bg-gradient-to-br from-slate-500 to-slate-700',
    title: 'text-slate-700',
  },
};

export function TopNav() {
  return (
    <nav aria-label="Primary" className="sticky top-14 z-10 shrink-0 border-b border-line bg-surface-0">
      {/* Primary workflow cards — all five fit a single screen row. */}
      <ul className="no-scrollbar mx-auto flex max-w-[1600px] gap-2.5 overflow-x-auto px-3 py-2.5 sm:px-5">
        {PRIMARY.map((item) => {
          const Icon = item.icon;
          const tone = CARD_TONES[item.tone];
          return (
            <li key={item.to} className="min-w-[230px] flex-1">
              <NavLink
                to={item.to}
                end={false}
                title={`${item.label} — ${item.hint}`}
                className={({ isActive }) =>
                  cn(
                    'group flex w-full items-center gap-3 rounded-xl border border-t-4 p-3.5 shadow-panel transition-all duration-150',
                    tone.bar,
                    isActive ? tone.active : tone.idle,
                  )
                }
              >
                {({ isActive }) => (
                  <>
                    <span
                      className={cn(
                        'grid h-12 w-12 shrink-0 place-items-center rounded-xl text-white shadow-md',
                        tone.solid,
                      )}
                      aria-hidden
                    >
                      <Icon size={22} />
                    </span>
                    <span className="min-w-0 flex-1">
                      <span
                        className={cn(
                          'block truncate text-[15px] font-extrabold leading-tight tracking-tight',
                          isActive ? tone.title : 'text-ink',
                        )}
                      >
                        {item.label}
                      </span>
                      <span className="mt-1 block min-h-9 overflow-hidden text-xs leading-snug text-ink-muted [-webkit-box-orient:vertical] [-webkit-line-clamp:2] [display:-webkit-box]">
                        {item.hint}
                      </span>
                    </span>
                    <span
                      className={cn(
                        'grid h-9 w-9 shrink-0 place-items-center rounded-full text-white shadow transition-all duration-150 group-hover:translate-x-0.5 group-hover:scale-105 group-hover:shadow-md',
                        tone.solid,
                      )}
                      aria-hidden
                    >
                      <ChevronRight size={18} />
                    </span>
                  </>
                )}
              </NavLink>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
