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
  { to: '/events', label: 'Vehicle Log', hint: 'Full vehicle history', icon: ListTree, tone: 'green' },
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

export function TopNav() {
  const { counts } = useAlerts();

  return (
    <nav aria-label="Primary" className="sticky top-14 z-10 shrink-0 border-b border-line bg-surface-0">
      {/* Primary workflow cards */}
      <ul className="no-scrollbar mx-auto flex max-w-[1600px] gap-2.5 overflow-x-auto px-3 py-2.5 sm:px-5">
        {PRIMARY.map((item, i) => {
          const Icon = item.icon;
          return (
            <li key={item.to} className="shrink-0">
              <NavLink
                to={item.to}
                end={item.end}
                title={`Step ${i + 1}: ${item.label} — ${item.hint}`}
                className={({ isActive }) =>
                  cn(
                    'flex w-[248px] items-center gap-3 rounded-xl border bg-surface-1 p-3 shadow-panel transition-colors',
                    isActive
                      ? 'border-brand/60 bg-brand/[0.05]'
                      : 'border-line hover:border-brand/40 hover:shadow-cardHover',
                  )
                }
              >
                {({ isActive }) => (
                  <>
                    <span className="relative shrink-0">
                      <IconTile tone={item.tone} size="lg" active={isActive}>
                        <Icon size={20} />
                      </IconTile>
                      <span
                        className="absolute -left-1.5 -top-1.5 grid h-5 w-5 place-items-center rounded-full bg-ink font-mono text-[10px] font-bold text-white"
                        aria-hidden
                      >
                        {i + 1}
                      </span>
                    </span>
                    <span className="min-w-0 flex-1">
                      <span
                        className={cn(
                          'block truncate text-sm font-bold leading-tight',
                          isActive ? 'text-brand' : 'text-ink',
                        )}
                      >
                        {item.label}
                      </span>
                      <span className="mt-0.5 block min-h-8 overflow-hidden text-2xs leading-snug text-ink-faint [display:-webkit-box] [-webkit-box-orient:vertical] [-webkit-line-clamp:2]">
                        {item.hint}
                      </span>
                    </span>
                    <span
                      className={cn(
                        'grid h-8 w-8 shrink-0 place-items-center rounded-full transition-colors',
                        isActive ? 'bg-brand text-white' : 'bg-brand/10 text-brand',
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
