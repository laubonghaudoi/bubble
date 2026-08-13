# Release 6 — KaTeX formula presentation and schema 2.2 QA record

Date: 2026-08-13<br>
Scope: KaTeX formula presentation, Cantonese readings, shared notation and rule provenance, schema `2.2.0` hard cut<br>
Implementation parent: `90eb92cc9d549c751d45c090305e1d1c6c263e2f`<br>
Implementation commit: `cc369beaba9e4056c2c22a1c9fbcd326503693c4`<br>
Production data commit: `f99b3245790e88864567680f070171192cd2633c`

## Locked contract

- Schema `2.2.0` is a hard cut. Python publication validation and the frontend loader reject `2.1.0` and earlier artifacts rather than filling display fields or notation defaults.
- Yellow, Red, and Extreme top-level evaluations require exact non-empty `expression`, `display_tex`, `plain_language`, `triggered`, and `clauses` fields. The original expression remains the audit and render-error fallback.
- Red Route A/B retain only `route_id`, `label`, `expression`, `triggered`, and `clauses`; the page renders one combined Red formula rather than duplicate route-level formula blocks.
- Model notation contains exactly 24 ordered, unique keys: 14 mathematical symbols, five `VIDEO_SOURCE_RULE` items, four `DASHBOARD_OPERATIONALIZATION` items, and one `MANUAL_CONTEXT` item.
- Formula text, TeX, readings, notation, route expressions, clause thresholds, and reserve chart references derive from the same configured thresholds. Semantic publication validation recomputes and rejects altered presentation content.
- KaTeX is presentation-only. The audited P0 composite, `overall_assessment`, switches, alerts, model truth values, and status-priority logic remain unchanged.

## Automated and data gates

- Python 3.12 full suite against the final local publication: **486 passed**. Targeted formula/config/contract suites: **87 passed**.
- The old and new evaluators were compared over 2,000 deterministic boundary, quality, context, and SRF cases. Status, formula truth, clause current values, thresholds, and evaluation states matched throughout.
- The config mutation test moves streak `3→4`, reserve levels `2.9→2.85`, `2.8→2.75`, `2.5→2.45`, TGA floor `0.95→0.93`, spread `3→4.25`, and SRF `2/3→3/4`; clause, expression, TeX, reading, notation, route, and chart reference checks move together.
- Frontend Vitest: **59 passed** across three files. Coverage includes real `.katex` and MathML output, the three top-level formulas, 24 notation entries, valid reading descriptions, no Red route formula duplication, invalid-TeX fallback, strict schema loading, and section deep-link focus.
- TypeScript/Vite production build passed. KaTeX remains a lazy `258.63 kB` JavaScript chunk plus a lazy `29.38 kB` stylesheet; it is absent from a fresh Overview load. Runtime `npm audit --omit=dev` reported zero vulnerabilities.
- Final local `public/data` contains 40 schema `2.2.0` series and four schema `2.2.0` top-level artifacts. Excluding schema/run metadata, all 40 series were unchanged from the prior publication; overall, switches, composite, alerts, thresholds, operationalizations, and formula outcomes were unchanged.
- `git diff --check` passed.

## Production deployment and live artifacts

- [Update data and deploy Pages run `31722039301`](https://github.com/laubonghaudoi/bubble/actions/runs/31722039301) completed successfully in 4m14s. It ran credentialed live collectors, **486 Python tests**, an independent `npm ci` with zero vulnerabilities, **59 Vitest tests**, the production build, atomic promotion, generated-data commit, Pages upload, and Pages deployment.
- The workflow generated `f99b324` and deployed the Pages artifact for implementation commit `cc369be`. The sole workflow annotation was GitHub's non-blocking action-runtime Node 20 deprecation notice.
- The live snapshot at [laubonghaudoi.github.io/bubble](https://laubonghaudoi.github.io/bubble/) is schema `2.2.0`, generated `2026-08-13T16:42:52.635431Z`, with 40 metrics, 24 notation entries, and all three required TeX/readings. Snapshot, manifest, and alerts are byte-identical to `public/data` at `f99b324`.
- Live `index-Db7oyyZf.js`, `index-DdGfLsEd.css`, lazy `katex-CiJ_n4H9.js`, and lazy `katex-CUAWePv0.css` all return HTTP 200. The KaTeX assets are 258,634 and 29,382 bytes respectively; the two fonts used by the rendered formulas also return HTTP 200.
- Live state at verification: audited overall `UNAVAILABLE`; independent video model `GREEN / LAST_GOOD / MEDIUM`; Yellow, Red, Extreme candidate, and Extreme confirmed all false. The existing single standalone alert remains present.

## Local and live rendered browser QA

The final local build and the deployed Pages site were each checked at 1440×1000, 1024×1000, 768×1000, and 390×844.

| Viewport | Live document width | Formula panel width | Yellow / Red / Extreme client=scroll width |
| --- | ---: | ---: | --- |
| 1440×1000 | 1440/1440 | 702/702 | 630, 630, 629px |
| 1024×1000 | 1024/1024 | 494/494 | 422, 422, 421px |
| 768×1000 | 762/762 | 732/732 | 660, 660, 659px |
| 390×844 | 384/384 | 384/384 | 324, 324, 323px |

Every live viewport passed the following checks:

- Three rendered display formulas, 24 rendered notation items, and 27 matching MathML trees; zero `data-render-error` elements.
- Three valid `aria-describedby` reading targets. Extreme reading preserves separate candidate and confirmed lines.
- Two Red routes with no route-level KaTeX; all ten clause rows remain visible and retain current values, state, dates, freshness, basis, and notes.
- Zero document, panel, notation, formula, or clause horizontal overflow. The 390px Route B row uses a full-width label followed by non-overlapping value/status columns.
- Four source links are visible, keyboard-focusable, and HTTP 200. The section deep link focuses `ARTICLE#p0-video-formulas`.
- Notation uses four semantic definition lists; all 24 items have direct `dt` and `dd` children. Each rendered root contains exactly one KaTeX tree and no exposed raw fallback text.
- Browser console warnings and errors: zero.

A fresh live Overview at 1440×1000 has no document scroll, no KaTeX DOM, and no KaTeX JS/CSS/font request. Activating the formula banner navigates and focuses the section, then lazy-loads the hashed KaTeX JavaScript, stylesheet, and two fonts before producing all 27 KaTeX/MathML instances.

## Explicit boundaries

- This release changes representation and the publication contract only. It does not change Yellow, Red, Extreme, alert, switch, or overall decision results.
- Real MathML and `aria-describedby` were verified in Chromium's accessibility tree; a separate hands-on VoiceOver session was not performed.
- A failed first KaTeX dynamic import stays on the plain-expression fallback for the lifetime of that page load; reloading retries the asset request. The fallback path is covered by Vitest.
- The existing main application chunk remains above Vite's 500 kB advisory threshold. KaTeX itself is isolated in a separate lazy chunk and does not increase the fresh Overview payload.

final result: passed
