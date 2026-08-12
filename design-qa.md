# USD Liquidity Dashboard — Bloomberg Editorial Palette QA

## Source visual truth

- Reference: current `https://www.bloomberg.com/` homepage captured on 2026-08-12.
- The reference is authoritative for colour language only: black masthead, white editorial surfaces, charcoal ticker, gray dividers, blue action accents, orange highlights, and green/red market direction. The dashboard's existing layout, typography, data, and interactions intentionally remain unchanged.
- Reference captures: `/tmp/bubble-bloomberg-reference-1440x1000.png`, `/tmp/bubble-bloomberg-reference-1024x1000.png`, `/tmp/bubble-bloomberg-reference-390x844.png`.
- No Bloomberg logo, font, copy, imagery, icon, or other brand asset is included in the implementation.

## Rendered implementation

- Production build preview: `http://127.0.0.1:4173/`.
- Implementation captures: `/tmp/bubble-bloomberg-local-1440x1000.png`, `/tmp/bubble-bloomberg-local-1024x1000.png`, `/tmp/bubble-bloomberg-local-390x844.png`, plus the focused provenance capture `/tmp/bubble-bloomberg-local-provenance-1440x1000.png`.
- Side-by-side comparisons: `/tmp/bubble-bloomberg-comparison-1440x1000.png`, `/tmp/bubble-bloomberg-comparison-1024x1000.png`, `/tmp/bubble-bloomberg-comparison-390x844.png`.
- Browser capture density was 1 CSS pixel per device pixel. The browser screenshot surface excludes its scrollbar gutter: source/local captures were 1425×990 / 1434×996, 1009×985 / 1018×994, and 375×812 / 384×831 pixels. Comparisons were top-left padded, never scaled, to the requested 1440×1000, 1024×1000, and 390×844 CSS canvases.
- State: single editorial theme, default SOFR−IORB main metric, 3M range, default SOFR/IORB/EFFR overlay unless otherwise noted.

## Full-view comparison

- 1440×1000: black masthead and charcoal footer frame the preserved four-row terminal deck; white cards, gray hairlines, blue chart/action colour, orange brand/source accent, green positive deltas, and red negative deltas match the reference palette hierarchy.
- 1024×1000: the original three-column deck remains readable. The 320px chart panel, wrapped readout metadata, source rail, and footer have no page-level horizontal overflow.
- 390×844: the masthead becomes a balanced 2×2 status grid after theme-toggle removal; switches, tape, charts, and read rail retain their existing stacked order with no horizontal overflow.
- Focused crop comparison was not needed because this is a palette-only adaptation rather than a structural or asset clone. Exact computed styles, ECharts option tests, contrast sampling, and the full-resolution viewport captures verify the small colour details that are not legible in a scaled full-page thumbnail.

## Required fidelity surfaces

- Fonts and typography: DM Mono and Noto Sans HK, sizes, weights, line heights, wrapping, and truncation are unchanged by design.
- Spacing and layout rhythm: deck tracks, body columns, square geometry, dividers, panel padding, and responsive breakpoint remain unchanged. No clipping or overlap was observed.
- Colours and tokens: DOM and canvas share `#0064FA` action blue, `#E51503` threshold/negative red, `#338736` positive text green, `#8A4A00` warning text orange, and `#767676` unavailable gray. SOFR/IORB/EFFR/OBFR/TGCR/BGCR remain blue/red/black/green/orange/gray in one ordered config.
- Image quality and assets: the dashboard contains no new image assets. Existing ECharts canvas and SVG sparklines render sharply; no source brand assets or placeholder art were introduced.
- Copy and content: all Cantonese/English dashboard labels, source data, methodology content, and missing-is-never-zero language are unchanged.
- Accessibility: a visible-text contrast scan at 1440×1000 returned zero values below 4.5:1. Keyboard controls, ARIA chart summaries, drawers, focus trap/restoration, loading/error live regions, and semantic pressed states continue to work.

## Interaction and runtime evidence

- Tape/main selection, 1M range, OBFR and TGCR overlay toggles, JSON download, source drawer, methodology drawer, Escape close, focus restoration, and responsive scrolling passed.
- Legacy `data-theme="dark"` and `liq-theme=dark` are removed on mount; there is no DARK/LIGHT control and the browser theme colour is `#000000`.
- Browser DOM contains meaningful dashboard content, no framework error overlay, and no console warnings or errors at desktop or mobile sizes.
- Frontend tests: 21 passed. Pipeline tests: 11 passed. TypeScript and production build passed; Vite reports only the existing bundle-size advisory.

## Comparison history

- Pass 1 found two P2 contrast issues: inactive overlay controls inherited 0.55 opacity, and chip tags used `#767676` on `#F8F8F8` (4.28:1).
- Fix: removed inactive-control opacity, introduced `#545454` secondary text, and mapped chip tags to that accessible foreground while retaining Bloomberg gray for unavailable states.
- Pass 2 found a P2 contrast issue in compact source-quality badges, whose tinted background reduced the green and orange foreground ratios. The static review also prompted explicit `ample` status coverage in the component test.
- Fix: moved badges to white editorial surfaces with semantic left-edge markers, kept `missing`/paid unavailable gray and `error` red, and added the `ample` healthy-state regression fixture.
- Pass 3: a full-page browser contrast scan returned no visible text below 4.5:1; the focused provenance capture and desktop, tablet, and mobile comparisons showed no remaining P0/P1/P2 findings.

## Remaining risk

- Bloomberg.com is a changing external reference; this implementation intentionally pins the palette measured on 2026-08-12.
- The existing JavaScript bundle remains above Vite's 500 kB advisory threshold; this is unchanged and outside the palette-only scope.

final result: passed
