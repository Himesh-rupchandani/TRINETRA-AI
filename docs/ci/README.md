# CI helpers

## `deploy-probe.yml` — is the production backend actually live?

`scripts/verify/verify_deploy.mjs` answers that question locally in one command.
`deploy-probe.yml` runs the same check on every merge to `main`, every `arena/**`
push, on demand, and daily — and writes the verdict into the job summary.

It lives here rather than in `.github/workflows/` because this repository is
pushed by automation whose token has no `workflows` permission; GitHub rejects
any push that creates or updates a file under `.github/workflows/`:

```
! [remote rejected] ... (refusing to allow a GitHub App to create or update
  workflow `.github/workflows/deploy-probe.yml` without `workflows` permission)
```

Enable it in one of two ways:

1. **From a normal checkout** (a human's PAT/SSH has the scope):

   ```bash
   mkdir -p .github/workflows
   git mv docs/ci/deploy-probe.yml .github/workflows/deploy-probe.yml
   git commit -m "ci: run the deploy probe on main" && git push
   ```

2. **In the GitHub UI**: Actions → *New workflow* → paste the file's contents →
   save as `.github/workflows/deploy-probe.yml`.

Afterwards the workflow is also runnable from **Actions → Deploy probe (prod
backend) → Run workflow**, which is the fastest way to show a reviewer exactly
what a deployment is serving.
