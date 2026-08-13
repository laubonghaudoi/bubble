# Release 8 — Provenance single-column QA record

Date: 2026-08-13

Scope: presentation-only Provenance delta. Make formulas, notation, source/model notes, collector health and legal notices one ordered page column at every width; remove only the notation section's outer box and inset.

Implementation parent: `32a3218d69a38f7560dc9391124ae45d70429e10`

Implementation commit: `24299ab9a52c8beb7502efe131cafd6bc5217437`

Production data commit: `bbc9da325d3299bf9d207370bf64e530f169bb4f`

> Status: **RELEASED / LIVE QA PASSED.** Local gates, credentialed workflow gates, Pages deployment, six-width live layout, accessibility counts, contrast, console, lazy loading and asset/data parity passed.

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

Live rendered screenshots:

- `live-provenance-1440x1000.jpg`
- `live-provenance-390x844.jpg`

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
| Formula-first DOM order | **PASS** | **PASS** — formula panel is the first grid child; collector/legal group follows |
| Collector before legal notices | **PASS** | **PASS** — 11 source rows precede the legal article |
| Three formula / 24 notation / 27 MathML count | **PASS** | **PASS** |
| Two Red routes / ten clauses / zero render errors | **PASS** | **PASS** |
| Direct deep-link focus | **PASS** | **PASS** — `ARTICLE#p0-video-formulas` focused |
| Browser console | **PASS — `[]`** | **PASS — `[]`** |
| Source and model links | **PASS** | **PASS** — 11 collector links and four model/segment links visible and keyboard-focusable |
| Invalid-TeX fallback | **PASS** — targeted regression test | **PASS boundary** — fallback code remains in the deployed bundle; live valid TeX produced zero errors |
| Contrast and 11px visible-font matrix | **PASS** — 1920 / 1024 / 390: minimum 11px and zero computed samples below 4.5:1 | **PASS** — same three widths, minimum 11px and zero samples below 4.5:1 |

## Deployment and live artifacts

- [Push-to-main workflow run `31733780145`](https://github.com/laubonghaudoi/bubble/actions/runs/31733780145): **PASS** in 4m43s; job `94560363083` passed in 4m37s.
- Workflow gates: schema v2 stage fetch/validate/transform, Python 486/486, frontend 59/59, TypeScript/Vite build, atomic promote, data commit, artifact upload and Pages deployment all passed. `npm audit` reported zero vulnerabilities.
- Pages deployment `5894259990`: **PASS** for implementation `24299ab9a52c8beb7502efe131cafd6bc5217437` at [laubonghaudoi.github.io/bubble](https://laubonghaudoi.github.io/bubble/).
- Generated data `bbc9da325d3299bf9d207370bf64e530f169bb4f`: schema `2.2.0`, 40 snapshot/manifest metrics, 40 series, 24 notation items, generated `2026-08-13T19:02:13.285869Z`. The bot commit changes only `public/data/**`.
- Live data are byte-identical to generated `public/data`: snapshot `c0d8c979…4a25`, manifest `5c933ab5…0d0f`, alerts `4cf6b49b…3d91` and events `173cb617…a11`.
- Live frontend is byte-identical to local `dist`: main JS `index-CN_GysBq.js` (`6566f422…19d13`), CSS `index-fa-uZoqz.css` (`389246ec…d365`), lazy KaTeX JS `katex-CiJ_n4H9.js` (`54cd905e…aea00`) and CSS `katex-CUAWePv0.css` (`c8d36b5a…ad312e`). Main/lazy assets and the two used WOFF2 fonts returned HTTP 200 with correct content types.
- Live six-width matrix: `1920 → 1914 / 1878`, `1440 → 1434 / 1398`, `1024 → 1018 / 982`, `999 → 993 / 957`, `768 → 762 / 726`, `390 → 384 / 356` for formula panel / notation width. Every top-level grid has one track and every document scroll width equals client width.
- Fresh live Overview loaded only the main JS/CSS with zero KaTeX DOM or KaTeX stylesheet. Formula navigation loaded the lazy stylesheet and rendered all formula/notation MathML with zero console warning/error.
- Workflow annotation: one non-blocking GitHub runner notice that Node 20 actions are forced onto Node 24. The existing Vite main-chunk-size advisory remains non-blocking.

## Release boundary and remaining risk

- Current evidence passes the requested Provenance presentation delta, all local gates, credentialed staging, Pages deployment and live verification.
- The browser matrix additionally covers 1440, 999 and 768 widths: all retain one top-level column and exact document width; 768 collapses the formula and notation subgrids.
- VoiceOver hands-on output, non-Chromium rendering and unusual browser zoom remain not tested.

Final result: **PASSED / DEPLOYED**
