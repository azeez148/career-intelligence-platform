# Angular foundation

Use Node 22.22.3 (`.nvmrc`) and `npm ci`. Commands: `npm start`, `npm run lint`, `npm test`, `npm run build`, and `npm run e2e`.

The dev proxy forwards `/api/**` to `127.0.0.1:8000`. Browser smoke tests default to the isolated Compose web server on port 18080; set `PLAYWRIGHT_BASE_URL` to override it.

See the [root README](../../README.md), [operations](../../docs/operations/local-development.md), and [test evidence](../../docs/testing/phase-0.md).
