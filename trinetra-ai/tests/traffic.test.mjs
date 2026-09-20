import { deepEq, eq, includes, loadTs, ok, readSource, suite, test } from './harness.mjs';
const calls = [];
const { trafficService, defaultTrafficConfig } = loadTs('src/services/trafficService.ts', {
  './api': Object.fromEntries(['get','post','put'].map(method => [method, async (...args) => { calls.push([method, ...args]); return {}; }])),
});
const { countingGeometry, trafficConfigProblem } = loadTs('src/lib/traffic.ts');

suite('traffic observations — normalized geometry, separate from ANPR');
test('line and zone coordinates use frame coordinates rather than screen pixels', () => {
  deepEq(countingGeometry({...defaultTrafficConfig, mode:'line'}, 640, 480), {kind:'line', x1:32, y1:240, x2:608, y2:240});
  deepEq(countingGeometry({...defaultTrafficConfig, mode:'line', axis:'vertical'}, 640, 480), {kind:'line', x1:320, y1:24, x2:320, y2:456});
  deepEq(countingGeometry({...defaultTrafficConfig, mode:'zone'}, 1920, 1080), {kind:'zone', x:480, y:270, width:960, height:540});
  eq(countingGeometry(defaultTrafficConfig,640,480),null);
});
test('bad spans, reversed boxes and nonfinite positions cannot paint or be saved', () => {
  for (const change of [{left:.9}, {top:.9}, {span_end:0}, {position:NaN}, {position:Infinity}, {mode:'wrong_way'}]) {
    const cfg = {...defaultTrafficConfig, mode:'zone', ...change};
    ok(trafficConfigProblem(cfg));
    eq(countingGeometry(cfg,640,480),null);
  }
  eq(trafficConfigProblem(defaultTrafficConfig),null);
  eq(trafficConfigProblem({...defaultTrafficConfig, span_start:.23, span_end:.25, left:.23, right:.25}), null);
});
test('config and count-reset requests never create plate events or alerts', async () => {
  calls.length = 0;
  await trafficService.settings('CAM 1');
  await trafficService.save('CAM 1', defaultTrafficConfig);
  await trafficService.reset('CAM 1');
  await trafficService.sessions();
  deepEq(calls.map(([method,path])=>[method,path]), [
    ['get','/cameras/CAM%201/traffic-config'], ['put','/cameras/CAM%201/traffic-config'],
    ['post','/cameras/CAM%201/traffic-reset'], ['get','/traffic/sessions'],
  ]);
});
test('the counting overlay uses contain geometry; current session counts are not a census', () => {
  includes(readSource('trinetra-ai/src/components/camera/CountingOverlay.tsx'), 'preserveAspectRatio="xMidYMid meet"');
  includes(readSource('trinetra-ai/src/components/dashboard/TrafficSessionsPanel.tsx'), 'not total traffic or unique registrations');
  includes(readSource('trinetra-ai/src/components/camera/TrafficCountingPanel.tsx'), 'not total traffic, plate reads or violations');
});
