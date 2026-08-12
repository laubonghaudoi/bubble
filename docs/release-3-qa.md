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
- Python fixture／scenario／privacy／cross-artifact gates：`297 passed`，包括以staged P2 candidate執行checked-publication tests。
- Frontend Vitest：`34 passed`；TypeScript／Vite production build：passed（只保留已知嘅 >500 kB chunk advisory）。
- Workflow contract／actionlint：passed；daily cron移至約07:00 UTC Tue–Sat，SEC raw cache只在`runner.temp`經`actions/cache`保存，唔會加入public data commit。
- 1440×1000、1024×1000、390×844 staged rendered QA：passed。三個 viewport 均無橫向 overflow、console warning/error 或 failed data request；desktop/1024 維持兩欄 active cards同三欄 held cards，390 正確疊成單欄。
- Route／interaction regression：P1 保持 `1/4 / LOW / assessment:null`，P2 顯示 `2/8 CONTEXT AVAILABLE` 且無 severity；Overview overall assessment、back/forward、route focus、8W/12W、drawer focus trap／Escape／focus restore均passed。
- Data disclosure：兩項active proxy、六項rights-held null、exact-quarter macro dates、Form 4 open-market或private語義、低priced-row coverage、SEC/FRED notices同source links均按contract顯示。
- GitHub Actions generated-data commit、Pages deployment同live data/browser QA：pending。

final result: pending live deployment
