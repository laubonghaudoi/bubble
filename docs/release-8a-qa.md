# Release 8A（合併 8C）— Selected Metric Interpreter QA record

Date: 2026-08-13

Scope: upgrade the Overview read rail from a mostly static summary into a pipeline-generated, source-backed selected-metric interpreter for all 13 LIVE TAPE metrics; include Release 8C statistical classifications without changing any alert or formula outcome.

Implementation parent: `a8cb7cdf1f987e1e493b6c3b1023b93e88ad2475`

Implementation commit: `035fb05b89e569c8c3a0b083e5c2b52ba1fdad04`

Production data commit: `2990e565b233d5ecb3cbd1bb8bd21336e6d3291c`

> Status: **RELEASED. LOCAL, WORKFLOW, GENERATED-DATA, PAGES AND LIVE BROWSER GATES PASSED.** No earlier release result certifies this schema or interpretation layer.

## Locked scope and publication contract

- Global schema is a hard cut to `2.3.0`; code, every config, staged/public artifacts, series, fixtures, strict Python validators and strict TypeScript loaders must agree. Schema `2.2.0` remains rejected.
- Every snapshot metric has a required `interpretation` key. The 17 canonical P0 records are non-null: 13 LIVE TAPE metrics plus EFFR／OBFR／TGCR／BGCR relative-to-IORB confirmation spreads. Every remaining interpretation, including other P0 rights-gated records and all P1/P2/P3 records, is exactly `null`.
- A non-null interpretation contains exactly `role`, `classification_type`, `data_state`, `numeric_direction`, `impact`, `state`, `severity`, `confidence`, `headline`, `what_it_measures`, `current_reasons`, `next_boundary`, typed `views`, `confirm_with`, `cannot_infer` and `rule_basis`.
- Roles are limited to `PRIMARY_FUNDING_PRICE`, `POLICY_RATE_ANCHOR`, `POLICY_ANCHORED_MARKET_RATE`, `CONFIRMATION_SPREAD`, `TREASURY_CASH_FLOW`, `LIQUIDITY_BUFFER`, `BACKSTOP_FACILITY`, `RESERVE_STOCK`, `BALANCE_SHEET_DRIVER` and `CROSS_CHECK`.
- Classification types are limited to `NO_HARD_THRESHOLD`, `SOURCE_PLUS_OPERATIONAL`, `SOURCE_PLUS_STATISTICAL`, `ROLLING_PERCENTILE`, `EVENT_TRIGGER`, `DIRECTIONAL` and `CROSS_CHECK`.
- Data state is `CURRENT | LAST_GOOD | STALE | UNKNOWN`; numeric direction is `RISING | FALLING | FLAT | UNKNOWN`; impact is `EASING | TIGHTENING | NEUTRAL | AMBIGUOUS | POLICY_ANCHOR | UNKNOWN`; severity is `NORMAL | WATCH | YELLOW | RED | EXTREME | CONTEXT_ONLY | UNKNOWN`; confidence is `HIGH | MEDIUM | LOW | UNKNOWN`. Metric-specific `state` remains a non-empty string.
- `views` is a non-empty discriminated union of `REGIME_LADDER`, `PERCENTILE_GAUGE`, `EVENT_STEPPER`, `BREADTH_COUNTER`, `DIRECTIONAL` and `CROSS_CHECK`. Every view and its ladder rows／breadth members use the frozen exact field set, and each metric must use its configured primary view. `next_boundary` is either null or exact `{label,current,threshold,distance,unit,rule,basis}`. `current_reasons` and unique `rule_basis` are non-empty.
- `rule_basis` is one of `VIDEO_SOURCE_RULE`, `DASHBOARD_OPERATIONALIZATION`, `STATISTICAL_BAND` or `CONTEXT_ONLY`. `VALIDATED_SIGNAL` is forbidden.
- The pipeline is the sole classification authority. React selects and renders the schema record; it does not calculate a band, next boundary, state, severity or fallback interpretation.
- Existing `methodology` and source/provenance fields remain authoritative and available from the selected-metric detail surface.

