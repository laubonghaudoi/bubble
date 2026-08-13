# 美元流動性監測

一個以 React/Vite 建立、由 GitHub Pages 托管嘅靜態美元流動性儀錶板。瀏覽器只讀取已發布嘅 schema `2.0.0` JSON；第三方 fetch、schema validation、金融計算、freshness 判斷同粵文解釋全部喺 Python pipeline 完成。

網站固定使用 Bloomberg editorial 配色，冇 dark-mode 或 theme switch。

## 網站路由

GitHub Pages 使用 hash routing，所以 project subpath 同直接開頁都唔需要 server rewrite：

- `#/overview`：總覽；
- `#/liquidity-fuel`：P0 美元流動性燃料；
- `#/market-ignition`：P1/P2 市場放大器同脆弱度；
- `#/fundamental-exit`：P3 CapEx 同產業需求。

## 本地設定

需要 Node.js 22、Python 3.12，同兩個 production source 設定：

```bash
export FRED_API_KEY='your-registered-fred-api-key'
export SEC_USER_AGENT='Bubble USD Liquidity Dashboard laubonghaudoi@icloud.com'
npm ci
python -m pip install -r pipeline/requirements.txt
```

- `FRED_API_KEY` 只用於 `config/source_registry.yml` allowlist 內、已覆核權利嘅政府來源 series。API key 唔會令 SP500、NASDAQCOM、VIXCLS、VXVCLS、CBBTCUSD 等第三方 series 自動獲得再發布權。
- `SEC_USER_AGENT` 必須可識別專案同聯絡方法；唔好用 generic browser User-Agent。
- 本地亦可以複製 `.env.example` 作 checklist，但 pipeline 唔會自動讀取 `.env`；要喺執行 shell 明確 export。`.env*` 已被 gitignore，唔好提交真實 credentials。

本地增量更新同驗證：

```bash
python -m pipeline.update --mode incremental --group all
python -m pytest pipeline/tests
npm test
npm run build
```

可用 group：`all`、`daily`、`h41`、`weekly`、`monthly`、`quarterly`、`manual`。`daily` 會處理 P0 同最新已完成 SEC Form 4 daily indexes；`weekly` 同時處理 H.4.1、CFTC TFF positioning 同 45 日 Form 4 index reconciliation；`monthly`／`quarterly` 會重查 government-origin equities/GDP exact-quarter proxy；`quarterly` 亦會原子更新四間 hyperscaler 嘅 SEC Company Facts CapEx。所有 group 都會先驗證 reviewed manual CSV，`manual` group可安全重建人工 evidence。

## Schema 2.0.0 contract

`public/data/` 係一次過發布嘅完整 artifact set，包括 `snapshot.json`、`manifest.json`、`alerts.json`、`events.json`、`series/*.json`，以及 privacy-minimized `ledgers/sec_form4/`。Pipeline 先喺 staging directory 完成 fetch、normalize、transform、ledger hash/privacy allowlist 同 contract validation，全部成功先用 directory promotion 取代 live data；任何一步失敗都保留上一版完整資料。Raw SEC submissions 只可以留喺私有 Actions cache，永遠唔可以進入 public artifact。

狀態分成三條獨立軸：

- Availability：`ACTIVE_FREE`、`ACTIVE_PROXY`、`MANUAL_READY`、`UNAVAILABLE_FREE`；
- Health：`OK`、`STALE`、`ERROR`、`NOT_RELEASED_YET`、`NOT_APPLICABLE`；
- Freshness：`FRESH`、`LATE`、`STALE`、`UNKNOWN`。

缺失值永遠係 `null`，唔會轉成 `0`。每項 metric 都有 observation/release/update/attempt timestamps、source rights note、quality metadata、numeric statistics 同 12 欄專屬 methodology。詳細權利政策見 [docs/source-rights.md](docs/source-rights.md)，人工資料政策見 [docs/manual-review.md](docs/manual-review.md)。

## GitHub Actions 同 Pages

喺 repository 設定：

1. **Settings → Secrets and variables → Actions → Secrets**：新增 `FRED_API_KEY`；
2. 同頁 **Variables**：新增 `SEC_USER_AGENT`，值為 `Bubble USD Liquidity Dashboard laubonghaudoi@icloud.com`；
3. **Settings → Pages → Source**：選擇 **GitHub Actions**。

唯一 production workflow 係 `Update data and deploy Pages`：

- `push` 到 `main`：group `all`；
- weekday daily、Thursday H.4.1、weekly、monthly、quarterly UTC cron；
- `workflow_dispatch`：可揀明確 group。

Workflow 依序執行：核對 reviewed P3 filing metadata → fetch → validate/transform → 寫入獨立 schema v2 stage → Python tests → 喺臨時 workspace 用同一份 code 加 staged data 跑 frontend tests/build → atomic promote 完整 stage → commit generated `public/data` → push → Pages deploy。所有 gates 通過前，version-controlled `public/data` 都唔會被逐檔覆蓋。任何 metadata、data push 或 contract failure都會停止 deployment，唔會靜默略過。

