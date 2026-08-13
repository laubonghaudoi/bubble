# Release 7 — Responsive dashboard redesign QA record

Date: 2026-08-13

Scope: responsive presentation redesign only; merged masthead and tape header, denser desktop rails, chart-height repair, route-specific evidence hierarchy and compact Provenance formulas.

Implementation parent: `3c470a25ff93e8c4842dfe9b047fe797d93fff5f`

Approved handoff SHA-256: `0c456951d89da27f16b5bccf5f1bbd26563186b74044880f1ae8550f5cd3c55a`

Implementation notes SHA-256: `058cac0eac8f7affc74b2fc4accec1965e5ebe8f2128e8d26c726e9da1a33f09`

Implementation commit: **PENDING — changes are not committed**

Production data commit: **PENDING — deployment has not run**

> Status: **LOCAL AUTOMATED AND BROWSER GATES PASSED; DEPLOYMENT PENDING.** The final local build has completed native-size comparison, responsive, interaction, contrast, console and production-preview asset checks. Live verification is recorded after the deployment workflow.

## Locked scope and contract

- Schema remains `2.2.0`. No pipeline, config, threshold, formula truth, freshness, P0 overall, switch, alert or missing-is-never-zero logic changed.
- Header contains one semantic route navigation between brand and status cluster. Overview uses one combined LIVE TAPE header.
- At 1440px and wider, Overview is a fixed-viewport three-column deck with a `400–460px` left rail, fluid chart column and `380–476px` right rail. At 1000–1439px it remains a compact three-column deck. At 999px and below it becomes a one-column document flow.
- Visible UI text has an 11px floor. Hidden accessibility text, KaTeX's hidden MathML tree and mathematical super/subscripts are excluded from the visual font audit.
- Provenance orders Yellow, Red and Extreme before notation and model/source notes. Collector health and two-column legal notices occupy the companion rail. The old `ANALYSIS CONTRACT` card is removed; the footer retains the research-only/non-investment-advice disclaimer.
- KaTeX remains lazy, reads schema-provided TeX, exposes MathML and Cantonese readings, and falls back to the audit expression on render/import failure. Red Route A/B retain outcomes and clauses without duplicate route-level formulas.

## Local automated and data gates

| Gate | Result |
| --- | --- |
| Clean dependency install | **PASS** — `npm ci` exited 0 |
| Python 3.12 full suite | **PASS** — Python 3.12.13, 486/486 pipeline tests passed |
| Frontend Vitest | **PASS** — 59/59 tests across three files |
| TypeScript | **PASS** — `npx tsc --noEmit` exited 0 |
| Production build | **PASS** — `npm run build` exited 0; only the existing main-chunk advisory remains |
| Lazy build output | **PASS** — main `index-C1bLCx9d.js` 1,476,200 bytes / `index-BBnGSSnq.css` 52,584 bytes; separate `katex-CiJ_n4H9.js` 258,634 bytes / `katex-CUAWePv0.css` 29,382 bytes |
| Runtime dependency audit | **PASS** — `npm audit --omit=dev` reported 0 vulnerabilities |
| Data invariance scope audit | **PASS** — no `pipeline/`, config, schema or `public/data` path is modified; schema remains `2.2.0` |
| Visible font static audit | **PASS** — zero CSS or ECharts visible-font declarations below 11px; degraded SRF chart label has an exact 11px regression test |
| Repository hygiene | **PASS** — `git diff --check`; no staged files. The two handoff inputs remain untracked and must not be included in the release commit |

The local build still has no implementation commit identity. Asset filenames must be regenerated and recorded again if any source changes before commit.

## Native-size reference and responsive browser QA

QA artifact directory:

`/var/folders/8c/37f47zk10552270psw18r9300000gn/T/bubble-redesign-release7-qa-2026-08-13`

The preliminary pass-three route matrix covered all five routes plus `#/provenance#p0-video-formulas` at all six widths. `doc` values below are `clientWidth / scrollWidth / clientHeight / scrollHeight`.

