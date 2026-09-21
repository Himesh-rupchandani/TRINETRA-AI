import { deepEq, eq, loadTs, suite, test } from './harness.mjs';

// Request-lifecycle tests for the real hook. Minimal hook/timer adapters avoid
// requiring a DOM or real clock; browser smoke separately exercises React.
let active;
const { useEventSearch } = loadTs('src/hooks/useEvents.ts', {
  react: {
    useState: (initial) => active.state(initial),
    useRef: (initial) => ({ current: initial }),
    useCallback: (callback) => callback,
    useEffect: (callback) => active.effects.push(callback),
  },
  '@/features/alerts/LiveProvider': { useLive: () => ({ eventsSeen: 0, connection: 'ONLINE' }) },
  '@/services/eventService': { eventService: { search: () => active.request() } },
});

const settle = () => new Promise((resolve) => setImmediate(resolve));
const records = { items: [{ id: '42', plate: 'GJ01AB1234' }], total: 1 };

async function withHook(check) {
  const saved = { setTimeout, clearTimeout, setInterval, clearInterval, document: globalThis.document };
  const rig = {
    values: [], effects: [], calls: [], timeouts: [], intervals: [],
    state(initial) {
      const index = this.values.push(initial) - 1;
      return [initial, (next) => { this.values[index] = next; }];
    },
    request() {
      return new Promise((resolve, reject) => this.calls.push({ resolve, reject }));
    },
  };
  active = rig;
  globalThis.setTimeout = (fn) => rig.timeouts.push(fn);
  globalThis.clearTimeout = () => {};
  globalThis.setInterval = (fn) => rig.intervals.push(fn);
  globalThis.clearInterval = () => {};
  globalThis.document = { hidden: false };
  const cleanups = [];
  try {
    rig.hook = useEventSearch({}, 1, 25);
    for (const effect of rig.effects) {
      const cleanup = effect();
      if (typeof cleanup === 'function') cleanups.push(cleanup);
    }
    await check(rig, () => cleanups.splice(0).forEach((cleanup) => cleanup()));
  } finally {
    cleanups.forEach((cleanup) => cleanup());
    Object.assign(globalThis, saved);
  }
}

suite('Vehicle Log — bounded, non-disruptive live refresh');
test('a background outage keeps the last successful rows, while manual refresh reports errors', () => withHook(async (rig) => {
  rig.calls[0].resolve(records);
  await settle();
  rig.intervals[0]();
  rig.calls[1].reject(new Error('Temporarily unavailable'));
  await settle();
  deepEq(rig.values[0], records);
  eq(rig.values[1], false);
  eq(rig.values[2], null);
  rig.hook.refresh();
  rig.calls[2].reject(new Error('Still unavailable'));
  await settle();
  eq(rig.values[2], 'Still unavailable');
}));
test('initial failures remain visible until a background request actually recovers', () => withHook(async (rig) => {
  rig.calls[0].reject(new Error('Offline'));
  await settle();
  rig.intervals[0]();
  eq(rig.values[2], 'Offline');
  rig.calls[1].resolve(records);
  await settle();
  deepEq(rig.values[0], records);
  eq(rig.values[2], null);
}));
test('repeated background triggers cannot create overlapping requests', () => withHook(async (rig) => {
  rig.timeouts[0]();
  rig.intervals[0]();
  rig.intervals[0]();
  eq(rig.calls.length, 1);
  rig.calls[0].resolve(records);
  await settle();
  rig.intervals[0]();
  rig.intervals[0]();
  eq(rig.calls.length, 2);
  rig.calls[1].resolve(records);
  await settle();
}));
test('late responses cannot change an unmounted log', () => withHook(async (rig, unmount) => {
  unmount();
  rig.calls[0].resolve(records);
  await settle();
  eq(rig.values[0], null);
}));
