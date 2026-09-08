import { useNavigate } from 'react-router-dom';
import { useEffect, useState } from 'react';
import {
  Bell,
  Menu,
  PanelLeftClose,
  PanelLeftOpen,
  Search,
  UserRound,
} from 'lucide-react';
import { cn, normalisePlate } from '@/lib/utils';
import { useAlerts } from '@/hooks/useAlerts';
import { useLiveEvents } from '@/hooks/useLiveEvents';
import { config } from '@/lib/config';
import { useOfficer } from '@/features/officer/OfficerProvider';

const CONNECTION_LABEL: Record<string, string> = {
  LIVE: 'Live feed',
  SIMULATED: 'Demo feed',
  CONNECTING: 'Connecting',
  OFFLINE: 'Offline',
};

const CONNECTION_TONE: Record<string, string> = {
  LIVE: 'text-online',
  SIMULATED: 'text-critical',
  CONNECTING: 'text-degraded',
  OFFLINE: 'text-offline',
};

/** Operations clock — control rooms always run on a visible wallclock (IST). */
function useOpsClock() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);
  return new Intl.DateTimeFormat('en-GB', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
    timeZone: 'Asia/Kolkata',
  }).format(now);
}

export function Header({
  onMenu,
  onToggleCollapse,
  collapsed,
}: {
  onMenu: () => void;
  onToggleCollapse: () => void;
  collapsed: boolean;
}) {
  const navigate = useNavigate();
  const { counts } = useAlerts();
  const { connection } = useLiveEvents();
  const { current: officer } = useOfficer();
  const [quick, setQuick] = useState('');
  const clock = useOpsClock();

  const submitQuick = (e: React.FormEvent) => {
    e.preventDefault();
    const p = normalisePlate(quick);
    if (p) navigate(`/vehicles/${p}`);
  };

  return (
    <header className="sticky top-0 z-20 flex h-16 shrink-0 items-center gap-3 border-b border-line bg-surface-0/85 px-4 backdrop-blur-md sm:px-6">
      <button type="button" className="btn-ghost h-10 w-10 px-0 lg:hidden" onClick={onMenu} aria-label="Open navigation">
        <Menu size={17} aria-hidden />
      </button>
      <button
        type="button"
        className="btn-ghost hidden h-10 w-10 px-0 lg:inline-flex"
        onClick={onToggleCollapse}
        aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
      >
        {collapsed ? <PanelLeftOpen size={16} aria-hidden /> : <PanelLeftClose size={16} aria-hidden />}
      </button>

      <div className="min-w-0 lg:hidden">
        <p className="truncate text-sm font-semibold leading-tight tracking-[0.12em] text-ink">
          {config.productName}
        </p>
        <p className="hidden truncate text-[11px] leading-tight text-ink-faint sm:block">
          by {config.appName}
        </p>
      </div>

      {/* Global plate search — the hero entry point, reachable from every screen */}
      <div className="hidden min-w-0 flex-1 justify-center px-2 md:flex">
        <form onSubmit={submitQuick} className="w-full max-w-xl" role="search">
          <label htmlFor="global-plate-search" className="sr-only">
            Trace registration number
          </label>
          <div className="relative">
            <Search size={15} className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-ink-faint" aria-hidden />
            <input
              id="global-plate-search"
              value={quick}
              onChange={(e) => setQuick(e.target.value.toUpperCase())}
              placeholder="Search a number plate, e.g. GJ01AB1234"
              className="input h-10 pl-10 font-mono uppercase"
              autoComplete="off"
              spellCheck={false}
            />
          </div>
        </form>
      </div>

      <div className="ml-auto flex items-center gap-2 sm:gap-3">
        {/* Operations clock — IST wallclock, standard in control rooms */}
        <span
          className="hidden items-center gap-2 rounded-lg border border-line px-3 py-1.5 font-mono text-xs tabular-nums text-ink-muted lg:inline-flex"
          title="Operations clock — Indian Standard Time"
        >
          {clock} <span className="text-[10px] font-semibold text-ink-faint">IST</span>
        </span>

        {config.useMocks && (
          <span className="chip hidden border-line bg-surface-2 text-ink-muted xl:inline-flex">
            Demo data
          </span>
        )}

        <span
          className={cn(
            'hidden items-center gap-2 text-2xs font-medium uppercase tracking-wide sm:inline-flex',
            CONNECTION_TONE[connection],
          )}
          title={`Realtime channel: ${connection}`}
        >
          <span
            className={cn(
              'h-1.5 w-1.5 rounded-full bg-current',
              connection === 'LIVE' && 'animate-pulse-dot',
            )}
            aria-hidden
          />
          {CONNECTION_LABEL[connection]}
        </span>

        <button
          type="button"
          onClick={() => navigate('/alerts')}
          className="relative grid h-10 w-10 place-items-center rounded-lg text-ink-muted transition-colors hover:bg-surface-1 hover:text-ink"
          aria-label={`${counts.ACTIVE} alerts need your attention — open Alerts`}
        >
          <Bell size={17} aria-hidden />
          {counts.ACTIVE > 0 && (
            <span className="absolute right-1.5 top-1.5 h-2 w-2 rounded-full bg-critical ring-2 ring-surface-0" aria-hidden />
          )}
        </button>

        <button
          type="button"
          onClick={() => navigate('/profile')}
          className="hidden items-center gap-3 rounded-lg py-1 pl-4 pr-1 text-left transition-colors hover:bg-surface-1 xl:flex"
          aria-label="Open officer profile"
        >
          <span className="min-w-0">
            <span className="block max-w-[160px] truncate text-xs font-semibold text-ink">
              {officer?.name ?? 'System Operator'}
            </span>
            <span className="block text-[11px] text-ink-faint">
              {officer?.designation ?? 'Control Center'}
            </span>
          </span>
          {officer ? (
            <img src={officer.photoUrl} alt="" className="h-8 w-8 shrink-0 rounded-full object-cover" aria-hidden />
          ) : (
            <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-surface-2 text-ink-muted" aria-hidden>
              <UserRound size={14} />
            </span>
          )}
        </button>
      </div>
    </header>
  );
}