Generated-data push 使用本次 job 嘅 repository `GITHUB_TOKEN`。按 [GitHub 官方觸發規則](https://docs.github.com/en/actions/concepts/security/github_token)，由呢個 token 造成嘅 push event 唔會建立另一個 workflow run，因此唔會形成 recursive data-commit loop。原本個 run 會喺 push 成功後直接上載已驗證嘅 `dist` 並部署 Pages；concurrency group 亦確保同一時間只得一個 production writer/deployer。唔好改用 PAT 或 GitHub App token，除非同時另外設計 recursion guard。

Cron 只係喚醒時間，而且 GitHub 可能延遲；collector 會用官方 observation/release metadata 判斷 `NOT_RELEASED_YET`、freshness 同 expected next update，唔會將 job start time 當 source as-of。

## Release 1–4 資料範圍

P0 包括：

- NY Fed SOFR、EFFR、OBFR、TGCR、BGCR；
- SOFR/EFFR/OBFR/TGCR/BGCR 相對 IORB spreads；
- ON RRP accepted amount、SRF accepted amount及官方 operational-readiness exercise calendar；
- Treasury daily TGA、auction settlement context；
- FRED 政府來源 allowlist：IORB、WRESBAL、WALCL、WTREGEN；
- 月／季／年結、已覆核報稅窗口同大型 Treasury settlement context。

P1 Market Ignition 使用 CFTC 官方 TFF Futures Only：

- E-mini S&P 500 同 Nasdaq-100 Consolidated 分開；
- Asset Manager／Institutional 同 Leveraged Funds 分開，唔會合併成一個「CTA」數字；
- 每條 series 顯示 net contracts、net % open interest、8W／12W change 同 trailing 156-observation z-score；
- positioning 只係 evidence direction，Market Ignition `assessment` 保持 `null`，唔產生 `WATCH`／`STRESS`；
- CFTC Tuesday observation、實際 release timestamp 同 pipeline update 分開顯示。

VIX/VIX3M、Cboe SKEW、BTC／ETH funding、trend 同 cross-asset transforms 有獨立 provider interface 同 fixture tests，但 production rights gate 維持關閉；佢哋會明確顯示 `UNAVAILABLE_FREE` 同精確原因，value 保持 `null`，亦唔會發 network request。

P2 Bubble / Fragility 係 Market Ignition 頁嘅獨立 context panel，唔會改變 P1 coverage、任何 switch severity 或 Overview overall assessment：

- `nonfinancial_equities_gdp_proxy`：FRED 只分發 rights-cleared government-origin `NCBEILQ027S`（Fed Z.1）同 `GDP`（BEA）；只 join exact common quarter，唔 forward-fill，先由 million 轉 USD bn 再計 ratio、QoQ／YoY 同 trailing-40-quarter percentile；
- `sec_form4_nonderivative_ps_count_ratio_20d`：由 SEC full-market daily master indexes 去重 accession，再讀 complete Form 4／4-A submission；只統計 Table I non-derivative `P`／`S`，即官方定義嘅 open-market **或 private** transactions，唔冒充純 open-market insider signal；
- Form 4 主值係 20 個 completed index business days 嘅 `(P+1)/(S+1)` transaction-row count proxy；5D、price coverage、dollar ratio、filing-level 10b5-1 tri-state、amendment review 同 parse audit 分開披露；
- Dollar coverage 低於 80% 或 sale-dollar denominator 為零時 dollar ratio 保持 `null`；真實 transaction count zero 仍保留零；
- FINRA margin debt、SPY Top-10、SPX 0DTE、NDX forward P/E、M2/Nasdaq 同 gamma flip 仍係 `UNAVAILABLE_FREE`，zero network request。

P2 畫面只顯示 `2/8 CONTEXT AVAILABLE`（兩項 active proxy、六項 rights/input hold）同各自 caveat，唔輸出 composite `WATCH`／`STRESS`。

P3 Fundamental Exit 係獨立 evidence-only 頁面，唔會改變 P0 overall、P1/P2 coverage 或任何 severity：

- `hyperscaler_aggregate_cash_capex` 同 `hyperscaler_aggregate_cash_capex_yoy_acceleration_pp` 由 Microsoft、Alphabet、Amazon、Meta 官方 SEC Company Facts／filing metadata建立；
- 每間公司按 fiscal Q1／H1／9M／FY context quarterize YTD cash CapEx，Q4 用 FY 減 9M；Amazon 使用現行 `PaymentsToAcquireProductiveAssets`，其餘三間使用 `PaymentsToAcquirePropertyPlantAndEquipment`；
- aggregate 先加總四間公司嘅 USD cash CapEx，再計 QoQ、YoY 同 acceleration；finance-lease right-of-use additions分開披露，永遠唔加入 cash CapEx；
- 完整 series 至少保留12個共同季度，並公開 company breadth、tag、accession、filing URL、context同quarterization method；
- orders/backlog、customer prepayments同take-or-pay使用17欄 reviewed CSV；未有 reviewed row時固定 `MANUAL_READY`，有 row亦只展示方向、coverage同短 factual paraphrase，唔自動抽取 narrative數字；
- P3初始coverage係 `2/4 / LOW / assessment:null`；三項人工 evidence由獨立 workflow搵新 filing／逾期 review並維護deduplicated issue，publication前會再次同SEC metadata核對。

## 文件

- [來源、授權同自動化 gate](docs/source-rights.md)
- [人工覆核及 manual import 政策](docs/manual-review.md)
- [故障排查](docs/troubleshooting.md)
- [Release 4 QA紀錄](docs/release-4-qa.md)

本工具只供研究，唔提供投資建議。操作門檻、相關性及 proxy 指標唔代表因果，單一 metric 亦唔足以證明危機、泡沫轉折或資產方向。
