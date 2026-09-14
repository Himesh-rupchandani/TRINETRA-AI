/**
 * Runner for the LIVE contract check.
 *
 * `src/services/adapters.ts` imports through the `@/` alias and reaches
 * `import.meta.env`, so it cannot be loaded by bare Node. Booting Vite's SSR
 * loader means the check exercises the exact modules the app bundles — aliases,
 * env and all — rather than a copy of them.
 *
 *   BACKEND=http://127.0.0.1:8000 npm run verify:live
 */
import { createServer } from 'vite';
import path from 'node:path';

const root = path.resolve(import.meta.dirname, '..');

// In the browser the app talks to a same-origin '/api'. Under SSR there is no
// origin, so point the axios base at the backend being checked.
const BACKEND = (process.env.BACKEND ?? 'http://127.0.0.1:8000').replace(/\/$/, '');
process.env.VITE_API_BASE_URL ??= `${BACKEND}/api`;

const server = await createServer({
  root,
  configFile: path.join(root, 'vite.config.ts'),
  server: { middlewareMode: true, hmr: false },
  appType: 'custom',
  logLevel: 'error',
});

try {
  await server.ssrLoadModule('/scripts/verify-live-contract.ts');
} catch (err) {
  console.error(`\nBLOCKED — ${err instanceof Error ? err.stack ?? err.message : String(err)}`);
  process.exitCode = 2;
} finally {
  await server.close();
}
