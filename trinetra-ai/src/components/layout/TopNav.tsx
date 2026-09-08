import { NavLink } from 'react-router-dom';
import {
  Activity,
  Bell,
  Car,
  Cctv,
  ChevronRight,
  LayoutDashboard,
  ListTree,
  Map,
  ScrollText,
  ShieldCheck,
  UserRound,
  Video,
} from 'lucide-react';
import { IconTile, type TileTone } from '@/components/common/IconTile';
import { cn } from '@/lib/utils';
import { useAlerts } from '@/hooks/useAlerts';

interface TopNavItem {
  to: string;
  label: string;
  /** One line explaining what the page is for, shown under the label. */
  hint: string;
  icon: typeof LayoutDashboard;
  tone: TileTone;
  badge?: 'alerts';
  end?: boolean;
}

/**
 * Supporting sections — slim links sitting at the very top of the bar,
 * right under the header.
 */
const SECONDARY: TopNavItem[] = [
  { to: '/', label: 'Dashboard', hint: 'Overview & statistics', icon: LayoutDashboard, tone: 'blue', end: true },
  { to: '/alerts', label: 'Alerts', hint: 'Active alerts needing action', icon: Bell, tone: 'red', badge: 'alerts' },
  { to: '/watchlist', label: 'Wanted List', hint: 'Vehicles being watched', icon: ShieldCheck, tone: 'purple' },
  { to: '/registry', label: 'Camera List', hint: 'All registered cameras', icon: ScrollText, tone: 'blue' },
  { to: '/system', label: 'System Status', hint: 'Health of all services', icon: Activity, tone: 'amber' },
  { to: '/profile', label: 'Profile', hint: 'Your details & challans', icon: UserRound, tone: 'blue' },
];

/**
 * The core workflow, in exact investigation order. These five cards are
 * the primary navigation of the whole application:
 * Video Analysis → Live Cameras → Find Vehicle → Map → Vehicle Log.
 */
const PRIMARY: TopNavItem[] = [
  { to: '/video-analysis', label: 'Video Analysis', hint: 'Upload and analyse CCTV or video files', icon: Video, tone: 'blue' },
  { to: '/cameras', label: 'Live Cameras', hint: 'Watch live CCTV feeds', icon: Cctv, tone: 'green' },
  { to: '/vehicles', label: 'Find Vehicle', hint: 'Search by number plate', icon: Car, tone: 'sky' },
  { to: '/gis', label: 'Map', hint: 'Cameras & vehicles on the map', icon: Map, tone: 'orange' },
  { to: '/events', label: 'Vehicle Log', hint: 'Full vehicle history', icon: ListTree, tone: 'purple' },
];

/**
 * Per-card colour: soft gradient body, glossy matching arrow button,
 * coloured title when active. Idle cards lift on hover.
 */
const CARD_TONES: Record<TileTone, { idle: string; active: string; arrow: string; title: string }> = {
  blue: {
    idle: 'border-blue-200 bg-gradient-to-br from-blue-100/80 via-blue-50 to-white hover:-translate-y-0.5 hover:border-blue-400 hover:shadow-cardHover',
    active: 'border-blue-500 bg-gradient-to-br from-blue-200/70 via-blue-100 to-blue-50 shadow-cardHover',
    arrow: 'bg-gradient-to-br from-blue-500 to-blue-700',
    title: 'text-blue-700',
  },
  sky: {
    idle: 'border-sky-200 bg-gradient-to-br from-sky-100/80 via-sky-50 to-white hover:-translate-y-0.5 hover:border-sky-400 hover:shadow-cardHover',
    active: 'border-sky-500 bg-gradient-to-br from-sky-200/70 via-sky-100 to-sky-50 shadow-cardHover',
    arrow: 'bg-gradient-to-br from-sky-500 to-sky-700',
    title: 'text-sky-700',
  },
  green: {
    idle: 'border-emerald-200 bg-gradient-to-br from-emerald-100/80 via-emerald-50 to-white hover:-translate-y-0.5 hover:border-emerald-400 hover:shadow-cardHover',
    active: 'border-emerald-500 bg-gradient-to-br from-emerald-200/70 via-emerald-100 to-emerald-50 shadow-cardHover',
    arrow: 'bg-gradient-to-br from-emerald-500 to-emerald-700',
    title: 'text-emerald-700',
  },
  orange: {
    idle: 'border-orange-200 bg-gradient-to-br from-orange-100/80 via-orange-50 to-white hover:-translate-y-0.5 hover:border-orange-400 hover:shadow-cardHover',
    active: 'border-orange-500 bg-gradient-to-br from-orange-200/70 via-orange-100 to-orange-50 shadow-cardHover',
    arrow: 'bg-gradient-to-br from-orange-500 to-orange-700',
    title: 'text-orange-700',
  },
  amber: {
    idle: 'border-amber-200 bg-gradient-to-br from-amber-100/80 via-amber-50 to-white hover:-translate-y-0.5 hover:border-amber-400 hover:shadow-cardHover',
    active: 'border-amber-500 bg-gradient-to-br from-amber-200/70 via-amber-100 to-amber-50 shadow-cardHover',
    arrow: 'bg-gradient-to-br from-amber-500 to-amber-700',
    title: 'text-amber-700',
  },
  purple: {
    idle: 'border-violet-200 bg-gradient-to-br from-violet-100/80 via-violet-50 to-white hover:-translate-y-0.5 hover:border-violet-400 hover:shadow-cardHover',
    active: 'border-violet-500 bg-gradient-to-br from-violet-200/70 via-violet-100 to-violet-50 shadow-cardHover',
    arrow: 'bg-gradient-to-br from-violet-500 to-violet-700',
    title: 'text-violet-700',
  },
  red: {
    idle: 'border-rose-200 bg-gradient-to-br from-rose-100/80 via-rose-50 to-white hover:-translate-y-0.5 hover:border-rose-400 hover:shadow-cardHover',
    active: 'border-rose-500 bg-gradient-to-br from-rose-200/70 via-rose-100 to-rose-50 shadow-cardHover',
    arrow: 'bg-gradient-to-br from-rose-500 to-rose-700',
    title: 'text-rose-700',
  },
  slate: {
    idle: 'border-slate-200 bg-gradient-to-br from-slate-100/80 via-slate-50 to-white hover:-translate-y-0.5 hover:border-slate-400 hover:shadow-cardHover',
    active: 'border-slate-500 bg-gradient-to-br from-slate-200/70 via-slate-100 to-slate-50 shadow-cardHover',
    arrow: 'bg-gradient-to-br from-slate-500 to-slate-700',
    title: 'text-slate-700',
  },
};

