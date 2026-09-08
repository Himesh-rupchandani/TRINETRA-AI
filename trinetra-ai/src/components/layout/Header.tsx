import { NavLink, useLocation, useNavigate } from 'react-router-dom';
import { useEffect, useRef, useState } from 'react';
import {
  Activity,
  ArrowLeft,
  Bell,
  LayoutDashboard,
  ScrollText,
  Search,
  ShieldCheck,
  UserRound,
} from 'lucide-react';
import { cn, normalisePlate } from '@/lib/utils';
import { useAlerts } from '@/hooks/useAlerts';
import { useLiveEvents } from '@/hooks/useLiveEvents';
import { config } from '@/lib/config';
import { useOfficer } from '@/features/officer/OfficerProvider';

const CONNECTION_TONE: Record<string, string> = {
  LIVE: 'text-online',
  SIMULATED: 'text-critical',
  CONNECTING: 'text-degraded',
  OFFLINE: 'text-offline',
};

interface HeaderLink {
  to: string;
  label: string;
  hint: string;
  icon: typeof LayoutDashboard;
  end?: boolean;
}

/**
 * Supporting sections on the right side of the top header bar.
 * (Alerts and Profile are covered by the bell and officer buttons,
 * so they are intentionally not repeated here.)
 */
const HEADER_LINKS: HeaderLink[] = [
  { to: '/', label: 'Dashboard', hint: 'Overview & statistics', icon: LayoutDashboard, end: true },
  { to: '/watchlist', label: 'Wanted List', hint: 'Vehicles being watched', icon: ShieldCheck },
  { to: '/registry', label: 'Camera List', hint: 'All registered cameras', icon: ScrollText },
  { to: '/system', label: 'System Status', hint: 'Health of all services', icon: Activity },
];

