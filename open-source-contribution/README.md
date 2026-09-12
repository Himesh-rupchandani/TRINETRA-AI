# Open-source contribution — ready to submit

**Repo:** [`wemake-services/django-modern-rest`](https://github.com/wemake-services/django-modern-rest) (1,449★, MIT, Python/Django REST framework with types)
**Issue:** [#1441 — Support `SlugConverter` and `PathConverter` from Django in path parameters](https://github.com/wemake-services/django-modern-rest/issues/1441)
**Status:** issue still **open / unassigned / no comments** as of 2026-09-12 10:15 UTC; patch is written, tested and lint/type-checked.
**Your remaining job:** claim the issue in your own words, then apply the patch and open the PR (~5 min of commands, listed below).

---

## 1. Why this repo + this issue

| Signal you asked for | Evidence |
| --- | --- |
| **Active repo** | last push 2026-09-12 09:33 UTC (minutes before I looked); 1,449★, 194 forks, 15 watchers |
| **Fast response** | community PRs merged by maintainer `sobolevn` the *same day*, e.g. #1433 opened 07:13 → merged 07:23 (10 minutes); #1427, #1420, #1419, #1417 all merged within hours |
| **High chance to merge** | the issue was opened by the *maintainer himself* with a concrete spec and implementation hints, and is labelled `good first issue` + `help wanted` + `opensource september` (an organised onboarding push). Several fresh issues in the same batch are currently being merged one after another. |
| **Issue is new** | #1441 was created 2026-09-12 09:28 UTC, i.e. today — and is the only unclaimed issue of the batch that needs real code plus tests |

Runner-up (in case #1441 gets taken while you read this): **#1439 “Improve `re_path` default parameter schema”** in the same repo (same file, same technique, also maintainer-authored + `good first issue`), or [`Automattic/harper#4367`](https://github.com/Automattic/harper/issues/4367) (15.3k★ Rust grammar checker, outside contributor PRs merged in ~1 hour — heavier because Rust).

## 2. What the patch does

Django's `path()` converters `slug` and `path` were documented as a plain `string` in the generated OpenAPI schema, losing the useful constraints. The patch teaches `ComponentParserGenerator` about them:

* `<slug:x>` → `{"type": "string", "pattern": "[-a-zA-Z0-9_]+"}` (pattern taken from `converters.SlugConverter.regex`, not hard-coded)
* `<path:x>` → `{"type": "string", "description": "Can contain slashes"}`
* `int`, `uuid`, `str` converters: unchanged (their schema, including the auto-generated `title`, is preserved)
* custom converters using `__dmr_converter_schema__`: unchanged
* `re_path()` handling: unchanged (that is issue #1439, deliberately not touched → no unrelated changes)

Files changed (121 insertions, 1 deletion):

| File | What |
| --- | --- |
| `dmr/openapi/generators/component_parsers.py` | `_converter_schemas` map + merge of those extra fields into the serializer-generated parameter schema |
| `tests/test_unit/test_openapi/test_path_converters.py` | new end-to-end test through `build_schema(...).convert()` |
| `docs/pages/components/path.rst` | documents that all built-in converters are now described in the schema |

## 3. Verification already done (on a clone at upstream `master` = `87a02f5`)

```text
pytest tests/test_unit            → 2330 passed, 5 skipped  (all 54 snapshots pass, no snapshot churn)
coverage                          → dmr/openapi/generators/component_parsers.py 100% (branch coverage on)
pytest tests/test_unit/test_openapi (fresh clone + git apply) → 210 passed
ruff check / ruff format --check  → pass
flake8 (wemake-python-styleguide) → pass
mypy .                            → Success: no issues found in 693 source files
pyright (whole repo)              → no errors
pyrefly check / slotscheck / import-linter → pass
ty check --error=all              → 2 pre-existing diagnostics, identical on unmodified master (no new ones)
tracecov gate (operations=100%)   → pass
```

The patch also applies cleanly with `git apply --check` on a fresh clone of `master` (re-verified after `git fetch`).

## 4. How to submit

```bash
# 1. Fork https://github.com/wemake-services/django-modern-rest in the browser (your account must be the author)
git clone https://github.com/<your-username>/django-modern-rest.git
cd django-modern-rest
git remote add upstream https://github.com/wemake-services/django-modern-rest.git
git fetch upstream && git checkout -b feat/path-converter-schemas upstream/master

# 2. Apply the patch (file next to this README)
git apply /path/to/open-source-contribution/django-modern-rest-1441.patch

# 3. Reproduce the checks (needs uv: https://docs.astral.sh/uv/)
uv sync --all-groups --all-extras
uv run python -m pytest tests/test_unit -n auto
uv run python -m ruff check && uv run python -m flake8 . && uv run python -m mypy .

# 4. Commit as yourself, push, open the PR
git add -A
git commit -m "OpenAPI: document slug and path Django converters, #1441"
git push -u origin feat/path-converter-schemas
gh pr create --repo wemake-services/django-modern-rest --base master \
  --title "Document \`slug\` and \`path\` Django converters in the OpenAPI schema" \
  --body-file ../pr-description.md
```

**Before or right after opening the PR, comment on [issue #1441](https://github.com/wemake-services/django-modern-rest/issues/1441) saying you are working on it** — the repo is busy today (the maintainer opened a batch of onboarding issues this morning and two other people already opened PRs for the neighbouring issue #1440), so a one-line claim avoids duplicated work.

## 5. ⚠️ Read this: their AI policy

This project publishes an [AI policy](https://github.com/wemake-services/django-modern-rest/blob/master/.github/AI_POLICY.md) that is copied from Astral, and the PR template has a mandatory checkbox for it. Key sentences:

> “We support using AI (i.e., LLMs) as tools for coding. However, you remain responsible for any code you publish… **AI should not be used to generate comments when communicating with maintainers.** … **We do not allow autonomous agents to be used for contributing to our projects.** We will close any pull requests that we believe were created autonomously.”

Practical consequences for you (this is a normal “AI as a tool + human in the loop” setup, but it is on you to honour it):

1. **Read the patch and understand it before submitting.** Be able to explain, in your own words: what `_converter_schemas` does, why the extra fields are merged into the schema the serializer generated instead of replacing it (it preserves the `title` and any other serializer-specific fields), and why `re_path` is untouched. If anything is unclear, ask me and I will explain it line by line.
2. **Write the issue comment and the PR body yourself.** `pr-description.md` in this folder is a *fact sheet / skeleton*, not copy-paste text — the policy explicitly forbids pasting AI-generated prose. Rewrite it in your voice; keep the facts (what changed, why, how it was tested, `Closes #1441`).
3. **Answer review comments yourself.** Maintainers may ask questions or request changes; do not paste my answers.
4. **Keep the PR template checkbox honest:** no “Co-Authored-By: …agent…” lines are present in the patch, and you should not add any.
5. One more reason to keep it human: I cannot open the PR for you anyway — the GitHub credentials in this sandbox only have access to *this* repo (`Himesh-rupchandani/hack`) and are blocked from pushing to or forking the upstream project. The commands above are designed to be run from your own machine/account.

If you would rather not own it that way, tell me and I will prepare the same kind of contribution for a repo without such a policy.

## 6. Files in this folder

* `django-modern-rest-1441.patch` — the diff (applies with `git apply` on `master` @ `87a02f5`)
* `pr-description.md` — factual skeleton for the PR body (rewrite in your own words)
