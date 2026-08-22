# 版面重排：字級加大、密度收緊

`USD·LIQ · IMPLEMENTATION NOTES · 2026-08-13`

保留現有 Bloomberg editorial 配色、DM Mono／Noto Sans HK 同全部資料契約。版面**流動寬度**（100% viewport），設計稿以 1920×1080 為基準檢視。

> **唔改嘅範圍：** pipeline、schema 2.2.0、threshold、formula outcome、freshness 判斷、missing-is-never-zero 語言、alerts、switch severity。以下全部係前端 presentation 層改動。

`FILES · src/styles.css · src/components/DashboardPanels.tsx · index.html · package.json（katex）`

---

## 1 · 字級：最細由 7.5px 提到 11px

所有 sub-11px 規則係主要可讀性問題。改 `src/styles.css`：

| SELECTOR | 現時 | 改成 |
| --- | --- | --- |
| `.video-p0-values small` | 7.5px | **12px** |
| `.last-good-tag` | 7.5px | **11px** |
| `.proxy-mark` | 8px | **10px** |
| `.video-p0-values dt` · `.video-p0-banner-state small` | 8.5px | **12px** |
| `.video-p0-values dd` | 11px | **18px / 500** |
| `.tape-delta small` · `.balance-delta small` | 9px | **11px** |
| `.range-caption` | 9px | **12px** |
| `.chart-reference-note` | 10.5px | **13px** |
| `.panel-header` · `.tape-head` · `.tape-group-title` · `*-kicker` | 11px | **13px** |
| `.tape-label` | 13px | **15px** |
| `.tape-value` · `.balance-value` · `.metric-value` | 13.5px | **16px** |
| `.read-bullet` | 13.5px | **15px** |
| `.read-headline` | 17.5px / 1.55 | **21px / 1.4** |
| `.readout-value` | 32px | **52px** |
| `.readout-delta` / `.readout-meta` | 14 / 11.5px | **18 / 13px** |
| `.source-notices p` 等法律段落 | ~11px | **13.5px / 1.5** |

## 2 · Tracking：細字唔可以再撐開

所有 mono micro-label 由 `letter-spacing: .14em` 收到 `.06–.08em`；`.tape-head` 由 .08em 收到 .06em。字級加大之後淨佔位反而窄咗，所以第 3 節嘅欄位收緊唔會爆行。

## 3 · 密度：拎返被 padding 食咗嘅空間

- **合併 chrome 兩行。** `.deck` 嘅 `grid-template-rows: 46px 30px minmax(0,1fr) 28px` → `54px minmax(0,1fr) 34px`；`RouteNav` 由 `StatusBar` 之後嘅獨立 row 改成移入 `.status-bar` 內、brand 同 `.status-cluster` 之間（`DashboardPanels.tsx · StatusBar`）。淨賺 23px。
- **Tape row 34px。** `.tape-row height: 37px → 34px`，但字級加大；`.tape-head`／`.tape-row` 嘅 `grid-template-columns` 由 `minmax(110px,1fr) 48px 72px 56px` → `minmax(0,1fr) 70px 100px 96px`（LAST／CHANGE 要容 16px 字）。`.sparkline` 48×19 → 70×22。
- **Header 合併。** `.panel-header`（31px）同 `.tape-head`（29px）併成一條 30px：LIVE TAPE 標題同欄名同行。`.tape-group-title` padding `7px 12px 5px → 4px 12px`。
- **Body grid 用足闊度。** `.body-grid` 由 `minmax(334px,400px) minmax(320px,1fr) minmax(250px,352px)` → `minmax(400px,460px) minmax(320px,1fr) minmax(380px,476px)`。中欄仍然係 `1fr`，所以闊屏會全部俾圖表。
- **法律聲明兩欄。** `.source-notices` 內文加 `columns:2; column-gap:22px` — 闊屏單欄長行最浪費空間。
- **Balance delta 欄。** `.balance-row-head` 第三軌由 `52px` 加到 `100px`；16px 字加 `1 OBS` 唔會溢出 rail padding。