export function Header() {
  const navigate = useNavigate();
  const location = useLocation();
  const { counts } = useAlerts();
  const { connection } = useLiveEvents();
  const { current: officer } = useOfficer();
  const [quick, setQuick] = useState('');
  const searchRef = useRef<HTMLInputElement>(null);

  // Ctrl/⌘+K focuses the global search from anywhere.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        searchRef.current?.focus();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  /** Every screen except the home page gets a way back to it. */
  const showBack = location.pathname !== '/';

  const submitQuick = (e: React.FormEvent) => {
    e.preventDefault();
    const p = normalisePlate(quick);
    if (p) navigate(`/vehicles/${p}`);
  };

  return (
    <header className="sticky top-0 z-20 flex h-14 shrink-0 items-center gap-2.5 border-b border-line bg-surface-1 px-3.5 sm:gap-3 sm:px-5">
      {showBack && (
        <button
          type="button"
          className="btn-ghost group h-9 shrink-0 gap-1.5 px-2.5"
          onClick={() => navigate('/')}
          aria-label="Back to home page"
          title="Back to home page"
        >
          <ArrowLeft size={16} className="transition-transform group-hover:-translate-x-0.5" aria-hidden />
          <span className="hidden sm:inline">Back</span>
        </button>
      )}

      <button
        type="button"
        onClick={() => navigate('/')}
        className="flex min-w-0 shrink-0 items-center gap-2.5 rounded-lg px-1 py-1 text-left"
        aria-label="TRINETRA AI — go to home page"
        title="Go to home page"
      >
        <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl border border-line bg-white shadow-sm" aria-hidden>
          <svg viewBox="0 0 24 24" className="h-6 w-6" fill="none" stroke="#2563EB" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M2.5 12C5 7.6 8.2 5.2 12 5.2s7 2.4 9.5 6.8c-2.5 4.4-5.7 6.8-9.5 6.8s-7-2.4-9.5-6.8Z" />
            <circle cx="12" cy="12" r="2.9" stroke="#1D4ED8" />
            <circle cx="12" cy="12" r="1" fill="#2563EB" stroke="none" />
          </svg>
        </span>
        <span className="hidden min-w-0 md:block">
          <span className="block truncate text-sm font-bold leading-tight tracking-tight text-ink">
            {config.appName}
          </span>
          <span className="block truncate text-2xs leading-tight text-ink-faint">{config.tagline}</span>
        </span>
      </button>

      {/* Global plate search — always in the title bar, on every screen. */}
      <form onSubmit={submitQuick} className="hidden min-w-0 max-w-sm flex-1 sm:block" role="search">
        <label htmlFor="global-plate-search" className="sr-only">
          Trace registration number
        </label>
        <div className="relative">
          <Search size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-ink-faint" aria-hidden />
          <input
            id="global-plate-search"
            ref={searchRef}
            value={quick}
            onChange={(e) => setQuick(e.target.value.toUpperCase())}
            placeholder="Search number plate, camera, or location…"
            className="input h-10 pl-9 pr-16 font-mono uppercase"
            autoComplete="off"
            spellCheck={false}
          />
          <kbd className="pointer-events-none absolute right-2.5 top-1/2 hidden -translate-y-1/2 rounded border border-line bg-surface-2 px-1.5 py-0.5 font-mono text-[10px] font-semibold text-ink-faint lg:inline-block">
            Ctrl K
          </kbd>
        </div>
      </form>

      {/* Supporting sections on the right — icon buttons on smaller screens, full labels on wide ones. */}
      <nav aria-label="Secondary" className="ml-auto hidden min-w-0 shrink-0 items-center gap-0.5 md:flex">
        {HEADER_LINKS.map((item) => {
          const Icon = item.icon;
          return (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              title={`${item.label} — ${item.hint}`}
              className={({ isActive }) =>
                cn(
                  'flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-lg px-2 py-2 text-2xs font-semibold transition-colors',
                  isActive ? 'bg-brand/10 text-brand' : 'text-ink-muted hover:bg-surface-2 hover:text-ink',
                )
              }
            >
              <Icon size={15} aria-hidden />
              <span className="hidden min-[1400px]:inline">{item.label}</span>
            </NavLink>
          );
        })}
      </nav>

      <div className="flex shrink-0 items-center gap-2 sm:gap-3">
        {config.useMocks && (
          <span className="chip hidden border-brand/25 bg-brand/10 font-semibold text-brand min-[1500px]:inline-flex">
            Demo Data
          </span>
        )}

        <span
          className={cn(
            'hidden items-center gap-1.5 text-2xs font-bold uppercase tracking-wide sm:inline-flex',
            CONNECTION_TONE[connection],
          )}
          title={`Realtime channel: ${connection}`}
        >
          <span className={cn('h-2 w-2 rounded-full bg-current', connection === 'LIVE' && 'animate-pulse')} aria-hidden />
          {connection === 'SIMULATED'
            ? 'Demo Feed'
            : connection === 'LIVE'
              ? 'Live Feed'
              : connection === 'CONNECTING'
                ? 'Connecting'
                : 'Offline'}
        </span>

        <button
          type="button"
          onClick={() => navigate('/alerts')}
          className="relative grid h-9 w-9 place-items-center rounded-lg border border-line text-ink-muted transition-colors hover:bg-surface-2 hover:text-ink"
          aria-label={`${counts.ACTIVE} alerts need your attention — open Alerts`}
        >
          <Bell size={16} className={counts.ACTIVE > 0 ? 'animate-pulse text-critical' : ''} aria-hidden />
          {counts.ACTIVE > 0 && (
            <span className="absolute -right-1 -top-1 grid h-4 min-w-4 place-items-center rounded-full bg-critical px-1 font-mono text-[10px] font-bold text-white">
              {counts.ACTIVE}
            </span>
          )}
        </button>

        <button
          type="button"
          onClick={() => navigate('/profile')}
          className="flex items-center gap-2.5 border-l border-line pl-3 text-left"
          aria-label="Open officer profile"
        >
          {officer ? (
            <span className="relative shrink-0">
              <img
                src={officer.photoUrl}
                alt=""
                className="h-9 w-9 rounded-full object-cover ring-1 ring-line"
                aria-hidden
              />
              <span className="absolute -bottom-0.5 -right-0.5 h-3 w-3 rounded-full border-2 border-surface-1 bg-online" aria-hidden />
            </span>
          ) : (
            <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-brand/10 text-brand" aria-hidden>
              <UserRound size={16} />
            </span>
          )}
          <div className="hidden leading-tight sm:block">
            <p className="max-w-[160px] truncate text-xs font-semibold text-ink">{officer?.name ?? 'System Operator'}</p>
            <p className="text-2xs text-ink-faint">{officer?.designation ?? 'Control Center'}</p>
          </div>
        </button>
      </div>
    </header>
  );
}
