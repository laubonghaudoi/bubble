# Troubleshooting

## Workflow 在 source configuration step 失敗

確認 repository 已設定：

- Secret `FRED_API_KEY`：向 FRED 註冊嘅 API key；
- Variable `SEC_USER_AGENT`：`Bubble USD Liquidity Dashboard laubonghaudoi@icloud.com`。

唔好將兩者寫入 workflow、README example 以外嘅真值、commit 或 pipeline log。`SEC_USER_AGENT` 雖然唔係 secret，仍要用可識別而唔過度暴露私人資料嘅聯絡地址。

## `SourceNotNetworkEligible`

呢個係預期嘅 fail-closed 保護。檢查：

1. metric 是否 `implemented: true`；
2. availability 是否 `ACTIVE_FREE` 或 `ACTIVE_PROXY`；
3. metric `network_enabled`；
4. source enablement 同 rights flags；
5. FRED `source_series` 是否命中 reviewed allowlist。

唔好只改其中一個 boolean 強行通過。Rights-held source 要先完成條款/permission review，並同步修改 methodology、fixtures 同 tests。

## Pipeline fetch 或 schema validation 失敗

本地重現相同 group：

```bash
python -m pipeline.update --mode incremental --group daily
python -m pytest pipeline/tests
```

Production log 會以 `pipeline-health-<run-id>` artifact 保存 14 日。Workflow 將完整 schema `2.3.0` output 留喺獨立 stage，Python 同 frontend gates 全過先 atomic promote。檢查 HTTP content type、必要 JSON keys/CSV columns、date、unit、duplicate observations 同 source as-of。HTML error page、空 200 response 或 schema drift 必須 fail closed，唔可以當正常空 series。

Collector 失敗時 pipeline 應保留 last-good observations：有歷史值用 `STALE`，完全冇可用值用 `ERROR`，並保存 `last_success_at`、`last_attempt_at` 同 `failure_reason`。唔好用零代替缺失。

## Schema `2.2.0` 或更舊版本／P0 decision model 被拒絕

Schema `2.3.0` 係 hard cut。Code、config、staged publication 同 frontend 必須同版；`2.2.0` 或更舊 snapshot 唔會由 compatibility shim 載入。最少檢查：

```bash
jq -r '.schema_version' public/data/{snapshot,manifest,alerts,events}.json
jq -r '(.decision_models // {}) | keys[]' public/data/snapshot.json
```

- 四個 top-level artifact 同所有 `series/*.json` 必須係 `2.3.0`；Form 4 ledger 有自己獨立 schema，唔好用全域 search/replace 改版本；
- `snapshot.decision_models` 必須恰好有 `p0_video_liquidity`，唔可以缺失或加入未註冊 model；
- 黃／紅／極端頂層 formula 必須各自有 `expression`、`display_tex`、`plain_language`、`triggered` 同 `clauses`；Red Route A/B 仍只用 route expression、truth value 同 clauses；
- model-level `notation` 必須包含完整固定 key、冇重複，並分清 `VIDEO_SOURCE_RULE`、`DASHBOARD_OPERATIONALIZATION`、`MANUAL_CONTEXT` 同純邏輯符號用嘅 `MATHEMATICAL_NOTATION`；
- model `evaluated_at` 必須等於 snapshot `generated_at`；source segments、thresholds、TeX、plain language、notation、clauses、route truth values、status、data status 同 confidence 必須通過 contract 重算；
- SRF full／short observations 必須帶完整 technical／nontechnical classification fields，未知分類唔可以默認為 `false`。

如果 checkout 仲係 `2.2.0` 或更舊 generated data，應重跑相應 update group／production workflow，等 pipeline 重新生成完整 stage，再通過 Python、frontend 同 publication gates。唔好只改 `schema_version`，亦唔好手加 `decision_models`／`interpretation`；咁做會令 model、metrics、manifest、series 同 timestamps 失去一致性，而且 contract 應該繼續 fail closed。

