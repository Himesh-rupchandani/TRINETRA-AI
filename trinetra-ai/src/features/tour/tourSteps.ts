/**
 * The guided walkthrough — one short stop per product beat.
 * Keep bodies to two sentences; judges read at a glance.
 * `target` elements are marked with data-tour="…" attributes across the pages.
 */
export interface TourStep {
  id: string;
  /** Route to navigate to before measuring the target (optional). */
  route?: string;
  /** CSS selector of the element to spotlight; omit for a centred card. */
  target?: string;
  title: string;
  body: string;
  /** Next-button label override. */
  cta?: string;
  /** Fired once after the target becomes visible (e.g. open a live feed). */
  action?: () => void;
}

export const TOUR_STEPS: TourStep[] = [
  {
    id: 'intro',
    title: 'TRINETRA AI in eight stops',
    body: 'One loop, live: dashboard → Gujarat map → AI feed → alerts → vehicle trace. Enter / → advances, ← goes back, Esc exits at any time.',
    cta: 'Start walkthrough',
  },
  {
    id: 'kpis',
    route: '/',
    target: '[data-tour="kpis"]',
    title: 'Command dashboard',
    body: 'Cameras, 24-hour detections and open alerts stream over SSE — nothing here is refreshed by hand. These counters are produced by the detection pipeline itself.',
  },
  {
    id: 'map',
    route: '/gis',
    target: '[data-tour="gis-map"]',
    title: 'The Gujarat map',
    body: 'Live Mapbox basemap (try Night for dark ops), the state outline drawn from census boundaries, and a pin per camera. Zoom out and the pins fold into district bubbles with counts.',
  },
  {
    id: 'layers',
    route: '/gis',
    target: '[data-tour="map-layers"]',
    title: 'Analyst controls',
    body: 'Toggle cameras, sightings, coverage, state focus and district density. Click any district to filter the whole screen to it — map, pins and the list on the right.',
  },
  {
    id: 'feed-open',
    route: '/gis',
    target: '[data-tour="camera-list"]',
    title: 'Every camera, one click',
    body: 'Pick a camera and its live feed docks right onto the map — no page change, no new tab. Watch: the DEMO FEED stream is opening for you now.',
    cta: 'See the feed',
    action: () => {
      const btns = Array.from(document.querySelectorAll<HTMLElement>('[data-tour="camera-list"] button'));
      const demo = btns.find((b) => /DEMO FEED/i.test(b.textContent ?? '')) ?? btns[0];
      demo?.click();
    },
  },
  {
    id: 'feed',
    route: '/gis',
    target: '[data-tour="live-feed"]',
    title: 'Real AI on every frame',
    body: 'What this card plays: YOLO11 vehicle boxes + track IDs and ANPR plate reads, annotated live by the engine and streamed from the backend — same-origin, works on venue Wi-Fi.',
  },
  {
    id: 'alerts',
    route: '/alerts',
    target: '[data-tour="alerts-list"]',
    title: 'Watchlist alert desk',
    body: 'Plate read → watchlist match → one CRITICAL alert (deduplicated, not spam). The hit card came from the map feed minutes ago — acknowledge, resolve, jump to evidence.',
  },
  {
    id: 'trace',
    route: '/vehicles/GJ01AB1234',
    target: '[data-tour="trace"]',
    title: 'Vehicle trace',
    body: 'Type any plate into the global search (⌘K) and get its timeline: every sighting, the evidence crop and the cross-camera route — including detections from the live demo feeds.',
  },
  {
    id: 'outro',
    title: 'That’s the loop',
    body: 'CCTV frame → detect → track → read plate → alert → trace, end to end and genuinely live. Replay this tour anytime from the ✨ Tour button in the header.',
    cta: 'Finish',
  },
];
