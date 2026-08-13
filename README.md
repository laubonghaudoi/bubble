# 美元流動性監測

一個以 React/Vite 建立、由 GitHub Pages 托管嘅靜態美元流動性儀錶板。瀏覽器只讀取已發布嘅 schema `2.2.0` JSON；第三方 fetch、schema validation、金融計算、freshness 判斷同粵文解釋全部喺 Python pipeline 完成。

網站固定使用 Bloomberg editorial 配色，冇 dark-mode 或 theme switch。

## 網站路由

GitHub Pages 使用 hash routing，所以 project subpath 同直接開頁都唔需要 server rewrite：

- `#/overview`：總覽；
- `#/liquidity-fuel`：P0 美元流動性燃料；
- `#/market-ignition`：P1/P2 市場放大器同脆弱度；
- `#/fundamental-exit`：P3 CapEx 同產業需求；
- `#/provenance`：collector 健康狀態、分析 contract、來源授權同法律聲明。

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

## Schema 2.2.0 contract

`public/data/` 係一次過發布嘅完整 artifact set，包括 `snapshot.json`、`manifest.json`、`alerts.json`、`events.json`、`series/*.json`，以及 privacy-minimized `ledgers/sec_form4/`。Pipeline 先喺 staging directory 完成 fetch、normalize、transform、ledger hash/privacy allowlist 同 contract validation，全部成功先用 directory promotion 取代 live data；任何一步失敗都保留上一版完整資料。Raw SEC submissions 只可以留喺私有 Actions cache，永遠唔可以進入 public artifact。

`2.2.0` 係 hard cut，唔係向後兼容提示。Python publication contract 同 frontend loader 都會拒絕 `2.1.0` 或更舊 snapshot；唔會忽略新欄位、補預設門檻，或者靜默退回舊模型。`snapshot.decision_models` 必須只包含完整嘅 `p0_video_liquidity`：模型狀態、資料狀態、信心、影片來源段落、黃／紅／極端門檻、operationalizations、formula clauses、兩條紅色路徑、crisis context、notation 同 technical flags 都要存在，並同 snapshot metric value、quality、freshness、timestamps 同公式真值逐項對得上。缺少、額外、過期或被手改嘅 model data 都會 fail closed。

黃／紅／極端三個頂層 formula evaluation 都必須同時提供可審核嘅純文字 `expression`、由同一套 config threshold 生成嘅 `display_tex`、粵文 `plain_language` 同即時 `clauses`；Red Route A/B 保留 route expression、truth value 同 clauses，唔重複另一套正式公式。Model-level `notation` 必須用唯一 key 完整定義公式變數、邏輯符號、source rule、dashboard operationalization 同 manual context。`VIDEO_SOURCE_RULE` 只表示影片明言嘅規則或門檻，`DASHBOARD_OPERATIONALIZATION` 係為咗可重現而訂嘅 persistence、floor、rolling-window 或 percentile 實作，`MANUAL_CONTEXT` 只用於危機背景判斷；純數學符號另標記為 `MATHEMATICAL_NOTATION`，唔會混入 evidence provenance。

Frontend 只將 `display_tex` 交畀 KaTeX，並同時輸出視覺 HTML 同可存取 MathML；粵文讀法會用 accessible description 同相應公式連結。TeX parse、module 或 stylesheet 載入失敗時，公式會顯示 pipeline 提供嘅 `expression` fallback，而唔會令成個 panel 消失。KaTeX 只改善表示方式，唔會將 source-specific rule、dashboard operationalization 或人工 crisis context 包裝成學術定律，亦唔會改變任何 formula outcome、P0 overall、switch 或 alerts。

`p0_video_liquidity` 係對影片公式嘅獨立、可審核 decision model；唔會改寫既有 P0 `overall_assessment`、switch 或 alerts。SRF full series 同 snapshot fallback 亦必須保留 technical／nontechnical classification metadata，缺失分類唔可以當作非技術性零使用。

狀態分成三條獨立軸：