## Methodology and no-lookahead contract

- New statistical bands use all available prior history as an expanding window.
- The evaluated endpoint is excluded. Observations after that endpoint cannot affect its band, boundary or classification.
- Threshold percentiles use deterministic nearest-rank: sorted prior value at one-indexed `ceil(q × n)`. Reported percentile is the empirical CDF `count(prior ≤ current) / n`. Daily classifications need at least 60 prior valid observations; weekly classifications need at least 104. ON RRP is the only non-expanding exception: it uses the 20 valid observations strictly before the endpoint, needs all 20 and uses the bottom-decile boundary `q = 0.10`.
- Insufficient history, stale/missing data or incomplete SRF technical classification remains explicit and cannot collapse to neutral, current or zero.
- New statistical views cover interpreter context such as TGA flow, confirmation-spread position/breadth and Fed-assets four-week impulse. They explain state and next boundary; they do not create a new alert engine.

Required invariants:

- P0 `overall_assessment`, `switches.liquidity_fuel`, `composite`, `snapshot.alerts` and standalone `alerts.json` are unchanged for identical inputs.
- The source-specific `p0_video_liquidity` status, Yellow／Red／Extreme `triggered` values, Extreme candidate/context state, clauses, Red routes, thresholds, TeX and notation are unchanged.
- The source-specific Extreme rapid-decline rule remains trailing-five-year p10. An expanding interpreter percentile must not replace it.
- The audited P0 alert engine and the interpreter breadth both use exactly EFFR／TGCR／BGCR as independent confirmation spreads. OBFR has its own gauge/context and must not enter breadth or alter alert confirmation count or severity.
- TGA、ON RRP、Fed assets、historical percentiles and technical flags remain context unless an existing audited rule explicitly says otherwise.

## Contract and methodology QA

| Check | Required evidence | Result |
| --- | --- | --- |
| Exact 2.3 hard cut | Python/config/fixtures/frontend agree; 2.2 snapshot rejected | **PASS — strict config, pipeline and frontend contract tests** |
| Required interpretation key | Every metric has key; exactly 17 P0 non-null; all others null | **PASS — generated publication has 40 metrics / 17 interpretations** |
| Exact field and enum validation | Missing/extra field, wrong enum, invalid basis and `VALIDATED_SIGNAL` fail closed | **PASS — controlled tamper tests** |
| Typed views | Every kind accepts only its exact shape; each metric uses its configured primary view; unrelated keys fail closed | **PASS — six view kinds and primary-view reconciliation tested** |
| Expanding-history calculation | Deterministic nearest-rank using only prior valid history | **PASS — tie and null-gap counterexamples included** |
| Minimum samples | Daily 59→insufficient / 60→classified; weekly 103→insufficient / 104→classified | **PASS** |
| ON RRP exception | Prior-only 19→insufficient / 20→classified; evaluated endpoint is excluded | **PASS — including prior-window null gap** |
| Prefix invariance | Appending future observations cannot change earlier interpretation records | **PASS** |
| Missing/stale/last-good | State, reasons, confidence and boundary remain evidence-consistent; no missing-as-zero | **PASS — `ERROR` remains unknown and stale/last-good remain distinct** |
| Alert/formula invariance | Composite, alerts and all source-video truth values match the pre-interpreter baseline | **PASS — independent structured comparison with parent publication** |
| Snapshot/series reconciliation | Interpretation values and statistical views recompute from the corresponding full series | **PASS — strict publication recomputation** |

## Local automated gates

| Gate | Result |
| --- | --- |
| Clean dependency install (`npm ci`) | **PASS — 125 packages installed** |
| Python 3.12 full pipeline suite | **PASS — 517 tests** |
| Frontend Vitest | **PASS — 62 tests** |
| TypeScript (`npx tsc --noEmit`) | **PASS** |
| Production build | **PASS — KaTeX remains a separate lazy JS/CSS chunk** |
| Runtime dependency audit | **PASS — 0 vulnerabilities** |
| Generated-publication/schema inspection | **PASS — 2.3.0, 40 series, exactly 17 interpretations** |
| Alert/formula before/after invariance artifact | **PASS — observations, alerts, switches and formula truth unchanged** |
| Repository hygiene and `git diff --check` | **PASS — user handoff files remain untracked and excluded** |

