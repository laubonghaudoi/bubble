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

Production log 會以 `pipeline-health-<run-id>` artifact 保存 14 日。Workflow 將完整 v2 output 留喺獨立 stage，Python 同 frontend gates 全過先 atomic promote。檢查 HTTP content type、必要 JSON keys/CSV columns、date、unit、duplicate observations 同 source as-of。HTML error page、空 200 response 或 schema drift 必須 fail closed，唔可以當正常空 series。

Collector 失敗時 pipeline 應保留 last-good observations：有歷史值用 `STALE`，完全冇可用值用 `ERROR`，並保存 `last_success_at`、`last_attempt_at` 同 `failure_reason`。唔好用零代替缺失。

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

Generated-data push 使用 repository `GITHUB_TOKEN`，按 GitHub 官方規則唔會建立另一個 push-triggered workflow run。如果見到 recursive runs，檢查 checkout/push authentication 有冇被改成 PAT、deploy key 或 GitHub App token；恢復預設 `GITHUB_TOKEN`，或者喺改 token 前加入明確 recursion guard。同時保持 deterministic serialization，避免每次執行只因無金融意義嘅 order 改變而產生 data commit。

## Pages deploy 或 route 404

- Settings → Pages → Source 必須係 GitHub Actions；
- 確認 `npm run build` 已產生 `dist`；
- 所有頁面應用 hash route：`#/overview`、`#/liquidity-fuel`、`#/market-ignition`、`#/fundamental-exit`、`#/provenance`；
- project path 前綴由 Vite base 處理，唔好新增 server rewrite；
- 檢查 `upload-pages-artifact` 同 `deploy-pages` steps。

## Frontend 顯示完整 error state

先檢查 `public/data/snapshot.json`：

- `schema_version` 必須係 `2.0.0`；
- snapshot counts 要同 metrics availability/health 相符；
- source health counts 要同 collector source records 相符；
- required P0 metric IDs、source fields、12 methodology fields、statistics、timestamps 同 `short_series` 都要存在。

Manifest 失敗只應令 methodology/catalog 部分降級；snapshot 失敗會顯示完整 dashboard error。修正 staging/build contract後先重新發布，唔好直接手改 live JSON。

## Quick verification

```bash
python -m pytest pipeline/tests
npm test
npm run build
git diff --check
```

部署後再開四條 hash route，驗證 source/methodology drawers、JSON data paths、console/network errors，同 live deployment commit。
