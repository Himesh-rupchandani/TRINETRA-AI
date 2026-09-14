import { useEffect } from 'react';

const CLICKABLE = 'button, a, [role="button"]';

/** Compact, icon-sized controls get a click ripple; big panels don't flood. */
function isRippleHost(el: HTMLElement): boolean {
  if (el.tagName === 'BUTTON') return true;
  if (/(^|\s)(btn|icon)(\s|$)/.test(el.className)) return true;
  const r = el.getBoundingClientRect();
  return r.width <= 64 && r.height <= 64;
}

/**
 * Global, zero-markup icon motion.
 *
 *  - Every lucide icon pressed inside a button / link plays a one-shot "pop".
 *  - Compact icon controls additionally emit a Material-style ripple from the
 *    exact click point.
 *
 * This covers the whole app (sidebar, header, cards, tables, toolbar buttons)
 * without touching individual components. Honours `prefers-reduced-motion`.
 */
export function useGlobalIconFx() {
  useEffect(() => {
    if (typeof window === 'undefined') return;
    const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    if (reduce) return;

    const onDown = (e: PointerEvent) => {
      const t = e.target as HTMLElement | null;
      if (!t || !t.closest) return;
      const host = t.closest(CLICKABLE) as HTMLElement | null;
      if (!host) return;

      const icon =
        (t.closest('.lucide') as HTMLElement | null) ??
        (host.querySelector('.lucide') as HTMLElement | null);
      if (!icon) return;

      // One-shot pop — restart cleanly even on rapid repeat clicks.
      icon.classList.remove('icon-pop-on');
      void icon.offsetWidth; // force reflow so the animation re-triggers
      icon.classList.add('icon-pop-on');
      icon.addEventListener(
        'animationend',
        () => icon.classList.remove('icon-pop-on'),
        { once: true },
      );

      if (!isRippleHost(host)) return;

      const cs = getComputedStyle(host);
      if (cs.position === 'static') host.style.position = 'relative';

      const rect = host.getBoundingClientRect();
      const x = (e.clientX || rect.left + rect.width / 2) - rect.left;
      const y = (e.clientY || rect.top + rect.height / 2) - rect.top;

      const ripple = document.createElement('span');
      ripple.className = 'icon-ripple';
      ripple.style.left = `${x}px`;
      ripple.style.top = `${y}px`;
      host.appendChild(ripple);
      ripple.addEventListener('animationend', () => ripple.remove(), { once: true });
    };

    document.addEventListener('pointerdown', onDown);
    return () => document.removeEventListener('pointerdown', onDown);
  }, []);
}