| Viewport | Final local evidence | Local close-out | Live |
| --- | --- | --- | --- |
| 2560×1440 | **PASS** — Overview `460 / 1622 / 476`; doc `2560 / 2560 / 1440 / 1440`; canvases `1622×614`, `1622×491` | 11px minimum; no x overflow or console error | **PENDING** |
| 1920×1080 | **PASS** — native handoff tracks `460 / 982 / 476`; doc `1920 / 1920 / 1080 / 1080`; 54px masthead, 56px banner, 34px footer | Native side-by-side visual comparison passed | **PENDING** |
| 1440×1000 | **PASS** — tracks `460 / 502 / 476`; doc `1440 / 1440 / 1000 / 1000`; canvases fill both chart slots | All five routes: 11px minimum, zero contrast failure | **PENDING** |
| 1024×1000 | **PASS** — compact tracks `311.8 / 398.4 / 311.8`; doc `1024 / 1024 / 1000 / 1000` | All five routes: 11px minimum, zero contrast failure | **PENDING** |
| 768×1000 | **PASS** — stacked flow; doc `762 / 762 / 1000 / 2812`; vertical scroll is intended | All routes have zero document x overflow | **PENDING** |
| 390×844 | **PASS** — stacked flow; doc `384 / 384 / 844 / 3357`; no document-level horizontal overflow | All five routes: 11px minimum, zero contrast failure | **PENDING** |

All final targets reported zero visible elements below 11px and exactly one active route item. Desktop Overview height equalled the viewport. At 768px and 390px, document height exceeded the viewport by design while scroll width equalled client width. Long mobile formulas use their own horizontal scroll owner.

The earlier `local-contrast-matrix.json` is a pass-two defect artifact, not final evidence. `local-contrast-matrix-final.json` is the final computed-style scan: all five routes at 1440×1000, 1024×1000 and 390×844 had a visible 11px minimum and zero text samples below 4.5:1. The repair maps faint/unavailable copy to `#545454` and route numbers to `#8A4A00`; static ratios are 7.57:1 on white, 7.13:1 on `#F8F8F8`, and 6.86:1 on white respectively.

## Three visual comparison passes

1. **Pass 1 — structure:** found and fixed the extra tape header, separated masthead/navigation, Market/Fundamental evidence ordering, missing evidence rail and global overflow masking. Native reference and implementation screenshots were compared side by side without scaling.
2. **Pass 2 — compact/mobile:** found and fixed 390px footer/read-rail overflow, clipped 1440px readout, cramped formula outcomes, compact Fundamental width and the contrast combinations above.
3. **Pass 3 — final browser matrix:** six viewports across five routes plus formula deep link showed zero document-level horizontal overflow, an 11px minimum and no known visual blocker. The independent contrast, console, deep-link focus, interaction and production-preview asset close-out also passed.

## Route and interaction matrix

| Flow | Local evidence | Live |
| --- | --- | --- |
| `#/overview` | **PASS** — one masthead nav, one tape header, full-height chart slots, tape selection and one active route item | **PENDING** |
| `#/liquidity-fuel` | **PASS** — hero → P0 banner → five confirmation spreads → chart → evidence; all eight metric tabs and six ranges became uniquely pressed; canvases matched parent sizes; OBFR/TGCR overlays toggled and restored | **PENDING** |
| `#/market-ignition` | **PASS** — CFTC → fragility → rights-gated → P2 held order; four CFTC cards, two fragility cards and twelve rights holds retained | **PENDING** |
| `#/fundamental-exit` | **PASS** — fluid main / 640px evidence layout; four companies and three manual cards retained; mobile collapse measured | **PENDING** |
| `#/provenance` | **PASS** — collector/legal rail plus formula rail; old Analysis Contract absent; 11 source links visible/focusable | **PENDING** |
| `#/provenance#p0-video-formulas` | **PASS** — direct load and forward navigation focus `ARTICLE#p0-video-formulas`; Back restores Overview route/heading | **PENDING** |
| Footer/drawers/interactions | **PASS** — JSON download equals the publication hash; source/methodology dialogs, Shift+Tab wrap, Escape, body-scroll restore and trigger focus restore verified | **PENDING** |

