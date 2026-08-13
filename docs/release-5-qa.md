# Release 5 — P0 video liquidity formula QA record

Date: 2026-08-13<br>
Scope: independent `p0_video_liquidity` decision model, schema `2.1.0` hard cut, formula panel/banner, JSON-driven chart annotations, SRF classification markers, section deep link<br>
Baseline commit: `55e9d3f7b517ccea9f5c0257f1ba5a39f5a08a33`

## Locked contract

- `decision_models.p0_video_liquidity` is a required, exact schema `2.1.0` object. It never rewrites the audited P0 composite, `overall_assessment`, standalone alerts, top pill, or existing switch semantics.
- Video status and data status are separate axes: `GREEN / YELLOW / RED / EXTREME_CONTEXT_REQUIRED / EXTREME_CONFIRMED / UNAVAILABLE` versus `CURRENT / LAST_GOOD / PARTIAL / UNAVAILABLE`.
- The evaluator uses three-valued logic. In particular, `TRUE OR UNKNOWN = TRUE`; an unknown higher-priority Extreme condition only makes the result unavailable when it can change the final status.
- `OK/FRESH` is current; `OK/LATE` and value-bearing `NOT_RELEASED_YET` remain evaluable as last-good; stale, error, not-applicable, missing, or unclassified required data becomes unknown.
- SRF reuses the existing daily aggregation. Technical-only days occupy the latest-three window but do not count positive; mixed days use only alert-eligible accepted amount; fewer than three classified completed days is unknown.
- All chart thresholds are read from the decision-model JSON. No local `3bp` or reserve constants and no chart fallback remain. Annotations never expand the data-derived y domain.
- `enabled:false` still publishes the required envelope as `UNAVAILABLE / DISABLED`, with unknown clauses and no chart annotations.

## Staged publication and automated gates

- Built an offline `manual` group stage from the checked-in last-good full series; no collector network call, JSON hand edit, workflow change, push, or deployment was used.
- `load_stage` revalidated the complete candidate before promotion. The independent stage frontend checkout used exactly that candidate under `public/data` before local atomic promotion.
- Candidate: generated `2026-08-13T08:05:03.154394Z`; audited overall `UNAVAILABLE`; existing alert count `1`; independent video model `GREEN / LAST_GOOD / LOW`; Yellow, Red, and Extreme all false.
- A direct pre/post comparison confirms `overall_assessment`, the complete audited `composite`, snapshot alerts, and standalone alert content are byte-equivalent after removing only schema/generation timestamps.
- Python suite against the candidate and again after promotion: **477 passed**.
- Frontend Vitest after the final integration: **58 passed** across three files. Coverage includes all video statuses and data statuses, 2.0 hard rejection, tampered model rejection, formula copy/routes/source links, deep-link focus, threshold propagation, domain isolation, zero-line dedupe, SRF marker/tooltips, and degraded fallback metadata.
- TypeScript/Vite production build: passed. The pre-existing `>500 kB` chunk advisory remains non-blocking; no new build failure was introduced.
- `git diff --check`: passed. Repository search found no `THRESHOLD_BP`, `thresholdBp`, or local reserve reference-line constant.

## Rendered browser QA

The existing Bloomberg-editorial interface was the visual reference. The new work deliberately reuses its black status bar, square panels, mono data labels, 1px rules, orange action accent, and compact information density.

| Requested viewport | Result |
| --- | --- |
| 1440×1000 | Two 701.5px provenance columns; formula target focused; legal notices span 1404px; no horizontal overflow. Overview banner is 54px high and the original tape/chart/read rail starts immediately below it. |
| 1024×1000 | Two 493.5px columns; collector and formula tops align; legal notices remain full-width; no horizontal overflow. |
| 768×1000 | Single 732px column; formula `order:-1`, collector begins after the formula panel; no horizontal overflow. |
| 390×844 | Single mobile column; formula is first and source links wrap without overflow. Overview banner is the only intended horizontal scroller (`719px` content in a `379px` client box); document width stays within the viewport. |

The in-app browser screenshot API excludes its 6px vertical scrollbar from narrow raster output, so the 768 and 390 captures are 762px and 384px wide respectively; browser `innerWidth` was measured at the requested 768px and 390px.

Rendered interaction/accessibility checks:

- `#/provenance#p0-video-formulas` resolves to Provenance, scrolls to the formula article, and leaves `document.activeElement.id === "p0-video-formulas"`; it does not redirect focus to the route heading.
- Formula prose exposes readable AND/OR descriptions for screen readers, and source/timestamp targets are native links with the three audited timestamp URLs.
- Status is never colour-only: every row prints `MET`, `NOT MET`, `UNKNOWN`, `LAST-GOOD`, `STALE`, or `REVIEW REQUIRED` alongside date, freshness, and basis.
- Measured normal-text contrast on white: `GREEN/MET` **4.51:1**, `LAST-GOOD` **6.86:1**, neutral `NOT MET` **17.04:1**.
- The live SOFR−IORB chart visibly contains the JSON-derived 0bp Yellow condition and +3bp Red line, with the Route A reserve caveat. ARIA describes visible versus out-of-range annotations and last-good state.
- Browser console: zero warnings and zero errors.

## Visual and copy comparison

1. The status bar, five-route navigation, footer ticker, existing three-column overview, and audited `UNAVAILABLE` pill retain their original placement and hierarchy.
2. The banner is inside the route body rather than a fifth `.deck` row, so it does not displace the header/nav/footer or change the desktop grid contract.
3. The formula panel uses existing provenance-panel geometry and typography; Yellow, Red, and Extreme are distinguished by border, heading, formula text, and explicit outcome—not colour alone.
4. At 1024 and above, collector health and formula evaluation remain comparable side by side; at 768 and below, the formula becomes the first item without changing legal notices to a narrow column.
5. Mobile keeps the dense tape and chart workflow intact. Only the compact banner scrolls internally, while the page itself never becomes horizontally scrollable.
6. New copy explicitly separates source rules, dashboard operationalizations, and manual context; identifies last-good data; says that CapEx resonance is outside Red; and repeats that the signal is not a conclusion or trading advice.

Core workflow remains unchanged: open Overview or Liquidity Fuel, inspect live metrics and charts, switch range/overlay/main metric, open methodology/source drawers, and use Provenance for audit detail. The new banner adds a direct audit path without replacing any of those actions.

## Screenshot record

- [1440×1000 overview](qa/release-5/p0-overview-1440x1000.jpg)
- [1024×1000 formula panel](qa/release-5/p0-formulas-1024x1000.jpg)
- [768×1000 formula-first layout](qa/release-5/p0-formulas-768x1000.jpg)
- [390×844 formula-first layout](qa/release-5/p0-formulas-390x844.jpg)
- [390×844 overview banner](qa/release-5/p0-overview-390x844.jpg)

## Explicit boundaries

- This record covers local stage, contract, frontend, production build, local atomic promotion, and rendered browser QA only. It does not authorize or claim a GitHub push, Actions run, Pages deployment, or live-site verification.
- The cited video URL/title and the 23–24, 19–20, and 26–27 minute source ranges follow the approved implementation plan; this release did not perform a new transcript-level verification.
- Current `GREEN / LAST_GOOD / LOW` is the source-formula model result, not the audited P0 overall and not a market or trading conclusion.

final result: passed