## 4 · 流動寬度（唔係固定 1920）

- `.app-shell` / `.deck` 維持 `width:100%`、`height:100dvh`；唔加 `max-width`。
- 中欄圖表用 `minmax(0,1fr)`，兩側 rail 用 `minmax()` 上限封頂，所以 1440 到 2560 之間都唔會出現死白。
- **Toolbar 一定要保留 `flex-wrap:wrap`。** `.chart-toolbar` 同 `.overlay-toolbar` 加大字級之後，窄屏會超出中欄；同時將 `.chart-panel` 嘅 toolbar row 由固定高度改成 `auto`，換行唔會被 clip。

## 5 · 層級：主讀數放大

- `.readout-value` 52px（`letter-spacing:-.03em`），delta 同 as-of 排在同一 baseline。
- `.metric-card strong`（IORB confirmation spreads）30px，**數值同 delta 分兩行、兩者都 `white-space:nowrap`** — 287px 卡放唔落一行 34px 數值加 delta。
- `.fundamental-aggregate` 主值 56px；`.cftc-readout strong` 同 `.fragility-readout strong` 40px。
- Detail page `h2` 32px、hero 說明 16px；每頁最多一個 40px+ 數字。

## 6 · 流動性燃料頁：補回 ChartPanel

現行 `LiquidityPage` 已經有 `ChartPanel` 配 `LIQUIDITY_MAIN_TABS`；重排稿保留同一結構（hero → P0 banner → confirmation grid → chart → evidence blocks），只係將 chart 區高度改成填滿剩餘 viewport，避免頁尾出現大片空白。`LIQUIDITY_MAIN_TABS` 八個指標同 `RANGES` 六個 window 一律唔變。

## 7 · 來源與方法頁：兩欄 + KaTeX

- `.provenance-grid` 改成 `minmax(560px,660px) minmax(0,1fr)`：左邊 collector health + 法律聲明，右邊公式面板。
- 黃／紅／極端三張 `.formula-card` 並排（`repeat(3,minmax(0,1fr))`），一屏可比。
- **Clause row 改成兩行。** `.formula-clause` 由 `minmax(0,1fr) auto` 改成：標籤 + 狀態一行，數值同 basis 各自一行、加 `overflow-wrap:anywhere`。原本 `auto` 值欄會壓縮左邊標籤到溢出。
- **Notation 表用兩欄佔滿。** 已刪除 ANALYSIS CONTRACT 區塊；`.formula-notation-grid` 改成 `repeat(2,minmax(0,1fr))`，SOURCE MODEL 同 TECHNICAL FLAGS 收成表底一行。⚠️ 注意：analysis-contract 嘅免責字句要確認仍然出現在 footer 或 drawer，唔可以連內容一齊消失。
- **KaTeX。** 公式由 `snapshot.decision_models.p0_video_liquidity.formulas.*.display_tex` 渲染，`output:'htmlAndMathml'`、`throwOnError:false`；渲染失敗就保留 pipeline 嘅純文字 `expression`（現行 `LatexFormula.tsx` 已經係呢個 contract）。符號表 `symbol_tex` 用 inline mode。字級：display 15px、inline 15px。

## 8 · 驗收

- 1440 / 1920 / 2560 三個闊度都無 horizontal overflow，中欄 toolbar 唔會壓到 read rail。
- 全頁可見文字對比度 ≥ 4.5:1（`--muted:#545454` 已經係 accessible foreground；唔好退回 `#767676` 做正文）。
- 最細字 11px；`design-qa.md` 記錄嘅三次 contrast pass 結果要重跑。
- KaTeX 載入失敗時公式 panel 唔會消失，只顯示純文字 expression。

`RUN · npm test · npx tsc --noEmit · npm run build · python -m pytest pipeline/tests`
