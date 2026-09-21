/**
 * ZERO-DEPENDENCY FRONTEND TEST HARNESS
 * -------------------------------------
 * The frontend has no JS test runner installed (no vitest/jest in
 * node_modules), yet several bug fixes live in pure TypeScript modules whose
 * behaviour must stay pinned — `toId` (alert ids reaching the API as "NaN"),
 * `asCameraStatus` (NOT_CONFIGURED collapsed into OFFLINE), `prettyPlate`
 * (half-split plates) and the plate regex shared with the two Python layers.
 *
 * Rather than assert on source text, this harness transpiles the real module
 * with sucrase (already a dependency of the toolchain) and executes it in a
 * `vm` context with a tiny require shim, so the tests exercise the shipped
 * code instead of a copy of it. Bare packages (`./api` -> axios chain) are
 * injected as stubs; anything unresolvable fails loudly.
 *
 * Usage:
 *   import { test, eq, runAll, loadTs } from './harness.mjs';
 *   const { toId } = loadTs('src/services/adapters.ts', STUBS);
 *   test('toId never yields NaN', () => eq(toId('AL-7'), '7'));
 *   // run-tests.mjs imports every *.test.mjs, then: process.exit(await runAll())
 */
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { createRequire } from 'node:module';

const nodeRequire = createRequire(import.meta.url);
const { transform } = nodeRequire('sucrase');

// tests/ -> trinetra-ai/ -> repository root
export const FRONTEND_ROOT = path.resolve(fileURLToDir(import.meta.url), '..');
export const REPO_ROOT = path.resolve(FRONTEND_ROOT, '..');

function fileURLToDir(url) {
  return path.dirname(new URL(url).pathname);
}

/* ------------------------------- module loader ---------------------------- */

const moduleCache = new Map();

function resolveSpec(spec, fromFile) {
  if (spec.startsWith('@/')) return path.join(FRONTEND_ROOT, 'src', spec.slice(2));
  if (spec.startsWith('./') || spec.startsWith('../')) return path.resolve(path.dirname(fromFile), spec);
  return null; // bare package specifier — must be stubbed
}

function withExtension(file) {
  for (const candidate of [file, `${file}.ts`, `${file}.tsx`, `${file}/index.ts`]) {
    if (fs.existsSync(candidate) && fs.statSync(candidate).isFile()) return candidate;
  }
  return null;
}

/**
 * Load a TypeScript module from the frontend source tree and return its
 * exports. `stubs` maps either a bare specifier ('./api') or an absolute path
 * to the exports object that specifier should resolve to.
 */
export function loadTs(relOrAbs, stubs = {}) {
  const requested = path.isAbsolute(relOrAbs) ? relOrAbs : path.join(FRONTEND_ROOT, relOrAbs);
  const file = withExtension(requested);
  if (!file) throw new Error(`harness: cannot find module ${relOrAbs}`);
  if (moduleCache.has(file)) return moduleCache.get(file);

  const source = fs.readFileSync(file, 'utf8');
  const { code } = transform(source, {
    transforms: ['typescript', 'imports'],
    filePath: file,
    production: true,
    disableESTransforms: true,
  });

  const module = { exports: {} };
  moduleCache.set(file, module.exports);

  const localRequire = (spec) => {
    if (spec in stubs) return stubs[spec];
    const resolved = resolveSpec(spec, file);
    if (resolved && stubs[resolved]) return stubs[resolved];
    if (resolved) return loadTs(resolved, stubs);
    throw new Error(
      `harness: "${spec}" (imported by ${path.relative(FRONTEND_ROOT, file)}) is a bare package ` +
        'specifier — add a stub for it',
    );
  };

  const wrapper = vm.runInThisContext(
    `(function (exports, require, module, __filename, __dirname) {\n${code}\n})`,
    { filename: file },
  );
  wrapper(module.exports, localRequire, module, file, path.dirname(file));
  return module.exports;
}

/** Read a source file (frontend- or repo-relative) as text. */
export function readSource(relPath) {
  const file = path.isAbsolute(relPath) ? relPath : path.join(REPO_ROOT, relPath);
  if (!fs.existsSync(file)) throw new Error(`harness: missing source file ${relPath}`);
  return fs.readFileSync(file, 'utf8');
}

/* --------------------------------- assertions ------------------------------ */

export class AssertionError extends Error {}

function show(value) {
  if (typeof value === 'string') return JSON.stringify(value);
  try {
    return JSON.stringify(value) ?? String(value);
  } catch {
    return String(value);
  }
}

export function eq(actual, expected, message = '') {
  if (!Object.is(actual, expected)) {
    throw new AssertionError(`${message ? message + ': ' : ''}expected ${show(expected)}, got ${show(actual)}`);
  }
}

export function deepEq(actual, expected, message = '') {
  const a = JSON.stringify(actual);
  const b = JSON.stringify(expected);
  if (a !== b) {
    throw new AssertionError(`${message ? message + ': ' : ''}expected ${b}, got ${a}`);
  }
}

export function ok(value, message = 'expected a truthy value') {
  if (!value) throw new AssertionError(`${message} (got ${show(value)})`);
}

export function notOk(value, message = 'expected a falsy value') {
  if (value) throw new AssertionError(`${message} (got ${show(value)})`);
}

export function matches(value, regex, message = '') {
  if (!regex.test(value)) {
    throw new AssertionError(`${message ? message + ': ' : ''}${show(value)} does not match ${regex}`);
  }
}

export function includes(haystack, needle, message = '') {
  const found = Array.isArray(haystack) ? haystack.includes(needle) : String(haystack).includes(needle);
  if (!found) {
    throw new AssertionError(`${message ? message + ': ' : ''}${show(needle)} not found in ${show(haystack)}`);
  }
}

export function excludes(haystack, needle, message = '') {
  const found = Array.isArray(haystack) ? haystack.includes(needle) : String(haystack).includes(needle);
  if (found) {
    throw new AssertionError(`${message ? message + ': ' : ''}${show(needle)} unexpectedly present in ${show(haystack)}`);
  }
}

export function doesNotThrow(fn, message = 'expected no throw') {
  try {
    fn();
  } catch (error) {
    throw new AssertionError(`${message}: ${error.message}`);
  }
}

export function throws(fn, message = 'expected a throw') {
  try {
    fn();
  } catch {
    return;
  }
  throw new AssertionError(message);
}

/* ---------------------------------- runner -------------------------------- */

const registered = [];
let currentSuite = 'suite';

export function suite(name) {
  currentSuite = name;
}

export function test(name, fn) {
  registered.push({ suite: currentSuite, name, fn });
}

export async function runAll() {
  let failed = 0;
  let lastSuite = null;
  for (const { suite: s, name, fn } of registered) {
    if (s !== lastSuite) {
      console.log(`\n${s}`);
      lastSuite = s;
    }
    try {
      await fn();
      console.log(`  ok   ${name}`);
    } catch (error) {
      failed += 1;
      console.log(`  FAIL ${name}`);
      console.log(`       ${error.message}`);
    }
  }
  const total = registered.length;
  console.log(`\n${total - failed}/${total} frontend tests passed`);
  return failed === 0 ? 0 : 1;
}
