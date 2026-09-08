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
 * Supporting sections. Deliberately smaller than the workflow cards above
 * so the eye goes to the investigation flow first.
 */
const SECONDARY: TopNavItem[] = [
  { to: '/', label: 'Dashboard', hint: 'Overview & statistics', icon: LayoutDashboard, tone: 'blue', end: true },
  { to: '/alerts', label: 'Alerts', hint: 'Active alerts needing action', icon: Bell, tone: 'red', badge: 'alerts' },
  { to: '/watchlist', label: 'Wanted List', hint: 'Vehicles being watched', icon: ShieldCheck, tone: 'purple' },
  { to: '/registry', label: 'Camera List', hint: 'All registered cameras', icon: ScrollText, tone: 'blue' },
  { to: '/system', label: 'System Status', hint: 'Health of all services', icon: Activity, tone: 'amber' },
  { to: '/profile', label: 'Profile', hint: 'Your details & challans', icon: UserRound, tone: 'blue' },
];

/** Per-card colour: tinted body, matching arrow button, active title. */
const CARD_TONES: Record<TileTone, { idle: string; active: string; arrow: string; title: string }> = {
  blue: {
    idle: 'border-blue-200 bg-blue-50 hover:border-blue-400',
    active: 'border-blue-500 bg-blue-100/80 shadow-cardHover',
    arrow: 'bg-blue-500',
    title: 'text-blue-700',
  },
  sky: {
    idle: 'border-sky-200 bg-sky-50 hover:border-sky-400',
    active: 'border-sky-500 bg-sky-100/80 shadow-cardHover',
    arrow: 'bg-sky-500',
    title: 'text-sky-700',
  },
  green: {
    idle: 'border-emerald-200 bg-emerald-50 hover:border-emerald-400',
    active: 'border-emerald-500 bg-emerald-100/80 shadow-cardHover',
    arrow: 'bg-emerald-500',
    title: 'text-emerald-700',
  },
  orange: {
    idle: 'border-orange-200 bg-orange-50 hover:border-orange-400',
    active: 'border-orange-500 bg-orange-100/80 shadow-cardHover',
    arrow: 'bg-orange-500',
    title: 'text-orange-700',
  },
  amber: {
    idle: 'border-amber-200 bg-amber-50 hover:border-amber-400',
    active: 'border-amber-500 bg-amber-100/80 shadow-cardHover',
    arrow: 'bg-amber-500',
    title: 'text-amber-700',
  },
  purple: {
    idle: 'border-violet-200 bg-violet-50 hover:border-violet-400',
    active: 'border-violet-500 bg-violet-100/80 shadow-cardHover',
    arrow: 'bg-violet-500',
    title: 'text-violet-700',
  },
  red: {
    idle: 'border-rose-200 bg-rose-50 hover:border-rose-400',
    active: 'border-rose-500 bg-rose-100/80 shadow-cardHover',
    arrow: 'bg-rose-500',
    title: 'text-rose-700',
  },
  slate: {
    idle: 'border-slate-200 bg-slate-50 hover:border-slate-400',
    active: 'border-slate-500 bg-slate-100/80 shadow-cardHover',
    arrow: 'bg-slate-500',
    title: 'text-slate-700',
  },
};

export function TopNav() {
  const { counts } = useAlerts();

  return (
    <nav aria-label="Primary" className="sticky top-14 z-10 shrink-0 border-b border-line bg-surface-0">
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
                    'flex w-full items-center gap-3 rounded-xl border p-3 shadow-panel transition-colors',
                    isActive ? tone.active : tone.idle,
                  )
                }
              >
                {({ isActive }) => (
                  <>
                    <IconTile tone={item.tone} size="lg" active={isActive}>
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
                        'grid h-8 w-8 shrink-0 place-items-center rounded-full text-white',
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

      {/* Secondary sections — compact links, clearly below the workflow */}
      <ul
        aria-label="Secondary"
        className="no-scrollbar flex items-center gap-1 overflow-x-auto border-t border-line bg-surface-1 px-3 py-1.5 sm:px-5"
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
    </nav>
  );
}
