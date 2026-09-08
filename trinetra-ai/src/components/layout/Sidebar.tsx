import { NavLink, useNavigate } from 'react-router-dom';
import {
  Activity,
  Bell,
  Car,
  Cctv,
  LayoutDashboard,
  ListTree,
  Map,
  ScanSearch,
  ScrollText,
  ShieldCheck,
  UserRound,
  X,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { useAlerts } from '@/hooks/useAlerts';
import { useOfficer } from '@/features/officer/OfficerProvider';

interface NavItem {
  to: string;
  label: string;
  /** One line explaining what the page is for, shown under the label. */
  hint: string;
  icon: typeof LayoutDashboard;
  badge?: 'alerts';
  end?: boolean;
}

const NAV: { section: string; items: NavItem[] }[] = [
  {
    section: 'Operations',
    items: [
      { to: '/', label: 'Command Center', hint: 'Network overview', icon: LayoutDashboard, end: true },
      { to: '/cameras', label: 'Live Cameras', hint: 'Watch live feeds', icon: Cctv },
      { to: '/vehicles', label: 'Find a Vehicle', hint: 'Search by number plate', icon: Car },
      { to: '/gis', label: 'Map', hint: 'Cameras & vehicle routes', icon: Map },
      { to: '/video-analysis', label: 'Video Analysis', hint: 'Compare multiple videos', icon: ScanSearch },
    ],
  },
  {
    section: 'Intelligence',
    items: [
      { to: '/alerts', label: 'Alerts', hint: 'Active alerts', icon: Bell, badge: 'alerts' },
      { to: '/events', label: 'Vehicle Log', hint: 'Detection history', icon: ListTree },
      { to: '/watchlist', label: 'Wanted List', hint: 'Vehicles being watched', icon: ShieldCheck },
    ],
  },
  {
    section: 'Administration',
    items: [
      { to: '/registry', label: 'Camera List', hint: 'All cameras', icon: ScrollText },
      { to: '/system', label: 'System Status', hint: 'Service health', icon: Activity },
      { to: '/profile', label: 'Profile', hint: 'Your details & challans', icon: UserRound },
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
  const { current: officer } = useOfficer();
  const navigate = useNavigate();

  return (
    <>
      {open && (
        <div
          className="fixed inset-0 z-30 bg-black/60 lg:hidden"
          onClick={onClose}
          aria-hidden
        />
      )}
      <aside
        className={cn(
          'fixed inset-y-0 left-0 z-40 flex w-[264px] flex-col border-r border-line bg-surface-1 transition-[width,transform] duration-200',
          collapsed && 'w-[76px]',
          open ? 'translate-x-0' : '-translate-x-full lg:translate-x-0',
        )}
        aria-label="Primary navigation"
      >
        {/* Brand block — SENTINEL is the platform, TRINETRA AI the team behind it */}
        <div className="flex h-16 shrink-0 items-center gap-3 border-b border-line px-5">
          <span
            className="grid h-9 w-9 shrink-0 place-items-center rounded-lg border border-line-strong bg-surface-2"
            aria-hidden
          >
            <svg viewBox="0 0 24 24" className="h-[18px] w-[18px] text-brand" fill="none" stroke="currentColor" strokeWidth="1.7">
              <path d="M12 3 3 7.5v4.2c0 5 3.8 8.6 9 9.3 5.2-.7 9-4.3 9-9.3V7.5L12 3Z" />
              <circle cx="12" cy="11" r="2.5" />
            </svg>
          </span>
          {!collapsed && (
            <div className="min-w-0">
              <p className="truncate text-[15px] font-semibold leading-tight tracking-[0.14em] text-ink">
                SENTINEL
              </p>
              <p className="mt-0.5 truncate text-[11px] leading-tight text-ink-faint">
                by TRINETRA AI
              </p>
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

        <nav className="flex-1 overflow-y-auto px-3 py-6">
          {NAV.map((group) => (
            <div key={group.section} className="mb-7 last:mb-0">
              {!collapsed && (
                <p className="eyebrow px-3 pb-2.5">{group.section}</p>
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
                            'group relative flex items-center gap-3 rounded-lg px-3 py-2.5 transition duration-150 active:scale-[0.98]',
                            isActive
                              ? 'bg-surface-2 text-ink'
                              : 'text-ink-muted hover:bg-surface-2/60 hover:text-ink',
                          )
                        }
                      >
                        {({ isActive }) => (
                          <>
                            <span
                              aria-hidden
                              className={cn(
                                'absolute left-0 top-1/2 h-4 w-[2px] -translate-y-1/2 rounded-full bg-brand transition-opacity',
                                isActive ? 'opacity-100' : 'opacity-0',
                              )}
                            />
                            <Icon
                              size={17}
                              className={cn(
                                'shrink-0 transition-colors',
                                isActive ? 'text-brand' : 'text-ink-faint group-hover:text-ink-muted',
                              )}
                              aria-hidden
                            />
                            {!collapsed && (
                              <span className="min-w-0 flex-1">
                                <span
                                  className={cn(
                                    'block truncate text-sm font-medium leading-tight',
                                    isActive ? 'text-ink' : 'text-ink-muted group-hover:text-ink',
                                  )}
                                >
                                  {item.label}
                                </span>
                                <span className="mt-0.5 block truncate text-[11px] font-normal leading-tight text-ink-faint">
                                  {item.hint}
                                </span>
                              </span>
                            )}
                            {badgeCount > 0 && (
                              <span
                                className={cn(
                                  'ml-auto grid h-5 min-w-5 place-items-center rounded-full bg-critical/15 px-1.5 font-mono text-[11px] font-semibold text-critical',
                                  collapsed && 'absolute right-1 top-1 ml-0 h-4 min-w-4',
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

        {/* Operator card */}
        <div className="border-t border-line p-3">
          <button
            type="button"
            onClick={() => {
              onClose();
              navigate('/profile');
            }}
            className="flex w-full items-center gap-3 rounded-lg p-2.5 text-left transition duration-150 hover:bg-surface-2/60 active:scale-[0.99]"
            aria-label="Open officer profile"
          >
            <span className="relative shrink-0">
              {officer ? (
                <img
                  src={officer.photoUrl}
                  alt=""
                  className="h-9 w-9 rounded-full object-cover"
                  aria-hidden
                />
              ) : (
                <span className="grid h-9 w-9 place-items-center rounded-full bg-surface-2 text-ink-muted" aria-hidden>
                  <UserRound size={16} />
                </span>
              )}
              <span
                className="absolute -bottom-px -right-px h-2.5 w-2.5 rounded-full border-2 border-surface-1 bg-online"
                title="On duty"
                aria-hidden
              />
            </span>
            {!collapsed && (
              <span className="min-w-0 flex-1">
                <span className="block truncate text-xs font-semibold text-ink">
                  {officer?.name ?? 'System Operator'}
                </span>
                <span className="block truncate text-[11px] text-ink-faint">
                  {officer?.designation ?? 'Control Center'}
                </span>
              </span>
            )}
          </button>
        </div>
      </aside>
    </>
  );
}
