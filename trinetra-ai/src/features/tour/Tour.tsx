import { useEffect, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { ChevronLeft, ChevronRight, GraduationCap, X } from 'lucide-react';
import { TOUR_STEPS } from './tourSteps';
import { tourStore, useTour } from './tourStore';
import { cn } from '@/lib/utils';

/**
 * Minimal spotlight walkthrough for first-time viewers (judges!).
 * Each step navigates to its route, waits for the target element
 * (pages lazy-mount, the map hydrates async), then draws a glowing cutout
 * over it with a compact card. No target ⇒ centred card (intro/outro).
 *
 * Keys: Enter/→ next · ← back · Esc exit · click anywhere advances.
 */

interface Rect {
  x: number;
  y: number;
  w: number;
  h: number;
}

const CARD_W = 360;
const CARD_H_EST = 224;
const GAP = 14;
const PAD = 10;

export function Tour() {
  const { open, i } = useTour();
  const step = TOUR_STEPS[i];
  const total = TOUR_STEPS.length;
  const navigate = useNavigate();
  const location = useLocation();
  const [rect, setRect] = useState<Rect | null>(null);
  const [ready, setReady] = useState(false);
  const firedActions = useRef<Set<string>>(new Set());
  const nextBtnRef = useRef<HTMLButtonElement>(null);

  // Fresh run ⇒ clear one-shot actions and start hidden until measured.
  useEffect(() => {
    if (open && i === 0) {
      firedActions.current.clear();
      setReady(false);
      setRect(null);
    }
  }, [open, i]);

  // Navigate to the step's route before measuring.
  useEffect(() => {
    if (!open || !step?.route) return;
    if (location.pathname !== step.route) navigate(step.route);
  }, [open, step, location.pathname, navigate]);

  // Poll for the target element; keep the cutout glued on scroll/resize.
  useEffect(() => {
    if (!open || !step) return;
    const fire = () => {
      if (step.action && !firedActions.current.has(step.id)) {
        firedActions.current.add(step.id);
        window.setTimeout(step.action, 80);
      }
    };
    if (!step.target) {
      setRect(null);
      setReady(true);
      fire();
      return;
    }
    const target = step.target; // narrowed for use inside listeners/polls
    let stopped = false;
    let tries = 0;
    let timer = 0;
    const measure = (el: Element): boolean => {
      const r = el.getBoundingClientRect();
      if (r.width < 24 && r.height < 24) return false;
      setRect({ x: r.x, y: r.y, w: r.width, h: r.height });
      return true;
    };
    setReady(false);
    const tick = () => {
      if (stopped) return;
      const el = document.querySelector(target);
      if (el && measure(el)) {
        setReady(true);
        fire();
        return;
      }
      if (++tries > 160) {
        // ~5 s and still nothing: degrade to a centred card, don't block the tour
        setRect(null);
        setReady(true);
        fire();
        return;
      }
      timer = window.setTimeout(() => requestAnimationFrame(tick), 40);
    };
    requestAnimationFrame(tick);
    const reflow = () => {
      const el = document.querySelector(target);
      if (el) measure(el);
    };
    window.addEventListener('resize', reflow);
    window.addEventListener('scroll', reflow, true);
    return () => {
      stopped = true;
      clearTimeout(timer);
      window.removeEventListener('resize', reflow);
      window.removeEventListener('scroll', reflow, true);
    };
  }, [open, step, location.pathname]);

  // Keyboard control.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') tourStore.stop();
      else if (e.key === 'Enter' || e.key === 'ArrowRight') {
        e.preventDefault();
        tourStore.next(total);
      } else if (e.key === 'ArrowLeft') tourStore.prev();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, total]);

  useEffect(() => {
    if (open) nextBtnRef.current?.focus();
  }, [open, i]);

  if (!open || !step) return null;

  const vw = window.innerWidth;
  const vh = window.innerHeight;
  let cardStyle: React.CSSProperties;
  if (!rect) {
    cardStyle = { left: '50%', top: '50%', transform: 'translate(-50%, -50%)' };
  } else {
    const below = rect.y + rect.h + GAP + CARD_H_EST < vh;
    const top = below
      ? rect.y + rect.h + GAP
      : Math.max(12, Math.min(rect.y - GAP - CARD_H_EST, vh - CARD_H_EST - 12));
    const left = Math.max(12, Math.min(rect.x + rect.w / 2 - CARD_W / 2, vw - CARD_W - 12));
    cardStyle = { left, top };
  }

  return (
    <>
      {/* Scrim: click anywhere to advance. */}
      <div
        className="fixed inset-0 z-[10040] cursor-pointer"
        onClick={() => tourStore.next(total)}
        aria-hidden
      />
      {rect ? (
        <div
          aria-hidden
          className="pointer-events-none fixed z-[10041] rounded-2xl transition-all duration-300 ease-out"
          style={{
            left: rect.x - PAD,
            top: rect.y - PAD,
            width: rect.w + PAD * 2,
            height: rect.h + PAD * 2,
            boxShadow:
              '0 0 0 9999px rgba(2,6,23,.68), 0 0 0 2px rgba(249,115,22,.9), 0 0 34px 6px rgba(249,115,22,.28)',
          }}
        />
      ) : null}

      <div
        role="dialog"
        aria-label={`Guided tour, step ${i + 1} of ${total}`}
        className={cn(
          'fixed z-[10042] w-[360px] max-w-[calc(100vw-24px)] rounded-2xl border border-line bg-surface-1 p-4 shadow-2xl transition-all duration-300 ease-out',
          !ready && 'pointer-events-none opacity-0',
        )}
        style={cardStyle}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-2 flex items-center gap-2">
          <span className="grid h-6 w-6 place-items-center rounded-lg bg-brand/10 text-brand" aria-hidden>
            <GraduationCap size={14} />
          </span>
          <span className="font-mono text-[10px] font-semibold text-ink-faint">
            {i + 1} / {total}
          </span>
          <span className="ml-auto flex items-center gap-1" aria-hidden>
            {TOUR_STEPS.map((s, si) => (
              <span
                key={s.id}
                className={cn(
                  'h-1 rounded-full transition-all duration-300',
                  si === i ? 'w-4 bg-brand' : si < i ? 'w-1.5 bg-brand/45' : 'w-1.5 bg-line',
                )}
              />
            ))}
          </span>
          <button
            type="button"
            onClick={() => tourStore.stop()}
            aria-label="Exit walkthrough"
            title="Exit (Esc)"
            className="grid h-6 w-6 place-items-center rounded-md text-ink-faint transition-colors hover:bg-surface-2 hover:text-ink"
          >
            <X size={13} aria-hidden />
          </button>
        </div>

        <h3 className="text-sm font-bold text-ink">{step.title}</h3>
        <p className="mt-1 text-xs leading-relaxed text-ink-muted">{step.body}</p>

        <div className="mt-3 flex items-center gap-2">
          <button
            type="button"
            onClick={() => tourStore.prev()}
            className={cn('btn-ghost btn-xs', i === 0 && 'invisible')}
          >
            <ChevronLeft size={12} aria-hidden /> Back
          </button>
          <span className="ml-auto text-[10px] text-ink-faint">click backdrop to advance</span>
          <button
            ref={nextBtnRef}
            type="button"
            onClick={() => tourStore.next(total)}
            className="btn-primary btn-xs"
          >
            {i === total - 1 ? 'Finish' : (step.cta ?? 'Next')}
            {i < total - 1 && <ChevronRight size={12} aria-hidden />}
          </button>
        </div>
      </div>
    </>
  );
}
