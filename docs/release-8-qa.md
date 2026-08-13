# Release 8 — Provenance single-column QA record

Date: 2026-08-13

Scope: presentation-only Provenance delta. Make formulas, notation, source/model notes, collector health and legal notices one ordered page column at every width; remove only the notation section's outer box and inset.

Implementation parent: `32a3218d69a38f7560dc9391124ae45d70429e10`

Implementation commit: **PENDING — changes are not committed**

Production data commit: **PENDING — deployment has not run**

> Status: **ALL LOCAL GATES PASSED; DEPLOYMENT AND LIVE QA PENDING.** A Release 7 pass is historical evidence, not proof of the changed Release 8 layout.

## Locked scope and contract

- Schema remains `2.2.0`; pipeline, thresholds, formula truth, notation content, freshness, P0 overall, switches, alerts and missing-is-never-zero semantics must not change.
- Provenance top-level order is formula panel → collector/legal group. Within the formula panel, order remains Yellow / Red / Extreme → notation → source/model notes.
- The notation section keeps its two-column internal definition grid where space allows, but its outer container is full width, transparent and unboxed.
- Collector health still precedes legal notices. All source rows, links, statuses, freshness metadata and legal text remain present.
- Formula rendering remains lazy and fallback-safe: three top-level formulas, no route-level Red formula duplication, MathML and Cantonese reading descriptions retained.
- The direct formula hash target and route heading must remain keyboard-focusable. The global footer retains the research-only disclaimer.

## Source truth and visual evidence

User-supplied issue/reference captures:

- `/var/folders/8c/37f47zk10552270psw18r9300000gn/T/codex-clipboard-e1e8878e-2b4f-43d8-93df-eca74bcecb9f.png`
- `/var/folders/8c/37f47zk10552270psw18r9300000gn/T/codex-clipboard-a53d58d0-25ad-4a77-9461-25c04c6ed048.png`

QA artifact directory:

`/var/folders/8c/37f47zk10552270psw18r9300000gn/T/bubble-provenance-release8-qa-2026-08-13`

Combined comparisons:

- `/var/folders/8c/37f47zk10552270psw18r9300000gn/T/bubble-provenance-release8-qa-2026-08-13/comparison-provenance-1920.png` — previous split rail versus formula-first full-width local result.
- `/var/folders/8c/37f47zk10552270psw18r9300000gn/T/bubble-provenance-release8-qa-2026-08-13/comparison-notation-1920.png` — previous inset boxed notation versus full-width transparent local result.

Local rendered screenshots:

- `local-provenance-1920x1080.jpg`
- `local-notation-1920x1080.jpg`
- `local-collector-bottom-1920x1080.jpg`
- `local-provenance-1024x1000.jpg`
- `local-provenance-390x844.jpg`

## Local browser measurements

| Viewport | Single-column evidence | Overflow / runtime | Result |
| --- | --- | --- | --- |
| 1920 | Grid and formula panel `1914px`; notation `1878px`, transparent and without an outer box; formula bottom `y=2750`, collector begins `y=2751` | Console `[]`; direct formula deep-link focus passed | **PASS** |
| 1024 | Grid and formula panel `1018px`; notation `982px` | Document x `1024 / 1024` | **PASS** |
| 390 | Grid and formula panel `384px`; notation `356px` | Document x `384 / 384`; console `[]` | **PASS** |

The 390px formula audit returned three display formulas, 24 notation items, 27 MathML roots, two Red routes, ten clauses and zero `data-render-error` elements. No document-level horizontal overflow was observed at the two measured narrow widths.

## Local automated gates

| Gate | Result |
| --- | --- |
| Targeted App tests | **PASS** — 27/27 `src/App.test.tsx` tests |
| TypeScript | **PASS** — `npx tsc --noEmit` exited 0 |
| Clean dependency install | **PASS** — `npm ci`, 125 packages, zero vulnerabilities |
| Full frontend Vitest suite | **PASS** — 59/59 across three files |
| Production build and lazy asset inspection | **PASS** — separate `katex-CiJ_n4H9.js` / `katex-CUAWePv0.css`; only the existing main-chunk advisory |
| Python 3.12 full pipeline suite | **PASS** — 486/486 |
| Runtime dependency audit | **PASS** — `npm audit --omit=dev`, zero vulnerabilities |
| Data invariance comparison | **PASS** — schema `2.2.0`, 40 metrics / series and 24 notation entries; no pipeline, config, package, type, KaTeX component or `public/data` diff |
| Repository hygiene / final diff audit | **PASS** — `git diff --check`; only expected presentation, test and QA-document paths modified; the two handoff files remain untracked |

## Route and accessibility close-out

| Check | Local | Live |
| --- | --- | --- |
| Formula-first DOM order | **PASS** | **PENDING** |
| Collector before legal notices | **PASS** | **PENDING** |
| Three formula / 24 notation / 27 MathML count | **PASS** | **PENDING** |
| Two Red routes / ten clauses / zero render errors | **PASS** | **PENDING** |
| Direct deep-link focus | **PASS** | **PENDING** |
| Browser console | **PASS — `[]`** | **PENDING** |
| Source and model links | Content retained; final interaction audit **PENDING** | **PENDING** |
| Invalid-TeX fallback | Existing targeted test passed; production-build check **PENDING** | **PENDING** |
| Contrast and 11px visible-font matrix | **PASS** — 1920 / 1024 / 390: minimum 11px and zero computed samples below 4.5:1 | **PENDING** |

## Deployment and live artifacts

- Push-to-main workflow run: **PENDING — URL, run id, status and duration**.
- Implementation SHA deployed to Pages: **PENDING**.
- Generated-data SHA and schema/generation timestamp: **PENDING**.
- Workflow Python, frontend and build gates: **PENDING**.
- Live `index.html`, main JS/CSS and lazy KaTeX asset identity: **PENDING**.
- Live snapshot, manifest, alerts and events parity with generated `public/data`: **PENDING**.
- Live 1920, 1024 and 390 Provenance measurements: **PENDING**.
- Live formula counts, focus, overflow, contrast, console and link checks: **PENDING**.

## Release boundary and remaining risk

- Current evidence passes the requested local Provenance presentation delta and all local release gates.
- Credentialed data staging, Pages deployment and live verification remain pending.
- The browser matrix additionally covers 1440, 999 and 768 widths: all retain one top-level column and exact document width; 768 collapses the formula and notation subgrids.
- Any source edit after these measurements requires the affected local checks to be repeated.

Final result: **LOCAL PASSED / RELEASE PENDING**