## Selected-metric interpretation 缺失、錯配或顯示 `INSUFFICIENT`

先檢查 pipeline output，唔好喺 React hardcode分類：

```bash
jq '[.metrics[] | select(has("interpretation"))] | length' public/data/snapshot.json
jq -r '.metrics | to_entries[]
  | select(.value.interpretation != null) | .key' public/data/snapshot.json
jq '.metrics.sofr_iorb_spread_bp.interpretation' public/data/snapshot.json
```

- 每個 metric record 都必須有 `interpretation` key；17 個 canonical P0 metrics 必須非空，其餘所有 metrics（包括其他 P0 rights-gated records 同全部 P1/P2/P3 records）必須明確係 `null`；
- 非空 object 必須完整包含 `role`、`classification_type`、`data_state`、`numeric_direction`、`impact`、`state`、`severity`、`confidence`、`headline`、`what_it_measures`、`current_reasons`、`next_boundary`、`views`、`confirm_with`、`cannot_infer` 同 `rule_basis`；
- `role` 只可以係 `PRIMARY_FUNDING_PRICE`、`POLICY_RATE_ANCHOR`、`POLICY_ANCHORED_MARKET_RATE`、`CONFIRMATION_SPREAD`、`TREASURY_CASH_FLOW`、`LIQUIDITY_BUFFER`、`BACKSTOP_FACILITY`、`RESERVE_STOCK`、`BALANCE_SHEET_DRIVER` 或 `CROSS_CHECK`；
- `classification_type` 只可以係 `NO_HARD_THRESHOLD`、`SOURCE_PLUS_OPERATIONAL`、`SOURCE_PLUS_STATISTICAL`、`ROLLING_PERCENTILE`、`EVENT_TRIGGER`、`DIRECTIONAL` 或 `CROSS_CHECK`；
- `data_state` 只可以係 `CURRENT`／`LAST_GOOD`／`STALE`／`UNKNOWN`；`numeric_direction` 只可以係 `RISING`／`FALLING`／`FLAT`／`UNKNOWN`；`impact` 只可以係 `EASING`／`TIGHTENING`／`NEUTRAL`／`AMBIGUOUS`／`POLICY_ANCHOR`／`UNKNOWN`；`severity` 只可以係 `NORMAL`／`WATCH`／`YELLOW`／`RED`／`EXTREME`／`CONTEXT_ONLY`／`UNKNOWN`；`confidence` 只可以係 `HIGH`／`MEDIUM`／`LOW`／`UNKNOWN`；
- `rule_basis` 只可以係 `VIDEO_SOURCE_RULE`、`DASHBOARD_OPERATIONALIZATION`、`STATISTICAL_BAND` 或 `CONTEXT_ONLY`；見到 `VALIDATED_SIGNAL` 應直接 fail closed；
- `views` 必須非空，kind 只可以係 `REGIME_LADDER`、`PERCENTILE_GAUGE`、`EVENT_STEPPER`、`BREADTH_COUNTER`、`DIRECTIONAL` 或 `CROSS_CHECK`。每種 view 要 exact field set：ladder `{kind,label,rows,note}`，row 係 `{label,operator,threshold,upper_threshold,unit,rule,basis,active,met}`；gauge `{kind,label,value,unit,percentile,sample_size,state,slope,slope_unit,basis}`；stepper `{kind,label,window_size,positive_count,required_count,state,technical_exercise,basis}`；breadth `{kind,label,count,total,state,members,basis}`，member 係 `{metric_id,state,percentile,slope,confirming}`；directional `{kind,label,value,change,unit,state,basis}`；cross-check `{kind,label,primary_metric_id,comparison_metric_id,difference,unit,percentile,sample_size,state,basis}`；
- `next_boundary` 只可以係 `null` 或 exact `{label,current,threshold,distance,unit,rule,basis}` object；`current_reasons` 同 `rule_basis` 必須非空，basis 唔可以重複；
- 13 個 LIVE TAPE metrics 同四個額外 confirmation spreads（EFFR／OBFR／TGCR／BGCR 相對 IORB）合共 17 個 interpretation records；SOFR−IORB 已經喺 tape，唔應重複計成第 18 個；
- P0 alert engine 同 interpreter breadth 嘅三條 independent confirmations 都只係 EFFR／TGCR／BGCR。OBFR spread 有自己嘅 gauge/context，但唔可以加入 breadth、composite、改 alert level或改 `funding_confirmation_count`；
- `data_state`、quality/freshness 同數值必須一致。Stale、missing、last-good、insufficient history或分類不完整唔可以被寫成 neutral/current，缺失值亦唔可以補零。

