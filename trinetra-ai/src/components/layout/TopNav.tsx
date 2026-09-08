import { NavLink } from 'react-router-dom';
import {
  Activity,
  Bell,
  Car,
  Cctv,
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
  /** Full description shown as a tooltip on hover. */
  hint: string;
  icon: typeof LayoutDashboard;
  tone: TileTone;
  badge?: 'alerts';
  end?: boolean;
}

/**
 * Every module in the product, always visible in one row under the header.
 * Nothing is hidden inside a collapsed menu — on narrow screens the row
 * scrolls sideways instead.
 */
const ITEMS: TopNavItem[] = [
  { to: '/video-analysis', label: 'Video Analysis', hint: 'Upload and analyse CCTV or video files', icon: Video, tone: 'blue' },
  { to: '/cameras', label: 'Live Cameras', hint: 'Watch live feeds', icon: Cctv, tone: 'green' },
  { to: '/vehicles', label: 'Find Vehicle', hint: 'Search by number plate', icon: Car, tone: 'sky' },
  { to: '/gis', label: 'Map', hint: 'Cameras & vehicles on the map', icon: Map, tone: 'orange' },
  { to: '/events', label: 'Vehicle Log', hint: 'Vehicle history', icon: ListTree, tone: 'green' },
  { to: '/', label: 'Dashboard', hint: 'Overview & statistics', icon: LayoutDashboard, tone: 'blue', end: true },
  { to: '/alerts', label: 'Alerts', hint: 'Active alerts', icon: Bell, tone: 'red', badge: 'alerts' },
  { to: '/watchlist', label: 'Wanted List', hint: 'Vehicles being watched', icon: ShieldCheck, tone: 'purple' },
  { to: '/registry', label: 'Camera List', hint: 'All cameras', icon: ScrollText, tone: 'blue' },
  { to: '/system', label: 'System Status', hint: 'System health', icon: Activity, tone: 'amber' },
  { to: '/profile', label: 'Profile', hint: 'Your details & challans', icon: UserRound, tone: 'blue' },
];

export function TopNav() {
  const { counts } = useAlerts();

  return (
    <nav
      aria-label="Primary"
      className="sticky top-14 z-10 shrink-0 border-b border-line bg-surface-1"
    >
      <ul className="no-scrollbar mx-auto flex max-w-[1600px] items-stretch gap-0.5 overflow-x-auto px-2 sm:px-4">
        {ITEMS.map((item) => {
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
                    'relative flex min-w-[92px] flex-col items-center gap-1 px-3 pb-2 pt-2.5 transition-colors',
                    isActive ? 'text-brand' : 'text-ink-muted hover:bg-surface-2 hover:text-ink',
                  )
                }
              >
                {({ isActive }) => (
                  <>
                    <span className="relative">
                      <IconTile tone={item.tone} size="md" active={isActive}>
                        <Icon size={17} />
                      </IconTile>
                      {badgeCount > 0 && (
                        <span
                          className="absolute -right-1.5 -top-1.5 grid h-5 min-w-5 place-items-center rounded-full bg-critical px-1 font-mono text-2xs font-bold text-white"
                          aria-label={`${badgeCount} active alerts`}
                        >
                          {badgeCount}
                        </span>
                      )}
                    </span>
                    <span className="whitespace-nowrap text-2xs font-semibold leading-tight">
                      {item.label}
                    </span>
                    <span
                      className={cn(
                        'absolute inset-x-2 bottom-0 h-0.5 rounded-full bg-brand transition-opacity',
                        isActive ? 'opacity-100' : 'opacity-0',
                      )}
                      aria-hidden
                    />
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
