#!/usr/bin/env node
/**
 * Frontend test entry point — `npm test` from trinetra-ai/.
 *
 * Zero dependencies beyond sucrase (already in node_modules): every *.test.mjs
 * registers its cases with tests/harness.mjs, then the whole set is executed and
 * the process exits non-zero if anything failed, so CI and `npm test` behave the
 * same way.
 */
import { runAll } from './harness.mjs';

await import('./adapters.test.mjs');
await import('./env-setup.test.mjs');
await import('./backend-status.test.mjs');
await import('./source-contracts.test.mjs');
await import('./live-anpr.test.mjs');
await import('./event-refresh.test.mjs');
await import('./evidence.test.mjs');
await import('./traffic.test.mjs');
await import('./deployment-routing.test.mjs');

process.exit(await runAll());
