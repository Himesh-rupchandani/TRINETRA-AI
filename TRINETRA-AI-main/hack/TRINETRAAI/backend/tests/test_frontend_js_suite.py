"""Runs the frontend regression suite (`trinetra-ai/tests`) from pytest.

The frontend has no JS test runner installed (no vitest/jest in node_modules),
yet several bug fixes live in TypeScript whose behaviour must stay pinned:

  item 3  — realtime ids such as "AL-7" became ``NaN`` and were sent back to
            ``/api/alerts/NaN/resolve``;
  item 8  — ``prettyPlate`` half-split non-canonical plates ("GJ011234");
  item 9  — the UI plate pattern must stay byte-identical to both Python layers;
  item 12 — the bandwidth panel invented projection figures on failure;
  item 13 — ``NOT_CONFIGURED`` cameras were collapsed into ``OFFLINE``;
  item 14 — the MJPEG effect ignored the ``streamType`` it reads;
  item 15 — the Command Center fetched KPIs exactly once per page load;
  item 16 — the stray root ``package-lock.json`` (``name: zip-2``);
  item 21 — gateway credentials hardcoded in sources/docs and committed;
  item 22 — the env setup scripts rewrote ``.env`` on every start;
  item 23 — the docs told operators to set a variable nothing reads.

``trinetra-ai/tests/harness.mjs`` transpiles the real modules with sucrase and
executes them in a ``vm`` context, so those tests exercise shipped code rather
than a copy of it; the env-setup tests run the real script inside a throwaway
directory tree. Wiring the suite into pytest keeps one entry point
(``cd TRINETRAAI/backend && pytest``) for the repository's regressions.

The suite is *skipped*, never failed, when node or the frontend dependencies are
unavailable — a Python-only checkout must still be able to run the backend tests.
"""
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

backend_root = Path(__file__).resolve().parents[1]
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))

# tests/ -> backend/ -> TRINETRAAI/ -> repository root
REPO_ROOT = Path(__file__).resolve().parents[3]
FRONTEND_ROOT = REPO_ROOT / "trinetra-ai"
RUNNER = FRONTEND_ROOT / "tests" / "run-tests.mjs"

NODE = shutil.which("node")

_skip_reason = None
if NODE is None:
    _skip_reason = "node is not installed — the frontend suite cannot run"
elif not RUNNER.exists():
    _skip_reason = f"frontend test runner missing at {RUNNER}"
elif not (FRONTEND_ROOT / "node_modules" / "sucrase").is_dir():
    _skip_reason = "frontend dependencies are not installed (run `npm install` in trinetra-ai)"

pytestmark = pytest.mark.skipif(bool(_skip_reason), reason=_skip_reason or "")


def _run_suite(timeout: int = 300):
    """Execute the frontend suite with a deterministic, credential-free env."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("SENTINEL_")}
    env.setdefault("PATH", os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"))
    return subprocess.run(
        [NODE, str(RUNNER)],
        cwd=str(FRONTEND_ROOT),
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )


@pytest.fixture(scope="module")
def suite_run():
    """Run the frontend suite once per module and share the result."""
    return _run_suite()


def test_frontend_regression_suite_passes(suite_run):
    proc = suite_run
    summary = re.search(r"(\d+)/(\d+) frontend tests passed", proc.stdout)
    if proc.returncode != 0 or not summary:
        # Show only the failing case names + reasons: the full output is noisy and
        # must never be dumped into a log that could carry a credential.
        failures = [line for line in proc.stdout.splitlines() if line.strip().startswith(("FAIL", "expected", "Error"))]
        pytest.fail(
            "frontend regression suite failed "
            f"(exit {proc.returncode}, summary={summary.group(0) if summary else 'none'})\n"
            + "\n".join(failures[:40])
            + ("\n" + proc.stderr[-2000:] if proc.stderr.strip() else "")
        )
    passed, total = int(summary.group(1)), int(summary.group(2))
    assert passed == total, f"{total - passed} frontend test(s) failed"
    # Guard against the suite silently shrinking to nothing.
    assert total >= 40, f"only {total} frontend tests ran — expected the full regression set"


def test_frontend_suite_is_wired_into_npm_test():
    """`npm test` in trinetra-ai must run the same suite CI/pytest runs."""
    import json

    pkg = json.loads((FRONTEND_ROOT / "package.json").read_text(encoding="utf-8"))
    assert pkg["scripts"].get("test", "").endswith("tests/run-tests.mjs")


def test_frontend_suite_reports_no_secret_leak(suite_run):
    """The suite itself asserts credentials never surface; double-check its output."""
    combined = suite_run.stdout + suite_run.stderr
    # A credential value from this machine must never appear in test output.
    env_file = FRONTEND_ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8", errors="replace").splitlines():
            match = re.match(r"^\s*(SENTINEL_EMAIL|SENTINEL_PASSWORD)\s*=(.+)$", line)
            if match and match.group(2).strip():
                assert match.group(2).strip() not in combined, (
                    f"the local {match.group(1)} value appeared in frontend test output"
                )
