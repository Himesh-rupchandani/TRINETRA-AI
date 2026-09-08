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
  icon: typeof LayoutDashboard;
  badge?: 'alerts';
  end?: boolean;
}

const NAV: { section: string; items: NavItem[] }[] = [
  {
    section: 'Operations',
    items: [
      { to: '/', label: 'Command Center', icon: LayoutDashboard, end: true },
      { to: '/cameras', label: 'Live Cameras', icon: Cctv },
      { to: '/vehicles', label: 'Find a Vehicle', icon: Car },
      { to: '/gis', label: 'City Map', icon: Map },
      { to: '/video-analysis', label: 'Video Analysis', icon: ScanSearch },
    ],
  },
  {
    section: 'Intelligence',
    items: [
      { to: '/alerts', label: 'Alerts', icon: Bell, badge: 'alerts' },
      { to: '/events', label: 'Vehicle Log', icon: ListTree },
      { to: '/watchlist', label: 'Wanted List', icon: ShieldCheck },
    ],
  },
  {
    section: 'Administration',
    items: [
      { to: '/registry', label: 'Camera Registry', icon: ScrollText },
      { to: '/system', label: 'System Status', icon: Activity },
      { to: '/profile', label: 'Officer Profile', icon: UserRound },
    ],
  },
];

/** Product mark — flat green seal, no gradients, no glow. */
export function BrandMark({ size = 'md' }: { size?: 'md' | 'lg' }) {
  const box = size === 'lg' ? 'h-10 w-10 rounded-[10px]' : 'h-9 w-9 rounded-lg';
  return (
    <span className={cn('grid shrink-0 place-items-center bg-accent text-white', box)} aria-hidden>
      <svg viewBox="0 0 24 24" className={size === 'lg' ? 'h-5 w-5' : 'h-[18px] w-[18px]'} fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 3 3 7.5v4.2c0 5 3.8 8.6 9 9.3 5.2-.7 9-4.3 9-9.3V7.5L12 3Z" />
        <circle cx="12" cy="11" r="2.5" />
      </svg>
    </span>
  );
}

/** Primary navigation — white rail, quiet rows, accent edge on the active item. */
export function SideNav({
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
        <div className="fixed inset-0 z-30 bg-ink/40 lg:hidden" onClick={onClose} aria-hidden />
      )}
      <aside
        className={cn(
          'fixed inset-y-0 left-0 z-40 flex w-[248px] flex-col border-r border-line bg-surface-1 transition-[width,transform] duration-200',
          collapsed && 'w-[68px]',
          open ? 'translate-x-0' : '-translate-x-full lg:translate-x-0',
        )}
        aria-label="Primary navigation"
      >
        {/* Brand */}
        <div className={cn('flex h-14 shrink-0 items-center gap-2.5 border-b border-line px-4', collapsed && 'justify-center px-0')}>
          <BrandMark />
          {!collapsed && (
            <div className="min-w-0">
              <p className="truncate text-[15px] font-bold leading-tight tracking-[0.12em] text-ink">SENTINEL</p>
              <p className="truncate text-[10px] font-semibold uppercase tracking-[0.14em] text-ink-faint">
                TRINETRA AI
              </p>
            </div>
          )}
          {!collapsed && (
            <button
              type="button"
              className="ml-auto rounded-md p-1.5 text-ink-faint transition-colors hover:bg-surface-2 hover:text-ink lg:hidden"
              onClick={onClose}
              aria-label="Close navigation"
            >
              <X size={15} aria-hidden />
            </button>
          )}
        </div>

        {/* Nav */}
        <nav className="flex-1 overflow-y-auto px-2.5 py-5">
          {NAV.map((group) => (
            <div key={group.section} className="mb-6 last:mb-0">
              {!collapsed && (
                <p className="px-2.5 pb-2 text-[10.5px] font-semibold uppercase tracking-[0.12em] text-ink-faint">
                  {group.section}
                </p>
              )}
              <ul className="space-y-0.5">
                {group.items.map((item) => {
                  const Icon = item.icon;
                  const badgeCount = item.badge === 'alerts' ? counts.ACTIVE : 0;
                  return (
                    <li key={item.to}>
                      <NavLink
                        to={item.to}
                        end={item.end}
                        onClick={onClose}
                        title={collapsed ? item.label : undefined}
                        className={({ isActive }) =>
                          cn(
                            'group relative flex h-9 items-center gap-2.5 rounded-lg px-2.5 text-[13px] font-medium',
                            'transition-colors duration-150 active:scale-[0.99]',
                            collapsed && 'justify-center px-0',
                            isActive
                              ? 'bg-accent-weak font-semibold text-accent-strong'
                              : 'text-ink-muted hover:bg-surface-2 hover:text-ink',
                          )
                        }
                      >
                        {({ isActive }) => (
                          <>
                            <span
                              aria-hidden
                              className={cn(
                                'absolute left-0 top-1/2 h-4 w-[3px] -translate-y-1/2 rounded-r-full bg-accent transition-opacity duration-150',
                                isActive ? 'opacity-100' : 'opacity-0',
                              )}
                            />
                            <Icon size={16} className={cn('shrink-0', collapsed && 'mx-auto')} aria-hidden />
                            {!collapsed && <span className="truncate">{item.label}</span>}
                            {!collapsed && badgeCount > 0 && (
                              <span
                                className="mono ml-auto rounded-full bg-critical/10 px-1.5 text-[11px] font-semibold leading-[18px] text-critical"
                                aria-label={`${badgeCount} active alerts`}
                              >
                                {badgeCount}
                              </span>
                            )}
                            {collapsed && badgeCount > 0 && (
                              <span
                                className="absolute right-2 top-1.5 h-1.5 w-1.5 rounded-full bg-critical"
                                aria-label={`${badgeCount} active alerts`}
                              />
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

        {/* Officer */}
        <div className={cn('border-t border-line p-2.5', collapsed && 'px-1.5')}>
          <button
            type="button"
            onClick={() => {
              onClose();
              navigate('/profile');
            }}
            className={cn(
              'flex w-full items-center gap-2.5 rounded-lg p-2 text-left transition-colors duration-150 hover:bg-surface-2 active:scale-[0.99]',
              collapsed && 'justify-center p-0',
            )}
            aria-label="Open officer profile"
          >
            <span className="relative shrink-0">
              {officer ? (
                <img src={officer.photoUrl} alt="" className="h-8 w-8 rounded-full object-cover" aria-hidden />
              ) : (
                <span className="grid h-8 w-8 place-items-center rounded-full bg-surface-3 text-ink-muted" aria-hidden>
                  <UserRound size={14} />
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
