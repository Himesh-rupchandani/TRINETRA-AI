import { useEffect, useState, type RefObject } from 'react';

/**
 * True while the referenced element is on screen (or close to it).
 *
 * The camera grid uses this to decide *when* a preview may cost bandwidth:
 * a registry page holds dozens of cards, and a control room must never pull
 * every one of those feeds through the gateway at once. A card that is
 * scrolled away releases its stream again.
 *
 * Two details matter for the grid:
 *  - `rootMargin` starts the preview slightly BEFORE the card reaches the
 *    viewport, so the video is already running when the operator looks at it;
 *  - both transitions are debounced, so flicking the scroll wheel through the
 *    list does not open and tear down a stream per card in between.
 *
 * @param ref        element to watch
 * @param enabled    when false the observer is not armed and the value is false
 * @param rootMargin how far outside the viewport still counts as visible
 * @param delayMs    debounce applied to both transitions
 */
export function useInViewport<T extends Element>(
  ref: RefObject<T | null>,
  enabled = true,
  rootMargin = '180px',
  delayMs = 220,
): boolean {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (!enabled) {
      setVisible(false);
      return;
    }
    const el = ref.current;
    if (!el) return;
    // Very old browsers (and jsdom) have no IntersectionObserver: showing the
    // preview is the safer degradation, since the alternative is an empty tile.
    if (typeof IntersectionObserver === 'undefined') {
      setVisible(true);
      return;
    }

    let settle: ReturnType<typeof setTimeout> | null = null;
    const io = new IntersectionObserver(
      (entries) => {
        const next = entries.some((e) => e.isIntersecting);
        if (settle) clearTimeout(settle);
        settle = setTimeout(() => setVisible(next), delayMs);
      },
      { rootMargin, threshold: 0.01 },
    );
    io.observe(el);
    return () => {
      if (settle) clearTimeout(settle);
      io.disconnect();
    };
  }, [ref, enabled, rootMargin, delayMs]);

  return visible;
}
