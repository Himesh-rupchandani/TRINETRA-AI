import { eq, includes, loadTs, suite, test } from './harness.mjs';

const { analysisUnavailableReason } = loadTs('src/lib/analysisReadiness.ts');
suite('video analysis — backend readiness');
test('reports the backend memory admission reason', () => {
  includes(analysisUnavailableReason({ resource_budget: { allowed: false, reason: '512 MB RAM' } }), '512 MB RAM');
});
test('reports a missing vision stack', () => {
  includes(analysisUnavailableReason({ vision: { available: false, reason: 'OpenCV missing' } }), 'OpenCV missing');
});
test('does not claim failure for older or admitted backends', () => {
  eq(analysisUnavailableReason({}), null);
  eq(analysisUnavailableReason({ resource_budget: { allowed: true } }), null);
});
