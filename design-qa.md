# USD Liquidity Dashboard — Release 7 responsive redesign QA

Date: 2026-08-13

Scope: presentation-only implementation of the approved responsive dashboard handoff. This record covers the local design comparison; deployment and live-artifact acceptance remain in `docs/release-7-qa.md`.

## Source of visual truth

- Approved handoff: `bubble-dashboard-redesign.html`, SHA-256 `0c456951d89da27f16b5bccf5f1bbd26563186b74044880f1ae8550f5cd3c55a`.
- Implementation notes: `IMPLEMENTATION-NOTES.md`, SHA-256 `058cac0eac8f7affc74b2fc4accec1965e5ebe8f2128e8d26c726e9da1a33f09`.
- Native reference canvas: 1920×1080. The handoff is authoritative for desktop hierarchy, density, rails, flat palette and type scale; its static 1920px canvas is not a tablet or mobile overflow oracle.
- Implementation parent: `3c470a25ff93e8c4842dfe9b047fe797d93fff5f`.
- Local QA artifacts: `/var/folders/8c/37f47zk10552270psw18r9300000gn/T/bubble-redesign-release7-qa-2026-08-13`.

The handoff contains hardcoded example data and state-only controls. Production hash routing, schema `2.2.0` data, KaTeX fallback, accessible names and working interactions remain authoritative where the reference differs.

## Native-size comparison

The 1920×1080 reference and implementation were captured at native size without scaling:

