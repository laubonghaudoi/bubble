# Release 4 — P3 Fundamental Exit QA record

Date: 2026-08-12<br>
Scope: four-company SEC Company Facts cash CapEx、YoY acceleration、company breadth、reviewed manual filing interface、Fundamental Exit evidence-only UI<br>
Baseline commit: `ca5e317`

## Locked contract

- P3固定`EVIDENCE_ONLY`、`assessment:null`，只展示四個evidence blocks嘅coverage、direction同confidence；唔改P0 overall、P1/P2 coverage或任何alert/severity。
- Automated metrics只得`hyperscaler_aggregate_cash_capex`同`hyperscaler_aggregate_cash_capex_yoy_acceleration_pp`，兩者共用同一atomic quality/provenance state同至少12個共同季度。
- Microsoft、Alphabet、Amazon、Meta按各自fiscal calendar將Q1／H1／9M／FY cash-flow facts quarterize；Amazon使用`PaymentsToAcquireProductiveAssets`，其餘三間使用`PaymentsToAcquirePropertyPlantAndEquipment`。
- Aggregate先加總四間公司USD cash CapEx，再計QoQ、YoY同兩種acceleration。Company同aggregate衍生值均由published full series重算，唔依賴隱藏warm-up observations。
- Finance-lease additions分開，永遠唔加入cash CapEx；只有同cash fact屬同一filing accession先發布，否則fail closed為`null`。
- Orders/backlog、prepayments同take-or-pay只經17欄reviewed CSV進入；URL必須係同issuer CIK／accession／SEC primary document一致嘅直接SEC Archives HTML filing。未有row保持`MANUAL_READY`；超過120日係`STALE`，唔會自動評級。
- PR同production workflow均先執行SEC metadata dry-run；獨立scheduled workflow只建立／更新deduplicated review issue，唔寫內容或發布數字。

## Pre-deployment verification

- Deterministic production-shaped stage：schema`2.0.0`、P3 `2/4 / LOW / assessment:null`；三項manual metric均為`MANUAL_READY`。
- Live-shaped SEC Company Facts結果：aggregate cash CapEx `165.05` USD bn、QoQ `+27.206166%`、YoY `+87.033973%`、YoY acceleration `+6.580022pp`、company breadth `2/4`、12個共同季度。
- Latest company cash CapEx：Alphabet `44.924`、Amazon `54.208`、Meta `30.116`、Microsoft `35.802` USD bn；finance-lease disclosure breadth `3/4`，全部非null finance evidence同cash filing accession一致。
- Publication contract鎖定exact metric/switch/block/manifest/series/nested company fields、P3-only source set、fiscal/form/context、timestamp、source URL、manual cumulative-as-of、null deltas同no-severity；schema drift及額外public fields均fail closed。
- Python完整stage suite：`436 passed`；reviewed disclosure production dry-run：passed。
- Frontend Vitest：`39 passed`；TypeScript／Vite production build：passed（只保留已知嘅 >500 kB chunk advisory）。
- 1440×1000、1024×1000、390×844 staged rendered QA：passed。三個viewport均無page-level horizontal overflow或console warning/error；390px嘅12-quarter table係唯一刻意保留嘅內部水平scroller，scrollbar可達全部欄位。
- Exact candidate載入manifest同五條P3 series均HTTP 200；P3維持`2/4 / LOW / assessment:null`，P0維持`NEUTRAL 4/4 / MEDIUM`，P1維持`1/4 / LOW / assessment:null`，P2仍係獨立context。
- Deep link、route click、back/forward、route-heading focus、switch Arrow/Home/End、8W/12W、overlay toggle、method/source drawers、focus trap、Escape同focus restore全部passed；11個collector來源及SEC／FRED／NY Fed／CFTC legal notices均可達。

## Deployment and live verification

- Phase commit `6f319b6` 嘅 [Actions run `31656976405`](https://github.com/laubonghaudoi/bubble/actions/runs/31656976405) 全部gates成功：SEC metadata dry-run、fetch/stage、Python `436 passed`、Vitest `39 passed`、TypeScript／Vite build、atomic promote、generated-data push同Pages deploy。npm audit為0 vulnerabilities。
- Generated-data commit `09d1957`由`github-actions[bot]`建立，parent為phase commit；Pages deployment `5880113239`成功。Live snapshot、manifest、40條series、index同兩個assets共47/47同Pages artifact逐byte一致；44個data files同bot commit零差異。
- Live schema`2.0.0`、40 metrics／40 series、11個automated sources全為`OK/FRESH`。P3維持`2/4 / LOW / assessment:null`；CapEx `165.05` USD bn、YoY acceleration `+6.580022pp`、breadth `2/4`、12個quarters、finance-lease breadth `3/4`。三項manual metrics全部`MANUAL_READY / null / 0 observations`。
- 四間公司latest cash CapEx獨立重算：Alphabet `44.924` + Amazon `54.208` + Meta `30.116` + Microsoft `35.802` = `165.05`。Company-level direct SEC accession、form、accepted timestamp、tag、fiscal context同quarterization provenance全部通過contract。
- 五個retired P3 aliases（`hyperscaler_capex`、`capex_acceleration`、`upstream_backlog`、`prepayments`、`take_or_pay`）全部HTTP 404。P0保持`NEUTRAL 4/4 / MEDIUM`；P1保持`1/4 / LOW / assessment:null`；P2同所有既有數值、series、switches及解讀保持不變，只刷新operational timestamps並清除非P0誤繼承嘅Treasury technical flags。
- Live browser喺1440×1000、1024×1000、390×844重新通過：新asset `index-DiobXzHU.js`、五條P3 series全部200；routes、back/forward、route focus、ranges、overlay、drawers、focus trap／Escape／restore、11-source provenance同legal notices正常；零console warning/error，冇page-level overflow。
- 獨立manual disclosure [run `31657324716`](https://github.com/laubonghaudoi/bubble/actions/runs/31657324716)成功，建立唯一由`github-actions[bot]`持有嘅 [P3 review queue issue #2](https://github.com/laubonghaudoi/bubble/issues/2)；workflow只讀SEC metadata，冇抽取或發布數字。

final result: passed