新 statistical bands 預設係全歷史 expanding、deterministic nearest-rank，而且評估 observation 本身同所有未來 observations 都要排除。Nearest-rank threshold 取排序後第 `ceil(q × n)` 個 prior value（1-indexed）；畫面 percentile 係 empirical CDF `count(prior ≤ current) / n`。Daily bands 少過 60 個 prior observations、weekly bands 少過 104 個 prior observations時，boundary／band應保持 null/insufficient。ON RRP 係唯一非 expanding 例外：只用 endpoint 之前 20 個 valid observations、少過完整 20 個一樣要 insufficient，bottom-decile boundary 用 `q = 0.10`；唔好誤用舊式「將 current 放入 trailing-20 window」計法。驗證 no-lookahead 時，至少要做 prefix invariance：向 series 尾加未來 observation後，之前每個 endpoint嘅 band同 classification必須 byte-for-byte不變。

Interpreter 係 explanation layer。TGA、ON RRP、Fed assets同 OBFR 自身 gauge 可以提供 context，但唔係自動 WATCH/STRESS；OBFR亦唔會加入三條 confirmation breadth。影片 Extreme仍用既有 trailing-five-year p10，同 Yellow／Red／Extreme thresholds、clauses、routes、alerts同 overall assessment保持不變。如果新增 interpretation 後 `alerts.json`、`snapshot.alerts`、`composite` 或 formula truth改變，先當 contract regression處理，唔好將佢描述成預期嘅新 signal。

## H.4.1 顯示 `NOT_RELEASED_YET`

如果 Thursday job 喺官方 release 前執行，保留上一個 observation 並顯示 `NOT_RELEASED_YET` 係正常行為，唔係 pipeline failure。Cron 係 UTC 並受 DST/GitHub delay 影響；判斷應以官方 release metadata，而唔係 job 開始時間。

## CFTC TFF positioning 未更新

CFTC COT/TFF 一般用星期二持倉、星期五 15:30 ET 發布，但假期同官方 catch-up schedule 可以延遲或改日。先核對官方 release schedule，再檢查：

- dataset 必須係 TFF Futures Only `gpe5-46if`；
- CFTC code 必須係 E-mini S&P 500 `13874A` 或 Nasdaq-100 Consolidated `20974+`；
- `futonly_or_combined`、contract identity、long／short／open interest 同 release timestamp 必須全部通過 validation；
- 同一 contract/date 完全相同嘅 duplicate 可以 dedupe；衝突 duplicate 要 fail closed；
- 8W、12W 同 3Y z-score 只用有效 weekly observations，唔用 calendar interpolation。

正常 release window 之前沿用最新 weekly value仍可係 `OK/FRESH`；預期發布時間過後冇新 row先進入 `NOT_RELEASED_YET/LATE`，再按 tolerance 變成 `STALE`。CFTC stale 只會降低 evidence coverage，唔可以令 Market Ignition 變成 neutral。

## FRED series 被拒絕

Production allowlist 係 IORB、WRESBAL、WALCL、WTREGEN、NCBEILQ027S、GDP。SP500、NASDAQCOM、VIXCLS、VXVCLS、CBBTCUSD 屬第三方 rights hold，唔可以因為有 FRED API key 就加入 production fetch。

