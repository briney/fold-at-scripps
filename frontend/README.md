# fold@Scripps — Researcher SPA

The researcher-facing single-page app for fold@Scripps, built with Vite, React,
and TypeScript. Researchers browse the available tools, fill out schema-driven
submission forms, and track their runs.

## Scripts

```bash
npm run dev       # start the Vite dev server (with HMR)
npm run build     # type-check and produce a production build
npm run lint      # run ESLint over the source
npm test          # run the Vitest unit/component suite
npm run test:e2e  # run the Playwright end-to-end tests
```

## Backend

During development, Vite proxies API requests to the FastAPI backend at
`http://localhost:8000` (see the `server.proxy` config in `vite.config.ts`), so
run the backend alongside `npm run dev`.

## Tooling

- Build/dev: Vite with `@vitejs/plugin-react`.
- Linting: ESLint. Formatting: Prettier.
- Tests: Vitest (unit/component) and Playwright (end-to-end).