## Local browser QA

QA artifact directory: `/var/folders/8c/37f47zk10552270psw18r9300000gn/T/bubble-interpretation-qa-2026-08-13/`

| Viewport / flow | Required evidence | Result |
| --- | --- | --- |
| Desktop Overview | Three-column fixed deck retained; read rail shows selected metric without clipping | **PASS — 1440×1000 document equals viewport** |
| Compact 1024px | Compact three-column layout retained; interpreter content remains readable and internally scrollable | **PASS — 1024×1000** |
| 768px / 390px | Single-column flow; no document-level horizontal overflow; long content wraps | **PASS — client width equals scroll width at both sizes** |
| All 13 tape rows | Each row selects the same main chart metric and the matching interpretation record | **PASS** |
| All 13 chart tabs | Each tab selects the matching tape row/read rail; exactly one active selection | **PASS** |
| Interpretation semantics | Role/state/headline, current reasons, boundary, confirmation and cannot-infer text agree with staged JSON | **PASS — all six typed view kinds exercised** |
| Methodology/provenance detail | Source links and methodology remain keyboard reachable; drawer focus/close restore passes | **PASS — Escape and trigger-focus restore verified** |
| Accessibility | 11px visible-font floor, ≥4.5:1 text contrast, semantic headings/status, keyboard operation | **PASS — all 13 interpreter states checked at 1440/390** |
| Runtime | Console/network errors empty; chart resize and range/overlay controls remain functional | **PASS — console empty; canvas/container parity, 6 ranges and overlays retained** |

## Deployment and live close-out

- Push-to-main workflow run: [31746304414](https://github.com/laubonghaudoi/bubble/actions/runs/31746304414), **success**, 2026-08-13 21:35:08Z–21:40:16Z.
- Workflow collector/stage, Python, staged-data frontend test/build, revalidation, atomic promote, generated-data commit, artifact upload and Pages deployment: **all steps passed**.
- Implementation SHA deployed to Pages: `035fb05b89e569c8c3a0b083e5c2b52ba1fdad04`.
- Generated-data SHA: `2990e565b233d5ecb3cbd1bb8bd21336e6d3291c`; schema `2.3.0`; generated `2026-08-13T21:35:27.822558Z`.
- Pages deployment: `5896469142`, state `success`, bound to implementation SHA.
- Cache-busted live snapshot／manifest／alerts／events and all 40 full-series files are byte-identical to generated `public/data`; snapshot has 40 metrics and exactly 17 interpretations.
- Live `index-17ICY1kD.css`, `index-C5qmfnv1.js`, lazy `katex-CUAWePv0.css`, `katex-CiJ_n4H9.js` and KaTeX main font return HTTP 200 with the expected content type.
- Live five-route focus matrix and responsive Overview／interpreter checks passed at 1440×1000 and 390×844; document horizontal overflow is zero and chart canvases match their containers.
- Live 13/13 row／tab selection, six typed views, drawer focus restore, 11px font floor, semantic contrast, source links and console checks passed. Fresh Overview loads no KaTeX DOM; Provenance renders 3 display formulas, 24 notation items and 27 MathML nodes with zero render errors.

## Known risks and release boundary

- Passing self-authored validators is not enough: controlled threshold, minimum-sample, future-append and tamper tests must prove the interpretation semantics.
- A visually plausible headline cannot compensate for a mismatched data state, boundary, basis label or source series.
- Statistical bands are descriptive history-relative context, not causal evidence or validated trading signals.
- Earlier Release 8 live QA remains evidence for the Provenance layout only; it does not certify schema `2.3.0`, new interpreter output or unchanged alerts under the new pipeline.
- Until all local gates, credentialed workflow gates, generated-data parity and live browser checks pass, Release 8A/8C remains unreleased.

Final result: **PASSED**
