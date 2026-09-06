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
  X,
} from 'lucide-react';
import { IconTile, type TileTone } from '@/components/common/IconTile';
import { cn } from '@/lib/utils';
import { useAlerts } from '@/hooks/useAlerts';

interface NavItem {
  to: string;
  label: string;
  /** One line explaining what the page is for, shown under the label. */
  hint: string;
  icon: typeof LayoutDashboard;
  tone: TileTone;
  badge?: 'alerts';
  end?: boolean;
}

const NAV: { section: string; items: NavItem[] }[] = [
  {
    section: 'Main',
    items: [
      { to: '/', label: 'Dashboard', hint: 'Overview & statistics', icon: LayoutDashboard, tone: 'blue', end: true },
      { to: '/vehicles', label: 'Find a Vehicle', hint: 'Search by number plate', icon: Car, tone: 'sky' },
      { to: '/alerts', label: 'Alerts', hint: 'Active alerts', icon: Bell, tone: 'red', badge: 'alerts' },
      { to: '/cameras', label: 'Live Cameras', hint: 'Watch live feeds', icon: Cctv, tone: 'green' },
      { to: '/gis', label: 'Map', hint: 'Cameras & vehicles', icon: Map, tone: 'orange' },
      { to: '/events', label: 'Vehicle Log', hint: 'Vehicle history', icon: ListTree, tone: 'green' },
      { to: '/profile', label: 'Profile', hint: 'Your details & challans', icon: UserRound, tone: 'blue' },
    ],
  },
  {
    section: 'Records',
    items: [
      { to: '/watchlist', label: 'Wanted List', hint: 'Vehicles being watched', icon: ShieldCheck, tone: 'purple' },
      { to: '/registry', label: 'Camera List', hint: 'All cameras', icon: ScrollText, tone: 'blue' },
      { to: '/system', label: 'System Status', hint: 'System health', icon: Activity, tone: 'amber' },
    ],
  },
];

export function Sidebar({
  open,
  onClose,
  collapsed,
}: {
  open: boolean;
  onClose: () => void;
  collapsed: boolean;
}) {
  const { counts } = useAlerts();

  return (
    <>
      {open && (
        <div
          className="fixed inset-0 z-30 bg-black/50 lg:hidden"
          onClick={onClose}
          aria-hidden
        />
      )}
      <aside
        className={cn(
          'fixed inset-y-0 left-0 z-40 flex flex-col border-r border-line bg-surface-1 transition-[width,transform] duration-200',
          collapsed ? 'w-[72px]' : 'w-[240px]',
          open ? 'translate-x-0' : '-translate-x-full lg:translate-x-0',
        )}
        aria-label="Primary navigation"
      >
        <div className="flex h-14 shrink-0 items-center gap-2.5 border-b border-line px-3.5">
          <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-brand shadow-sm" aria-hidden>
            <svg viewBox="0 0 24 24" className="h-5 w-5 text-white" fill="none" stroke="currentColor" strokeWidth="1.8">
              <path d="M12 3 3 7.5v4.2c0 5 3.8 8.6 9 9.3 5.2-.7 9-4.3 9-9.3V7.5L12 3Z" />
              <circle cx="12" cy="11" r="2.6" />
            </svg>
          </span>
          {!collapsed && (
            <div className="min-w-0">
              <p className="truncate text-sm font-bold tracking-tight text-ink">TRINETRA AI</p>
              <p className="truncate text-2xs text-ink-faint">Intelligent Vision</p>
            </div>
          )}
          <button
            type="button"
            className="btn-ghost btn-xs ml-auto lg:hidden"
            onClick={onClose}
            aria-label="Close navigation"
          >
            <X size={13} aria-hidden />
          </button>
        </div>

        <nav className="flex-1 overflow-y-auto px-3 py-4">
          {NAV.map((group) => (
            <div key={group.section} className="mb-4">
              {!collapsed && (
                <p className="px-2 pb-2 text-2xs font-semibold uppercase tracking-[0.14em] text-ink-faint/80">
                  {group.section}
                </p>
              )}
              <ul className="space-y-1">
                {group.items.map((item) => {
                  const Icon = item.icon;
                  const badgeCount = item.badge === 'alerts' ? counts.ACTIVE : 0;
                  return (
                    <li key={item.to}>
                      <NavLink
                        to={item.to}
                        end={item.end}
                        onClick={onClose}
                        title={collapsed ? `${item.label} — ${item.hint}` : undefined}
                        className={({ isActive }) =>
                          cn(
                            'group relative flex items-center gap-2.5 rounded-xl px-2 py-2 transition-colors',
                            isActive
                              ? 'bg-brand/10'
                              : 'text-ink-muted hover:bg-surface-2 hover:text-ink',
                          )
                        }
                      >
                        {({ isActive }) => (
                          <>
                            <IconTile tone={item.tone} size="md" active={isActive}>
                              <Icon size={17} />
                            </IconTile>
                            {!collapsed && (
                              <span className="min-w-0 flex-1">
                                <span
                                  className={cn(
                                    'block truncate text-[13px] font-semibold leading-tight',
                                    isActive ? 'text-brand' : 'text-ink',
                                  )}
                                >
                                  {item.label}
                                </span>
                                <span className="block truncate text-2xs font-normal text-ink-faint">
                                  {item.hint}
                                </span>
                              </span>
                            )}
                            {badgeCount > 0 && (
                              <span
                                className={cn(
                                  'ml-auto grid h-5 min-w-5 place-items-center rounded-full bg-critical px-1 font-mono text-2xs font-bold text-white',
                                  collapsed && 'absolute right-0.5 top-0.5 ml-0 h-4 min-w-4',
                                )}
                                aria-label={`${badgeCount} active alerts`}
                              >
                                {badgeCount}
                              </span>
                            )}
                          </>
                        )}
                      </NavLink>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </nav>

        {!collapsed && (
          <div className="px-3 pb-4">
            <div className="flex items-center gap-2.5 rounded-xl border border-line bg-surface-2/70 p-3">
              <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-brand/10 text-brand" aria-hidden>
                <UserRound size={16} />
              </span>
              <div className="min-w-0 flex-1">
                <p className="truncate text-xs font-semibold text-ink">System Operator</p>
                <p className="truncate text-2xs text-ink-faint">Control Center</p>
              </div>
              <span className="chip border-online/30 bg-online/10 text-online">
                <span className="h-1.5 w-1.5 rounded-full bg-online" aria-hidden />
                Online
              </span>
            </div>
          </div>
        )}
      </aside>
    </>
  );
}
