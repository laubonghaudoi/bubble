# USD Liquidity Dashboard — current visual QA

Date: 2026-08-13

Current candidate: Release 8, Provenance single-column presentation delta.

This document puts the latest local visual result first. The completed Release 7 redesign remains recorded as a historical baseline in `docs/release-7-qa.md`; its former desktop two-rail Provenance layout is not the current target.

## Release 8 source truth

The two user-supplied captures are the authority for the requested Provenance correction:

- `/var/folders/8c/37f47zk10552270psw18r9300000gn/T/codex-clipboard-e1e8878e-2b4f-43d8-93df-eca74bcecb9f.png` — 2940×1600, SHA-256 `ae768803b4ac78a31a7d6d3c75bd0b777960bb24f1ded2b8dc0046b41dce3220`.
- `/var/folders/8c/37f47zk10552270psw18r9300000gn/T/codex-clipboard-a53d58d0-25ad-4a77-9461-25c04c6ed048.png` — 1628×504, SHA-256 `24755e0a72cb20438bcae481b8be54e542db178fe5da64eeb3948a7080ac265a`.

They identify two related problems in the deployed Release 7 presentation: formulas and collector health compete in a split desktop rail, and notation is visually boxed and inset after an already dense formula section. The accepted Release 8 interpretation is:

1. Provenance has one page column at every width.
2. The full-width Yellow / Red / Extreme formula comparison comes first.
3. Notation follows the formulas at full available width, with no outer box, fill or side inset.
4. Source/model notes remain attached to the formula section.
5. Collector health and legal notices begin only after the formula section ends.

No formula, notation, source, legal, status or data content is removed by this presentation change.

## Combined comparison evidence

Local QA artifacts are under:

`/var/folders/8c/37f47zk10552270psw18r9300000gn/T/bubble-provenance-release8-qa-2026-08-13`

- `/var/folders/8c/37f47zk10552270psw18r9300000gn/T/bubble-provenance-release8-qa-2026-08-13/comparison-provenance-1920.png` — 1920×2104, SHA-256 `f9765ee7e76412fc4441e8d5efae94afd7adef22d9b6e20baf7bd70f439464f6`.
- `/var/folders/8c/37f47zk10552270psw18r9300000gn/T/bubble-provenance-release8-qa-2026-08-13/comparison-notation-1920.png` — 1920×1654, SHA-256 `168991ecc36b7bc666be7b461df4d39ae92ac8a09cf5c6a29ec5541d52858e40`.

The first comparison contrasts the previous split rail with the local single-column result: the three formula cards occupy the entire content width before any collector row. The second comparison shows the notation correction: the old inset bordered surface is replaced by a transparent, borderless section aligned with the formula content.

## Release 8 local measurements

The flow under test was: open `#/provenance` or its formula deep link → render the formula model first → read full-width notation → continue vertically into collector health and legal notices.

| Evaluated viewport | Evidence | Result |
| --- | --- | --- |
| 1920 | Provenance grid and formula panel `1914px`; notation `1878px`; transparent background, no outer border or box; formula panel bottom `y=2750`, collector begins `y=2751` | **PASS** — one continuous column and exact vertical handoff |
| 1440 | Provenance grid and formula panel `1434px`; notation `1398px`; document x measurement `1440 / 1440` | **PASS** — desktop single column remains fluid |
| 1024 | Provenance grid and formula panel `1018px`; notation `982px`; document x measurement `1024 / 1024` | **PASS** — full-width layout without document horizontal overflow |
| 999 | Provenance grid and formula panel `993px`; notation `957px`; document x measurement `993 / 993` | **PASS** — compact three-card layout owns long-formula overflow internally |
| 768 | Provenance grid and formula panel `762px`; notation `726px`; document x measurement `762 / 762` | **PASS** — formula and notation subgrids collapse to one column |
| 390 | Provenance grid and formula panel `384px`; notation `356px`; document x measurement `384 / 384` | **PASS** — mobile width preserved without overlap or document horizontal overflow |

The local screenshot set is:

- `local-provenance-1920x1080.jpg`
- `local-notation-1920x1080.jpg`
- `local-collector-bottom-1920x1080.jpg`
- `local-provenance-1024x1000.jpg`
- `local-provenance-390x844.jpg`

The browser console result was `[]`. Direct formula deep-link focus passed. At 390px the rendered formula panel retained three display formulas, 24 notation entries, 27 MathML roots, two Red routes, ten clause rows and zero render errors.

## DOM, accessibility and content contract

- Top-level order is formula panel → provenance side content.
- The provenance side retains collector health before legal source notices.
- Formula-card order remains Yellow → Red → Extreme; notation remains after the three-card grid.
- KaTeX remains lazy and retains the audit-expression fallback. There is no route-level Red formula duplication.
- The direct `#/provenance#p0-video-formulas` target still receives focus.
- The old `ANALYSIS CONTRACT` card remains absent; the global footer retains the research-only/non-investment-advice disclaimer.
- Existing source links, freshness, status, clauses, readings and legal language remain present.

## Local automated evidence

- Targeted `src/App.test.tsx`: 27/27 passed, including formula-first top-level order, collector/legal order, deep-link focus, KaTeX counts and invalid-TeX fallback.
- `npm ci`: passed; 125 packages installed and zero vulnerabilities.
- Full Vitest: 59/59 passed across three files.
- `npx tsc --noEmit`: passed.
- Production build: passed; KaTeX remains separate lazy JS/CSS chunks. The existing main-chunk advisory is unchanged.
- Python 3.12 pipeline suite: 486/486 passed.
- `npm audit --omit=dev`: zero vulnerabilities.
- `git diff --check`: passed; schema, pipeline, package/lockfile, types, KaTeX component and `public/data` remain unchanged.

Deployment and live verification subsequently passed and are recorded with exact commit, workflow, asset and data identities in `docs/release-8-qa.md`.

## Release 7 historical baseline

Release 7 implemented the broader responsive redesign and was deployed from implementation `62f4348aaa6c81d2a1427ad3e2955d15f12ca4a1`, followed by generated data `28dcfc187c0e2669ffc8ad062a71382493f60f5c`. Its native-size, six-viewport, interaction, contrast, lazy-KaTeX and live asset/data evidence remains authoritative for that release in `docs/release-7-qa.md`.

The historical Release 7 Provenance contract used `660px / fluid` desktop rails and placed collector/legal content beside formulas. Release 8 intentionally supersedes only that presentation decision. Release 7 evidence for the shared masthead, footer, formula semantics, responsive font floor, chart behavior and unchanged data contract remains useful baseline evidence but does not certify the new single-column deployment.

## Current acceptance boundary

The screenshots, comparison composites, six-width responsive measurements, console result, deep-link check and full local gates pass the requested presentation delta. The matching six-width Pages matrix, live focus/count/contrast checks and byte-identical asset/data verification close the release boundary; exact identities are recorded in `docs/release-8-qa.md`.

final result: passed
