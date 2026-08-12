# USD Liquidity Dashboard — Design QA

## Accepted source

- Reference: `design_handoff_liquidity_dashboard/Liquidity Dashboard.dc.html`
- Normative specification: the handoff `README.md`; production uses the repository's React, TypeScript, Vite, and ECharts runtime.
- Data comparison used the current `public/data/**` payload. The handoff's older JSON copies were not used by the application.

## Visual fidelity

- 1440 × 1000: compared reference and final renders at the same viewport. The four-row terminal deck, three switches, 400 / fluid / 352 body columns, hairlines, square geometry, typography, status colours, main chart, overlay, read rail, and footer align with the accepted direction.
- 1024 × 1000: the desktop deck remains three-column and readable without horizontal page overflow.
- 999px breakpoint: tape, charts, and read rail stack in that order with no horizontal page overflow.
- 390 × 844: status controls, switches, tape rows, both charts, balance bars, NOT WIRED chips, provenance, and the full-screen drawer remain readable and operable.
- Light and dark themes were visually checked. Screenshots stayed in `/tmp` and are not repository artefacts.

## Intentional production corrections

- The live payload's newer `generated_at` timestamp is shown instead of the handoff snapshot timestamp.
- Overlay dates use the selected series' sorted union and therefore retain IORB's latest date.
- Balance-sheet negative deltas use the README's red treatment.
- Percentage labels render one `%`; source health is interactive; switch order is keyed rather than JSON insertion order.

## Interaction and accessibility

- Tape selection, metric tabs, global range controls, overlay toggles, JSON download, source drawer, and methodology drawer passed browser checks.
- Theme choice survives reload in the browser session.
- Drawer initial focus, focus trap, Escape close, focus restoration, scrim close behaviour, and body scroll lock passed.
- Charts expose accessible summaries; controls expose pressed/selected state and visible keyboard focus.
- Loading and fatal error states are live regions and explicitly state that missing values are never replaced with zero.

## Data and runtime

- All 11 full series load independently; a failed series falls back to its snapshot `short_series` without failing the page.
- Ranges share one global latest-date anchor; overlay values align on a sorted date union with explicit null gaps.
- Snapshot failure is fatal; manifest failure is nonfatal and produces a clear methodology-unavailable message.
- Browser console was clean at 1440, 1024, and 390px.

final result: passed
