import { useId, useState, type FormEvent } from 'react';
import { Search, Loader2 } from 'lucide-react';
import { cn, normalisePlate } from '@/lib/utils';
import { config } from '@/lib/config';

const SUGGESTIONS = ['GJ01AB1234', 'GJ05XY4321', 'GJ18MH0099'];

/**
 * The hero entry point: registration number → full investigation.
 * Used on the Command Center and on the Vehicles screen.
 */
export function TraceSearchBar({
  initialValue = '',
  onTrace,
  loading = false,
  size = 'md',
  showSuggestions = true,
  className,
}: {
  initialValue?: string;
  onTrace: (plate: string) => void;
  loading?: boolean;
  size?: 'md' | 'lg';
  showSuggestions?: boolean;
  className?: string;
}) {
  const [value, setValue] = useState(initialValue);
  const inputId = useId();

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const p = normalisePlate(value);
    if (p) onTrace(p);
  };

  const big = size === 'lg';

  return (
    <form onSubmit={submit} className={cn('w-full', className)} role="search" aria-label="Find a vehicle">
      <div className="flex flex-wrap items-center gap-2.5">
        <div className="relative min-w-[220px] flex-1">
          <label htmlFor={inputId} className="sr-only">
            Number plate
          </label>
          <Search
            size={big ? 17 : 15}
            className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-ink-faint"
            aria-hidden
          />
          <input
            id={inputId}
            value={value}
            onChange={(e) => setValue(e.target.value.toUpperCase())}
            placeholder="Type a number plate, e.g. GJ01AB1234"
            autoComplete="off"
            spellCheck={false}
            className={cn(
              'input plate pl-10 uppercase tracking-widest',
              big ? 'h-12 text-lg' : 'h-10 text-sm',
            )}
          />
        </div>
        <button
          type="submit"
          className={cn('btn-solid shrink-0', big ? 'h-12 px-6 text-sm' : 'h-10 px-5 text-sm')}
          disabled={loading}
        >
          {loading ? <Loader2 size={15} className="animate-spin" aria-hidden /> : <Search size={15} aria-hidden />}
          {loading ? 'Searching…' : 'Search'}
        </button>
      </div>

      {showSuggestions && (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <span className="text-xs text-ink-faint">Try these demo plates:</span>
          {SUGGESTIONS.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => {
                setValue(s);
                onTrace(s);
              }}
              className={cn(
                'chip border-line bg-surface-2 font-mono text-ink-muted hover:border-brand/50 hover:text-brand',
                s === config.demo.primaryPlate && 'border-brand/40 text-brand',
              )}
            >
              {s}
            </button>
          ))}
        </div>
      )}
    </form>
  );
}