export function TopNav() {
  const { counts } = useAlerts();

  return (
    <nav aria-label="Primary" className="sticky top-14 z-10 shrink-0 border-b border-line bg-surface-0">
      {/* Secondary sections — slim links at the top of the bar. */}
      <ul
        aria-label="Secondary"
        className="no-scrollbar flex items-center gap-1 overflow-x-auto border-b border-line bg-surface-1 px-3 py-1.5 sm:px-5"
      >
        {SECONDARY.map((item) => {
          const Icon = item.icon;
          const badgeCount = item.badge === 'alerts' ? counts.ACTIVE : 0;
          return (
            <li key={item.to} className="shrink-0">
              <NavLink
                to={item.to}
                end={item.end}
                title={`${item.label} — ${item.hint}`}
                className={({ isActive }) =>
                  cn(
                    'flex items-center gap-1.5 whitespace-nowrap rounded-md px-2.5 py-1.5 text-2xs font-semibold transition-colors',
                    isActive ? 'bg-brand/10 text-brand' : 'text-ink-muted hover:bg-surface-2 hover:text-ink',
                  )
                }
              >
                <Icon size={14} aria-hidden />
                {item.label}
                {badgeCount > 0 && (
                  <span
                    className="grid h-4 min-w-4 place-items-center rounded-full bg-critical px-1 font-mono text-[10px] font-bold text-white"
                    aria-label={`${badgeCount} active alerts`}
                  >
                    {badgeCount}
                  </span>
                )}
              </NavLink>
            </li>
          );
        })}
      </ul>

      {/* Primary workflow cards — all five fit a single screen row. */}
      <ul className="no-scrollbar mx-auto flex max-w-[1600px] gap-2.5 overflow-x-auto px-3 py-2.5 sm:px-5">
        {PRIMARY.map((item) => {
          const Icon = item.icon;
          const tone = CARD_TONES[item.tone];
          return (
            <li key={item.to} className="min-w-[215px] flex-1">
              <NavLink
                to={item.to}
                end={item.end}
                title={`${item.label} — ${item.hint}`}
                className={({ isActive }) =>
                  cn(
                    'group flex w-full items-center gap-3 rounded-xl border p-3 shadow-panel transition-all duration-150',
                    isActive ? tone.active : tone.idle,
                  )
                }
              >
                {({ isActive }) => (
                  <>
                    <IconTile
                      tone={item.tone}
                      size="lg"
                      active={isActive}
                      className="shadow-sm ring-1 ring-inset ring-black/5"
                    >
                      <Icon size={20} />
                    </IconTile>
                    <span className="min-w-0 flex-1">
                      <span
                        className={cn(
                          'block truncate text-sm font-bold leading-tight',
                          isActive ? tone.title : 'text-ink',
                        )}
                      >
                        {item.label}
                      </span>
                      <span className="mt-0.5 block min-h-8 overflow-hidden text-2xs leading-snug text-ink-muted [-webkit-box-orient:vertical] [-webkit-line-clamp:2] [display:-webkit-box]">
                        {item.hint}
                      </span>
                    </span>
                    <span
                      className={cn(
                        'grid h-8 w-8 shrink-0 place-items-center rounded-full text-white shadow-sm transition-transform duration-150 group-hover:scale-110',
                        tone.arrow,
                      )}
                      aria-hidden
                    >
                      <ChevronRight size={16} />
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