如 key 無效，FRED official API request 應失敗並沿用 last-good；唔好退回 `fredgraph.csv` scraping。

## P2 equities/GDP proxy 未更新

確認兩個 official FRED metadata仍然符合 contract：`NCBEILQ027S` 係 quarterly、NSA、millions USD、period-end government-origin series；`GDP` 係 quarterly、SAAR、billions USD。Transform只會 join exact calendar quarter，唔會將較新 GDP forward-fill落較舊 equities quarter。新 common quarter其中一個 component係缺失時，endpoint同 value都應顯示 `null`，唔可以倒退顯示上一個非空 ratio。

## SEC Form 4 collector／ledger 失敗

Daily job改喺約 07:00 UTC Tue–Sat喚醒，避開 SEC current-day index夜間生成前嘅窗口；collector仍只會處理 quarter `index.json`實際列出並完整讀取嘅 daily master indexes。檢查：

- `SEC_USER_AGENT` 有可識別專案同聯絡資料；
- `SEC_FORM4_CACHE_DIR`只係 private Actions cache，唔可以指向 `public/data`；
- 403會立即停止，429／502／503／504按 bounded Retry-After/backoff重試；
- index row按 accession去重，joint-owner duplicate唔可以重複計交易；
- 任何 required day master/submission failure會保留整套 last-good metric/ledger，標記 STALE/ERROR，唔會用 partial day當成功；
- weekly group會reconcile完整45-calendar-day retained window，daily group重查最新5日吸收 PAC/index timing；
- public `ledgers/sec_form4/manifest.json` hash、retention、completed-day、shard allowlist同私隱欄位全部要過 gate；額外 raw file/symlink會令 stage失敗。

初次啟用要做 bounded 45 日 backfill，可能需要約一小時；唔好中途用手改 stage。Form 4 `P`／`S`係 open-market或private transaction code，唔好將卡片或説明改成純 open-market。

## P3 Company Facts／CapEx 失敗

P3只讀`config/companies.yml`固定四間公司。先檢查：

- Microsoft、Alphabet、Meta使用`PaymentsToAcquirePropertyPlantAndEquipment`；Amazon使用`PaymentsToAcquireProductiveAssets`；
- issuer CIK、fiscal-year-end、Q1／H1／9M／FY context、form、unit、accession同SEC Archives issuer path必須一致；
- Q1至Q3只接受10-Q／10-Q-A context，Q4只接受10-K／10-K-A；Q2、Q3、Q4分別由H1−Q1、9M−H1、FY−9M計算；
- 四間公司要有至少12個連續共同季度；aggregate一定先加總USD cash CapEx，再計QoQ、YoY同acceleration；
- finance-lease additions唔會加入cash CapEx，亦只會喺finance fact同cash fact屬同一filing accession時發布，否則保持`null`。

Collector或schema失敗會原子保留兩條automated metric嘅同一份last-good，兩者唔可以一條`OK`、另一條`STALE`。P3只影響evidence coverage，唔可以改P0 overall、P1 switch或alerts。

## P3 reviewed manual filing 驗證失敗

所有group都會先結構驗證`data/manual/industry_signals.csv`；PR同production workflow亦會執行：

```bash
SEC_USER_AGENT='Bubble USD Liquidity Dashboard laubonghaudoi@icloud.com' \
python -m pipeline.check_p3_disclosures --dry-run
```

每條record要有canonical accession、reviewer、review time、短paraphrase，同直接`www.sec.gov/Archives/edgar/data/.../*.htm[l]` filing URL。URL必須同issuer CIK、accession及SEC submissions嘅primary document完全一致；issuer marketing page、PDF、redirect、query、fragment或path traversal一律拒絕。未有row係`MANUAL_READY`；有row但超過120日係`STALE`並要求重新覆核，唔可以描述成「冇記錄」，亦唔會自動變成WATCH/STRESS。

