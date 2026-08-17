# Browser validation

P0 browser tests use Chromium and the local Next.js app. Install the browser once
with `npx playwright install chromium`, then use the package scripts from the
repository root or `npm --prefix apps/web run ...`.

`tooling-smoke.spec.ts` intentionally does not require login, API data or a seed.
It only verifies that Chromium and `@axe-core/playwright` can run.
