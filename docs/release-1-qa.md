# Release 1 — G0 + P0 QA record

Date: 2026-08-12<br>
Scope: schema v2 foundation, P0 Liquidity Fuel, four hash routes, staged publication workflow<br>
Baseline commit: `2ba6abfad26dbcc460a4356cd005e0d211a4201d`

## Data and rule contract

- Staged artifact validates as schema `2.0.0` with `snapshot.json`, `manifest.json`, `alerts.json`, `events.json`, and 39 matching canonical series files.
- Legacy aliases are absent. `public/data/**` was not changed during local staging.
- `on_rrp_accepted` publishes its measured fractional value; `srf_accepted` preserves a genuine `0.0` rather than converting it to missing.
- Exact duplicates dedupe and conflicting source rows fail closed across FRED, NY Fed, FiscalData TGA, and Treasury auctions. SRF detail totals must reconcile to operation totals.
- SRF operational-readiness exclusions match a reviewed operation ID, so regular usage on the same date stays alert-eligible. ON RRP near-floor context is trailing-history relative and never uses a fixed dollar danger threshold.
- All 22 Release 1 unavailable metrics remain `null`, with rights reason, missing input, and future-interface disclosure.
- A stale or not-yet-released required P0 input now makes the deterministic assessment `UNAVAILABLE` with `LOW` confidence. It cannot fall through to `NEUTRAL`.
- Each P0 evidence block computes coverage independently. An unavailable block never displays a stale trigger such as `P10 BREACH` or `3/3 UP`.
- The local no-key run failed closed: last-good FRED observations remained `STALE`, the P0 assessment was `UNAVAILABLE`, and no `fredgraph.csv` fallback was used.

## Automated gates

- Python 3.12: `86 passed` against the final staged artifact via `BUBBLE_DATA_DIR`.
- Frontend: `27 passed`; the exact temporary-workspace `npm ci`, Vitest, TypeScript, and production-build path passed.
- TypeScript and Vite production build passed. The existing JavaScript chunk-size advisory remains non-blocking.
- Workflow contract tests passed; `actionlint` passed in the Node 22/Linux parity audit.
- Cross-parent staging/promotion smoke test passed, including whole-directory replacement and legacy-file removal.
- `git diff --check`, untracked-file whitespace checks, and binary-diff checks passed.

## Browser QA

Local production build was served with the real staged v2 artifact and checked at 1440×1000, 1024×1000, and 390×844.

- Overview, Liquidity Fuel, Market Ignition, and Fundamental Exit routes render and deep-link correctly.
- Browser Back/Forward, route-heading focus, switch-card Arrow navigation, and native Enter activation passed.
- Route-specific series loading, 8W/12W regime windows, overlay toggles, weekly change labels, and reserve reference lines passed.
- Source and metric drawers passed focus trap, Escape close, scrim close, and focus restoration.
- Non-OK numeric values display a visible `LAST-GOOD` marker across tape, charts, overlays, balance rows and methodology drawers; chart summaries state that they are not today's new values.
- FRED and New York Fed public source notices, Terms links, attribution and non-affiliation wording are visible at desktop and mobile widths.
- ON RRP rendered as `0.725B`; true-zero SRF rendered as `0B`; unavailable values rendered as `—`.
- The JSON download resolves to the v2 snapshot and returns 39 metrics.
- No page-level horizontal overflow was present at 1024 or 390 pixels. Console logs remained empty after the interaction loop.

## Production gate

- Repository variable `SEC_USER_AGENT` is configured as `Bubble USD Liquidity Dashboard laubonghaudoi@icloud.com`.
- Required repository secret `FRED_API_KEY` is configured. Its value is scoped only to the workflow preflight and Python fetch step.
- Release 1 is ready to push; no live deployment claim is made until Actions and Pages QA complete.

final result: pending successful Actions deployment and live Pages QA