The chart close-out exercised all eight Liquidity tabs and all six ranges after the last source change. Every selected state retained non-zero canvases equal to its parent slot, including SRF and RESERVES reference states, without an unused lower grid row.

## KaTeX lazy-load and accessibility gate

- Formula DOM: **PASS** — three display formulas, 24 notation items, 27 MathML roots, three valid reading descriptions, two Red routes, ten clauses, zero route-level formula duplicates and zero `data-render-error` elements.
- Invalid TeX: **PASS in Vitest** — audit-expression fallback appears with `data-render-error="true"` and the page remains usable.
- Lazy bundle isolation: **PASS in build** — KaTeX JS and CSS remain separate hashed chunks.
- Fresh Overview zero-request browser check: **PASS** — zero KaTeX DOM/MathML and zero KaTeX JS/CSS/font assets.
- Production-preview formula navigation: **PASS** — hashed KaTeX JS/CSS and two used WOFF2 fonts loaded; the page-asset bundle fetched 5/5 with zero failures.
- Deep-link focus and links: **PASS** — section focus, three valid reading idrefs, 11 source links and four formula/model links are visible and keyboard focusable. Five unique official source destinations returned HTTP 200.
- Console: **PASS** — local development, clean lazy-load and production-preview flows each returned zero warnings/errors.

## Browser evidence

- Native handoff screenshot: `reference-overview-1920x1080.png`.
- Native implementation screenshot: `local-overview-final-1920x1080.jpg`.
- Native side-by-side comparison: `comparison-final-overview-1920x1080.jpg`.
- Responsive Overview screenshots: `local-overview-final-{2560x1440,1440x1000,1024x1000,768x1000,390x844}.jpg`.
- Focused route evidence: `local-market-final-1440x1000.jpg`, `local-fundamental-final-1440x1000.jpg`, `local-formulas-final-1440x1000.jpg`.
- DOM and contrast reports: `local-route-matrix-final.json`, `local-contrast-matrix-final.json`.
- Interaction reports: `local-liquidity-interactions-final.json`, `local-drawer-interactions-final.json`, `local-deeplink-history-final.json`.
- Lazy/network reports: `local-katex-lazy-final.json`, `preview-katex-assets-final.json`; final browser console arrays were empty.
- Final live screenshots and report: **PENDING**.

## Production deployment and live artifacts

- Update and deploy workflow run: **PENDING — URL, run id, status and duration**.
- Pages deployment and implementation SHA: **PENDING**.
- Generated-data SHA and live schema/generation timestamp: **PENDING**.
- Live `index.html` hashed JS/CSS compared with final `dist`: **PENDING**.
- Live snapshot, manifest, alerts and events compared with generated `public/data`: **PENDING**.
- Main JS/CSS, lazy KaTeX JS/CSS and used KaTeX fonts return HTTP 200: **PENDING**.
- Five live routes plus formula deep link, console/network and cache-busted asset checks: **PENDING**.

## Explicit boundaries and remaining risk

- Local unit/build success and final browser matrix are not a substitute for live verification.
- The design handoff uses hardcoded presentation data; production schema data and accessible interaction behavior remain authoritative.
- VoiceOver hands-on output, non-Chromium rendering and unusual browser zoom remain **PENDING / NOT TESTED**.
- The existing main application chunk remains above Vite's 500kB advisory. KaTeX stays isolated from the fresh Overview chunk.
- The implementation is uncommitted, so any further source edit invalidates the recorded local asset hashes and requires affected gates to run again.

Final result: **LOCAL PASS — commit, deployment and live verification outstanding**
