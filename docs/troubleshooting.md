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

## FRED series 被拒絕

Release 1 allowlist 係 IORB、WRESBAL、WALCL、WTREGEN；registry 亦預留經覆核嘅 NCBEILQ027S/GDP。SP500、NASDAQCOM、VIXCLS、VXVCLS、CBBTCUSD 屬第三方 rights hold，唔可以因為有 FRED API key 就加入 production fetch。

如 key 無效，FRED official API request 應失敗並沿用 last-good；唔好退回 `fredgraph.csv` scraping。

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
- 所有頁面應用 hash route：`#/overview`、`#/liquidity-fuel`、`#/market-ignition`、`#/fundamental-exit`；
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
