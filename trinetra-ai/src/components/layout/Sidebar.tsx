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
import { IconTile, type TileTone } from '@/components/common/IconTile';
import { EyeMark } from '@/components/common/EyeMark';
import { cn } from '@/lib/utils';
import { useAlerts } from '@/hooks/useAlerts';
import { useOfficer } from '@/features/officer/OfficerProvider';

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
    section: 'Operations',
    items: [
      { to: '/', label: 'Dashboard', hint: 'Overview & statistics', icon: LayoutDashboard, tone: 'blue', end: true },
      { to: '/vehicles', label: 'Find a Vehicle', hint: 'Search by number plate', icon: Car, tone: 'sky' },
      { to: '/alerts', label: 'Alerts', hint: 'Active alerts', icon: Bell, tone: 'red', badge: 'alerts' },
      { to: '/cameras', label: 'Live Cameras', hint: 'Watch live feeds', icon: Cctv, tone: 'green' },
      { to: '/gis', label: 'Map', hint: 'Cameras & vehicles', icon: Map, tone: 'orange' },
      { to: '/video-analysis', label: 'Video Analysis', hint: 'Compare multiple videos', icon: ScanSearch, tone: 'purple' },
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
  const { current: officer } = useOfficer();
  const navigate = useNavigate();

  return (
    <>
      {open && (
        <div
          className="fixed inset-0 z-30 bg-black/60 backdrop-blur-[2px] lg:hidden"
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
        {/* Logo lockup — the third eye */}
        <div className="flex h-14 shrink-0 items-center gap-2.5 border-b border-line px-3.5">
          <span className="relative grid h-9 w-9 shrink-0 place-items-center" aria-hidden>
            <EyeMark size={36} />
          </span>
          {!collapsed && (
            <div className="min-w-0">
              <p className="truncate text-sm font-extrabold tracking-[0.02em] text-ink">TRINETRA AI</p>
              <p className="truncate text-[10px] font-medium uppercase tracking-[0.14em] text-brand/80">
                The third eye
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

        <nav className="flex-1 overflow-y-auto px-3 py-4">
          {NAV.map((group) => (
            <div key={group.section} className="mb-4">
              {!collapsed && <p className="section-label px-2 pb-2">{group.section}</p>}
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
                            'group relative flex items-center gap-2.5 rounded-lg px-2 py-2 transition-colors',
                            isActive
                              ? 'bg-brand/10'
                              : 'text-ink-muted hover:bg-surface-2 hover:text-ink',
                          )
                        }
                      >
                        {({ isActive }) => (
                          <>
                            {isActive && (
                              <span
                                className="absolute left-0 top-1/2 h-5 w-[2px] -translate-y-1/2 rounded-r bg-brand"
                                aria-hidden
                              />
                            )}
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
                                  'ml-auto grid h-5 min-w-5 place-items-center rounded-full bg-critical px-1 font-mono text-2xs font-bold text-[#16040B]',
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
          <div className="px-3 pb-3">
            <button
              type="button"
              onClick={() => {
                onClose();
                navigate('/profile');
              }}
              className="flex w-full items-center gap-2.5 rounded-lg border border-line bg-surface-2/60 p-2.5 text-left transition-colors hover:border-line-strong hover:bg-surface-2"
              aria-label="Open officer profile"
            >
              {officer ? (
                <img
                  src={officer.photoUrl}
                  alt=""
                  className="h-9 w-9 shrink-0 rounded-full object-cover ring-1 ring-line-strong"
                  aria-hidden
                />
              ) : (
                <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-brand/10 text-brand" aria-hidden>
                  <UserRound size={16} />
                </span>
              )}
              <div className="min-w-0 flex-1">
                <p className="truncate text-xs font-semibold text-ink">{officer?.name ?? 'System Operator'}</p>
                <p className="truncate text-2xs text-ink-faint">{officer?.designation ?? 'Control Center'}</p>
              </div>
              <span className="chip border-online/30 bg-online/10 text-online">
                <span className="h-1.5 w-1.5 rounded-full bg-online" aria-hidden />
                Online
              </span>
            </button>
          </div>
        )}

        {/* Persistent brand badge — every screenshot is on-brand. */}
        <div
          className={cn(
            'flex shrink-0 items-center gap-2 border-t border-line px-3.5 py-2.5',
            collapsed && 'justify-center px-0',
          )}
          title="Sentinel Hackathon · TRINETRA AI"
        >
          <EyeMark size={18} sweep={false} />
          {!collapsed && (
            <p className="text-[10px] font-semibold uppercase leading-tight tracking-[0.1em] text-ink-faint">
              Sentinel Hackathon
              <span className="px-1 text-ink-faint">·</span>
              <span className="text-ink-muted">TRINETRA AI</span>
            </p>
          )}
        </div>
      </aside>
    </>
  );
}