- Reference: `reference-overview-1920x1080.png`.
- Implementation: `local-overview-final-1920x1080.jpg`.
- Side-by-side: `comparison-final-overview-1920x1080.jpg` (3840×1080; implementation was top-left padded by the browser's 20px screenshot gutter, never scaled).

The final layout contract matches the handoff: 54px merged masthead/navigation, 56px P0 banner, 34px footer, 34px tape rows, 70×22 sparklines, 52px primary readout and square, flat editorial surfaces. At 1920px the Overview body tracks are exactly `460px 982px 476px`, matching the reference target. Both main and overlay ECharts canvases fill their parent slots rather than retaining the former unused lower area.

## Responsive measurements

The pass-three route matrix exercised all five routes plus the formula deep link. `doc` records `clientWidth / scrollWidth / clientHeight / scrollHeight`; a matching first pair means no document-level horizontal overflow.

| Evaluated viewport | Overview tracks | Document measurement | Chart canvases | Result |
| --- | --- | --- | --- | --- |
| 2560×1440 | `460 / 1622 / 476` | `2560 / 2560 / 1440 / 1440` | `1622×614`, `1622×491` | Fluid centre; fixed rails; no document scroll |
| 1920×1080 | `460 / 982 / 476` | `1920 / 1920 / 1080 / 1080` | `982×414`, `982×331` | Native handoff structure matched |
| 1440×1000 | `460 / 502 / 476` | `1440 / 1440 / 1000 / 1000` | `502×289`, `502×231` | Desktop minimum retained without clipping |
| 1024×1000 | `311.8 / 398.4 / 311.8` | `1024 / 1024 / 1000 / 1000` | `398×262`, `398×210` | Compact three-column deck; toolbar wrapping retained |
| 768×1000 | one column | `762 / 762 / 1000 / 2812` | `762×360`, `762×260` | Intended stacked document flow; vertical scroll only |
| 390×844 | one column | `384 / 384 / 844 / 3357` | `384×320`, `384×220` | Intended mobile flow; no document-level horizontal overflow |

The 768px and 390px client widths exclude the browser scrollbar gutter. The 390px page therefore correctly measures `384px` client and `384px` scroll width. Formula overflow at this size is owned by the formula container; long KaTeX content can scroll internally without widening the document.

Across the final six-viewport by six-target matrix (`local-route-matrix-final.json`):

- Every route had exactly one active navigation item.
- Overview remained fixed-height from 1024px upward and stacked only at `999px` and below.
- Fundamental Exit used a fluid main column plus a 640px evidence column on desktop and collapsed to one column below 1000px.
- Provenance used `660px / fluid` columns from 1280px upward, then one page column; formulas remained three-up and notation two-up until the 768px collapse.
- Formula output contained three display formulas, 24 notation items, 27 MathML roots, three reading descriptions, two Red routes, ten clause rows, zero route-level formula duplicates and zero render errors.

## Three comparison passes

### Pass 1 — structural match

The native comparison found an extra LIVE TAPE header row, route navigation outside the masthead, route-section ordering drift, and global overflow masking that could conceal a real width defect. Market Ignition also placed rights-gated material before quantitative fragility evidence, while Fundamental Exit had not separated its company/manual evidence rail.

The implementation merged the masthead and navigation, merged the tape title with column labels, removed global overflow masking, restored route order, and added explicit Liquidity, Market, Fundamental and Provenance layout hooks.

### Pass 2 — compact and mobile repair

The second pass found 390px footer/read-rail overflow, a clipped 1440px readout, cramped formula outcomes, an over-wide compact Fundamental layout and several contrast combinations inherited from the old faint token. The route and formula DOM order was also checked against the production data contract rather than the handoff's mock state.

The repair introduced the 1000–1439 compact three-column tracks, a 999px stacked breakpoint, wrapped toolbars/footer controls, two-line formula clauses, internal formula scrolling, `--faint: var(--muted)`, `--unavailable-fg: #545454`, and the high-contrast warning foreground for route numbers.

### Pass 3 — final layout audit

The pass-three layout matrix found zero document-level horizontal overflow across 2560, 1920, 1440, 1024, 768 and 390 widths on all five routes plus the formula deep link. Its visible-font probe returned no sub-11px elements. Static CSS and ECharts scans likewise found zero visible font declarations below 11px; the SRF degraded chart annotation is explicitly tested at 11px.

The obsolete pass-two contrast artifact records the issues that triggered the token repair and is not a final result. The final token calculation is `#545454` on white **7.57:1**, `#545454` on `#F8F8F8` **7.13:1**, warning `#8A4A00` on white **6.86:1**, action blue **5.00:1**, positive green **4.51:1**, and negative red **4.73:1**. The post-last-patch computed-style matrix (`local-contrast-matrix-final.json`) scanned all five routes at 1440×1000, 1024×1000 and 390×844: every route had a visible 11px minimum and zero text samples below 4.5:1. The local development, clean lazy-load and production-preview browser flows each returned zero console warnings or errors.

## Typography, colour and assets

- DM Mono remains the terminal/data face and Noto Sans HK remains the Cantonese body face.
- Visible UI text has an 11px floor. Hidden `.sr-only` content, KaTeX's hidden MathML tree and mathematical super/subscripts are excluded from the visual-size audit.
- Mono micro-label tracking is limited to `.06–.08em`; long source, clause and legal text wraps without changing document width.
- The existing black/white/gray palette, blue actions, orange warnings and green/red directions are preserved. There are no radii, gradients or card shadows.
- No image or brand assets were added. ECharts canvases, SVG sparklines and lazy KaTeX fonts remain the only rendered graphic resources.

## Local automated evidence

- Python 3.12.13 pipeline suite: 486/486 passed.
- Frontend Vitest: 59/59 passed across three files.
- `npx tsc --noEmit`: passed.
- Production Vite build: passed; KaTeX remains a separate lazy JS/CSS chunk. The only build message is the existing main-chunk size advisory.
- `npm audit --omit=dev`: zero vulnerabilities.
- `git diff --check`: passed.

## Final browser close-out

- All eight Liquidity metric tabs and all six range controls became the unique pressed control and kept both ECharts canvases equal to their assigned containers. OBFR and TGCR overlays toggled on and restored off. The current publication exposes five IORB confirmation spread cards.
- Methodology and source drawers opened with semantic dialogs; Shift+Tab wrapped from the close control to the final source link, Escape closed them, body scrolling was restored and focus returned to the invoking control. The downloaded `snapshot.json` was byte-identical to the local publication (`7ac70060…1759`).
- `#/provenance#p0-video-formulas` focused `ARTICLE#p0-video-formulas` on direct load and after forward navigation; Back returned to the Overview heading and active route.
- A fresh production-preview Overview loaded no KaTeX DOM or KaTeX asset. Banner navigation produced 3 display formulas, 24 notation items and 27 MathML roots with zero errors; hashed JS, CSS and the two used fonts were discovered, bundled and fetched with 0/5 failures.
- Eleven source links and four formula/source-model links were visible and keyboard focusable. The five unique official source destinations returned HTTP 200.

## Acceptance boundary

This local design comparison has no known P0/P1/P2 visual blocker. The final implementation commit identity, deployed Pages assets and live data parity are recorded after deployment in the Release 7 QA record.

final result: passed