- Availability：`ACTIVE_FREE`、`ACTIVE_PROXY`、`MANUAL_READY`、`UNAVAILABLE_FREE`；
- Health：`OK`、`STALE`、`ERROR`、`NOT_RELEASED_YET`、`NOT_APPLICABLE`；
- Freshness：`FRESH`、`LATE`、`STALE`、`UNKNOWN`。

缺失值永遠係 `null`，唔會轉成 `0`。每項 metric 都有 observation/release/update/attempt timestamps、source rights note、quality metadata、numeric statistics 同 12 欄專屬 methodology。詳細權利政策見 [docs/source-rights.md](docs/source-rights.md)，人工資料政策見 [docs/manual-review.md](docs/manual-review.md)。

`public/data/**` 全部係 pipeline generated output，唔係手改資料源。包括 schema version、decision model、formula outcome、threshold、series、manifest hash 同 generated timestamp，都唔可以直接修改去「修好」build 或 deployment。應該改相應 `config/`、pipeline code 或 reviewed `data/manual/` input，再重跑完整 staging、contract tests、frontend tests/build 同 atomic promotion；schema 升級亦一樣。

## GitHub Actions 同 Pages

喺 repository 設定：

1. **Settings → Secrets and variables → Actions → Secrets**：新增 `FRED_API_KEY`；
2. 同頁 **Variables**：新增 `SEC_USER_AGENT`，值為 `Bubble USD Liquidity Dashboard laubonghaudoi@icloud.com`；
3. **Settings → Pages → Source**：選擇 **GitHub Actions**。

唯一 production workflow 係 `Update data and deploy Pages`：

- `push` 到 `main`：group `all`；
- weekday daily、Thursday H.4.1、weekly、monthly、quarterly UTC cron；
- `workflow_dispatch`：可揀明確 group。

Workflow 依序執行：核對 reviewed P3 filing metadata → fetch → validate/transform → 寫入獨立 schema `2.2.0` stage → Python tests → 喺臨時 workspace 用同一份 code 加 staged data 跑 frontend tests/build → atomic promote 完整 stage → commit generated `public/data` → push → Pages deploy。所有 gates 通過前，version-controlled `public/data` 都唔會被逐檔覆蓋。任何 metadata、data push 或 contract failure都會停止 deployment，唔會靜默略過。

Generated-data push 使用本次 job 嘅 repository `GITHUB_TOKEN`。按 [GitHub 官方觸發規則](https://docs.github.com/en/actions/concepts/security/github_token)，由呢個 token 造成嘅 push event 唔會建立另一個 workflow run，因此唔會形成 recursive data-commit loop。原本個 run 會喺 push 成功後直接上載已驗證嘅 `dist` 並部署 Pages；concurrency group 亦確保同一時間只得一個 production writer/deployer。唔好改用 PAT 或 GitHub App token，除非同時另外設計 recursion guard。

Cron 只係喚醒時間，而且 GitHub 可能延遲；collector 會用官方 observation/release metadata 判斷 `NOT_RELEASED_YET`、freshness 同 expected next update，唔會將 job start time 當 source as-of。

## Release 1–5 資料範圍

P0 包括：

- NY Fed SOFR、EFFR、OBFR、TGCR、BGCR；
- SOFR/EFFR/OBFR/TGCR/BGCR 相對 IORB spreads；
- ON RRP accepted amount、SRF accepted amount及官方 operational-readiness exercise calendar；
- Treasury daily TGA、auction settlement context；
- FRED 政府來源 allowlist：IORB、WRESBAL、WALCL、WTREGEN；
- 月／季／年結、已覆核報稅窗口同大型 Treasury settlement context。
- 獨立 `p0_video_liquidity` 黃／紅／Extreme 來源公式模型；只供可審核重現，唔改既有 P0 overall、switch、pill 或 alerts。

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
- [Release 5 QA紀錄](docs/release-5-qa.md)

本工具只供研究，唔提供投資建議。操作門檻、相關性及 proxy 指標唔代表因果，單一 metric 亦唔足以證明危機、泡沫轉折或資產方向。
