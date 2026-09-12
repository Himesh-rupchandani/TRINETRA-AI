# PR body — factual skeleton, REWRITE IN YOUR OWN WORDS

> The maintainers require every PR description to be written by a human (see
> their AI policy). The bullets below are the facts to cover, not text to paste.
> Write 3–6 sentences / short bullets in your own voice, keep the closing
> reference `Closes #1441`, and fill in the checkboxes of their PR template.

## What to say

- What was wrong before: `path()` parameters are generated from the Django
  converter, but the generator only knew `int` and `uuid`, so `slug` and `path`
  parameters were documented as a plain `string` with no constraints.
- What the PR does:
  - `slug` parameters now get the pattern `[-a-zA-Z0-9_]+`
    (read from Django's `SlugConverter.regex`, so it cannot drift).
  - `path` parameters are documented with `description: Can contain slashes`.
  - The extra fields are merged into the schema the serializer already produced,
    so the converter-specific schema is kept intact: `int`/`uuid`/`str` output
    is byte-identical (no snapshot changes) and custom converters using
    `__dmr_converter_schema__` keep working.
  - `re_path()` is intentionally untouched — that is the separate issue #1439.
- How it is tested: new test file
  `tests/test_unit/test_openapi/test_path_converters.py` builds a full schema
  through `build_schema(...).convert()` with `<int:…>/<slug:…>/<path:…>` in one
  URL and asserts the resulting parameter schemas.
- Docs: `docs/pages/components/path.rst` now says how all built-in converters
  appear in the schema.
- QA: `pytest tests/test_unit` (2330 passed), `ruff`, `flake8`, `mypy`,
  `pyright`, `pyrefly`, `ty`, plus the coverage and tracecov gates — all green.

## Checklist for their template

- [ ] AI Policy checkbox — only tick it if it is honest for you (they require a
      human in the loop who understands the change and wrote the text).
- [ ] No unrelated changes (the diff is 3 files: generator, test, docs).
- [ ] At least one test case — yes, see above.
- [ ] Documentation updated — yes, `docs/pages/components/path.rst`.
- [ ] `Closes #1441`.