## Generated-data commit 或 push 失敗

Workflow 會喺 deploy 前 commit/push `public/data`。Push failure 係 blocking failure；Pages 唔會用一個未記錄嘅 data state 繼續發布。

常見原因：

- `main` branch protection 唔允許 Actions push；
- workflow `contents: write` 被 repository/organization policy 收窄；
- 同一時間有人更新 main；
- generated data 含未預期檔案或 contract test 未過。

先處理權限／branch divergence，再重跑 group。唔好恢復 `git push || true`。

`public/data/**` 係整套 generated publication，唔可以直接修補 snapshot、decision model、formula result、series、manifest hash 或 generated timestamp。應改 `config/`、pipeline code 或 reviewed `data/manual/` source input，再由 staging workflow 重建同 atomic promote。即使只係 schema 升級或一條 formula threshold，都唔可以用手改 live JSON 繞過 contract。

Generated-data push 使用 repository `GITHUB_TOKEN`，按 GitHub 官方規則唔會建立另一個 push-triggered workflow run。如果見到 recursive runs，檢查 checkout/push authentication 有冇被改成 PAT、deploy key 或 GitHub App token；恢復預設 `GITHUB_TOKEN`，或者喺改 token 前加入明確 recursion guard。同時保持 deterministic serialization，避免每次執行只因無金融意義嘅 order 改變而產生 data commit。

## Pages deploy 或 route 404

- Settings → Pages → Source 必須係 GitHub Actions；
- 確認 `npm run build` 已產生 `dist`；
- 所有頁面應用 hash route：`#/overview`、`#/liquidity-fuel`、`#/market-ignition`、`#/fundamental-exit`、`#/provenance`；
- project path 前綴由 Vite base 處理，唔好新增 server rewrite；
- 檢查 `upload-pages-artifact` 同 `deploy-pages` steps。

## Responsive 版面有空白、重疊或 document overflow

先用 browser 開五條 hash route，並以實際 `window.innerWidth/innerHeight` 記錄 `1440×1000`、`1024×1000`、`768×1000` 同 `390×844`；browser screenshot 有時會扣除 scrollbar 像素，所以 overflow 判斷應以 DOM measurement 為準：

```js
({
  clientWidth: document.documentElement.clientWidth,
  scrollWidth: document.documentElement.scrollWidth,
  clientHeight: document.documentElement.clientHeight,
  scrollHeight: document.documentElement.scrollHeight,
})
```

- 所有 viewport 都要有 `scrollWidth <= clientWidth`；只可以由 `.route-nav`、`.video-p0-banner` 或 `.latex-formula.is-display` 自身處理必要嘅水平 scroll；
- `1000px` 以上 Overview 係固定 viewport 三欄，只容許 tape／read rail 內部垂直 scroll；`999px` 或以下先改用單欄 document flow；
- Overview chart 留有大片底部空白時，檢查 `.chart-panel` grid rows、`.main-chart`／`.overlay-chart` client height，同 ECharts resize 有冇跟 container 更新；唔好用固定 canvas 高度掩蓋 grid slot 錯位；
- toolbar、range controls、status cluster 或 footer 被截時，先檢查 flex/grid wrap 同 `min-width: 0`，唔好用 `body { overflow-x: hidden }` 當成修復；
- 可見 UI 字體不得低於 `11px`，普通文字 contrast 要至少 `4.5:1`。審計時排除 `.sr-only`、KaTeX 隱藏 MathML tree 同數學上下標。

Header 應只有一個 `.route-nav`，而且 DOM 次序係 brand → navigation → status cluster。LIVE TAPE 亦只應有一個合併 header；如果見到舊式兩層 masthead 或獨立 panel/tape 雙 header，通常係舊 CSS/JS asset cache，應先核對 live `index.html` 所引用嘅 hashed JS/CSS 同本次 deploy artifact。

