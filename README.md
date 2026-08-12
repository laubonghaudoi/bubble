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

可用 group：`all`、`daily`、`h41`、`weekly`、`monthly`、`quarterly`、`manual`。`weekly` 同時處理 H.4.1 同 CFTC TFF positioning；monthly、quarterly、manual 等未實作 phase group 只會安全重建 last-good schema v2 output，唔會假裝新 metric 已 active。

## Schema 2.0.0 contract

`public/data/` 係一次過發布嘅完整 artifact set，包括 `snapshot.json`、`manifest.json`、`alerts.json`、`events.json` 同 `series/*.json`。Pipeline 先喺 staging directory 完成 fetch、normalize、transform 同 contract validation，全部成功先用 directory promotion 取代 live data；任何一步失敗都保留上一版完整資料。

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

Workflow 依序執行：fetch → validate/transform → 寫入獨立 schema v2 stage → Python tests → 喺臨時 workspace 用同一份 code 加 staged data 跑 frontend tests/build → atomic promote 完整 stage → commit generated `public/data` → push → Pages deploy。所有 gates 通過前，version-controlled `public/data` 都唔會被逐檔覆蓋。任何 data push 失敗會停止 deployment，唔會靜默略過。

Generated-data push 使用本次 job 嘅 repository `GITHUB_TOKEN`。按 [GitHub 官方觸發規則](https://docs.github.com/en/actions/concepts/security/github_token)，由呢個 token 造成嘅 push event 唔會建立另一個 workflow run，因此唔會形成 recursive data-commit loop。原本個 run 會喺 push 成功後直接上載已驗證嘅 `dist` 並部署 Pages；concurrency group 亦確保同一時間只得一個 production writer/deployer。唔好改用 PAT 或 GitHub App token，除非同時另外設計 recursion guard。

Cron 只係喚醒時間，而且 GitHub 可能延遲；collector 會用官方 observation/release metadata 判斷 `NOT_RELEASED_YET`、freshness 同 expected next update，唔會將 job start time 當 source as-of。

## Release 1–2 資料範圍

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

VIX/VIX3M、Cboe SKEW、BTC／ETH funding、trend 同 cross-asset transforms 有獨立 provider interface 同 fixture tests，但 production rights gate 維持關閉；佢哋會明確顯示 `UNAVAILABLE_FREE` 同精確原因，value 保持 `null`，亦唔會發 network request。未推出嘅 P2–P3 metric 同樣 fail closed。

## 文件

- [來源、授權同自動化 gate](docs/source-rights.md)
- [人工覆核及 manual import 政策](docs/manual-review.md)
- [故障排查](docs/troubleshooting.md)

本工具只供研究，唔提供投資建議。操作門檻、相關性及 proxy 指標唔代表因果，單一 metric 亦唔足以證明危機、泡沫轉折或資產方向。
