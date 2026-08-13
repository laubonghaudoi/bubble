# Release 3 — P2 Bubble / Fragility QA record

Date: 2026-08-12<br>
Scope: government-origin equities/GDP proxy、full-market SEC Form 4 P/S count proxy、privacy-minimized ledger、Market Ignition fragility context UI<br>
Baseline commit: `72dcfa5`

## Locked contract

- P2 係 Market Ignition 頁嘅獨立 context panel；唔改 P1 evidence switch、P0 Liquidity Fuel、Overview overall assessment或 alerts。
- Active proxy只得 `nonfinancial_equities_gdp_proxy` 同 `sec_form4_nonderivative_ps_count_ratio_20d`；其餘六項 rights/input hold固定 `UNAVAILABLE_FREE`、value `null`、零 network request。
- Equities/GDP只 join `NCBEILQ027S` 同 `GDP` exact common quarter，唔 forward-fill；component、ratio、QoQ／YoY同 trailing-40-quarter midrank由full series交叉驗證。
- SEC Form 4只計Table I non-derivative `P`／`S` transaction rows。按SEC定義，P/S包括open-market **或 private** transactions，所以名稱、methodology同UI都唔作open-market-only聲稱。
- Form 4主值係20個completed EDGAR-index business days `(P+1)/(S+1)`；dollar ratio要求至少80% priced-row coverage；10b5-1只用filing-level tri-state，explicit-false sensitivity分開顯示。
- Public ledger只保存privacy allowlist字段、45日retention、manifest/shard hashes；raw submission只可留喺private Actions cache。額外檔案、symlink、schema／hash／retention錯誤全部fail closed。
- Required SEC index/submission partial failure會保留整套last-good metric同ledger，唔會將partial day發布成成功。

## Pre-deployment verification

- Deterministic完整stage：schema `2.0.0`、40 metrics、40 series、10 automated collectors；P1維持`1/4 / LOW / assessment:null`，P2兩項active proxy健康，六項hold保持null。
- Python fixture／scenario／privacy／cross-artifact gates：最終 `328 passed`，包括以production-shaped staged P2 publication執行checked-publication tests。
- Frontend Vitest：`34 passed`；TypeScript／Vite production build：passed（只保留已知嘅 >500 kB chunk advisory）。
- Workflow contract／actionlint：passed；daily cron移至約07:00 UTC Tue–Sat，SEC raw cache只在`runner.temp`經`actions/cache`保存，唔會加入public data commit。
- 1440×1000、1024×1000、390×844 staged rendered QA：passed。三個 viewport 均無橫向 overflow、console warning/error 或 failed data request；desktop/1024 維持兩欄 active cards同三欄 held cards，390 正確疊成單欄。
- Route／interaction regression：P1 保持 `1/4 / LOW / assessment:null`，P2 顯示 `2/8 CONTEXT AVAILABLE` 且無 severity；Overview overall assessment、back/forward、route focus、8W/12W、drawer focus trap／Escape／focus restore均passed。
- Data disclosure：兩項active proxy、六項rights-held null、exact-quarter macro dates、Form 4 open-market或private語義、低priced-row coverage、SEC/FRED notices同source links均按contract顯示。
- Phase commit `f0e2e00` 嘅 run `31646177412` 雖然 workflow／Pages 成功，但production probe發現 FRED `NCBEILQ027S` 現行frequency係 `Quarterly, End of Period`，同時SEC daily master header／日期格式同fixture假設不同；P2只得`0/8`，因此未當作通過。
- Collector schema修正 commit `6917f1c` 嘅 run `31646874965` 成功，macro proxy恢復`OK/FRESH`；不過真實Form 4 `periodOfReport`合法使用帶timezone嘅 `xs:date`，SEC collector仍fail closed，P2只得`1/8`，同樣未當作通過。
- `xs:date`修正 commit `884c1b8` 嘅 run `31652417996` 成功：Python `328 passed`、Vitest `34 passed`、production build同Pages deploy通過，並產生完整data commit `77531a5`。Live P2達到`2/8 CONTEXT AVAILABLE`，兩項active proxy均為`OK/FRESH`。
- Final Form 4 ledger保存31個completed index days（2026-06-29至2026-08-11）、31個shards、16,890個unique accessions，collection failures為0。Manifest／shard hashes、exact file membership、privacy allowlist同amendment resolver全部通過；public artifact無owner姓名、地址、簽名、security title或raw filing內容。
- 20D窗口（2026-07-15至2026-08-11）有9,099份processed filings；修訂解析後8,973份effective（8,943 originals + 30 amendments），排除21份superseded originals同105份unlinked amendments。獨立重算P=1,082、S=6,660、eligible=7,742、priced=7,726，count ratio `0.162588`、dollar coverage `0.997933`、dollar ratio `1.397903`，同snapshot、series endpoint及UI逐項一致。
- Macro live value為`218.139197%`（2026-Q1 exact common quarter；47個quarter observations）；Form 4 live value為`0.162588`。六項rights/input hold維持`UNAVAILABLE_FREE / NOT_APPLICABLE / null`，五個retired aliases全部HTTP 404；P0維持`NEUTRAL 4/4`，P1維持`assessment:null / 1/4 / MIXED / LOW`。
- Live browser QA喺1440×1000、1024×1000、390×844通過：無水平overflow、console error／warning或failed data request；ranges、hash history、route focus、兩種drawer、focus trap／Escape／restore、legal notices及JSON download正常。
- Browser QA另發現methodology drawer將explicit-false ratios誤套integer formatter。Hotfix commit `ae3b388` 加入ratio-first semantic formatting同regression；run `31653252262` 成功，產生最終data commit `c578455`，79/79 Pages files同artifact byte-identical。最終live drawer正確顯示20D `0.50`、5D `0.39`，載入`index-CE0nAvvW.js`，console維持0 error/warn。

final result: passed