## KaTeX 公式冇顯示／解釋同結果唔一致

先檢查 publication contract，而唔係喺 React hardcode 另一條公式：

```bash
jq '.decision_models.p0_video_liquidity
  | {formulas, notation}' public/data/snapshot.json
```

- 黃／紅／極端頂層 formula 都要有非空 `display_tex`、`plain_language` 同 audit fallback `expression`；呢三者、clauses 同 chart reference 必須由同一套 config threshold 生成；
- Red Route A/B 只保留 route expression、truth value 同 clause table；頁面只會渲染三個頂層正式公式，唔應該因為 route 冇 `display_tex` 而報 contract error；
- `notation` 要覆蓋所有公式變數、邏輯符號同規則來源。影片明言門檻用 `VIDEO_SOURCE_RULE`；dashboard 為重現而設定嘅 persistence、floor、2-of-3 window 或 trailing percentile 用 `DASHBOARD_OPERATIONALIZATION`；危機背景 `c_t` 用 `MANUAL_CONTEXT`；`∧`／`∨`／`⇔` 等純符號用 `MATHEMATICAL_NOTATION`；
- KaTeX 正常時會同時產生 `.katex` 視覺 HTML 同 MathML，公式用 `aria-describedby` 連結相應粵文讀法。只見 fallback 時，檢查 browser console、KaTeX module/CSS/font request 同 `data-render-error`；TeX parse 或 lazy-load 失敗應只降級至 `expression`，唔應該令 formula card 或整頁消失；
- 唔好為咗令 KaTeX 成功而將 `throwOnError` 關閉、開啟 `trust`，或者用 auto-render 掃描整頁。應修正 pipeline 產生嘅 TeX，再重新生成完整 schema `2.3.0` stage。

KaTeX 只係表示層。`+3 bp`、`2.9/2.8/2.5T` 同 TGA 朝向 `1T` 可以係 source rule；`n≥3`、`g≥0.95T`、最近三日最少兩日 SRF 正值同 trailing-5y p10 係 dashboard operationalization；危機背景係 manual context。畫面同文件必須保留呢啲標籤，唔可以用正式排版暗示全部門檻都係學術定律或由原來源逐字定義。

公式頁嘅固定次序係 Yellow／Red／Extreme 三張頂層 card → notation → source/model notes；Red Route A/B 只顯示 outcome 同 clauses。畫面已移除舊 `ANALYSIS CONTRACT` 卡；研究用途／非投資建議聲明保留喺全站 footer，唔應因為 formula panel 搵唔到 `ANALYSIS CONTRACT` 而當成載入錯誤。

## Frontend 顯示完整 error state

先檢查 `public/data/snapshot.json`：

- `schema_version` 必須係 `2.3.0`；`2.2.0` 或更舊版本會被 hard reject，唔會顯示舊 dashboard；
- `decision_models` 必須恰好包含完整 `p0_video_liquidity`，而且 status／formula expression／TeX／plain language／notation／threshold／timestamp 要同 metrics 對得上；
- snapshot counts 要同 metrics availability/health 相符；
- source health counts 要同 collector source records 相符；
- required P0 metric IDs、source fields、12 methodology fields、statistics、timestamps、`short_series` 同 required `interpretation` key都要存在。

Manifest 失敗只應令 methodology/catalog 部分降級；snapshot schema 或 required decision model 失敗會顯示完整 dashboard error。先修正 source/config/pipeline，再重新生成 stage 同發布；唔好直接手改 live JSON。

## Quick verification

```bash
python -m pytest pipeline/tests
npm test
npx tsc --noEmit
npm run build
git diff --check
```

部署後再開五條 hash route同 formula deep link，驗證 merged masthead/tape header、13 個 tape/chart selections、selected-metric interpreter同步、document overflow、chart sizing、P0 formula panel、chart threshold／SRF marker、source/methodology drawers、JSON data paths、console/network errors，同 live deployment commit／hashed assets。
