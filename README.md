# 美元流動性監測

一個以 React/Vite 建立、由 GitHub Pages 托管嘅靜態儀錶板。瀏覽器只讀取版本控制內的 JSON；所有第三方抓取、驗證、衍生計算及規則解釋均由 Python pipeline 完成。

## 本地開發

```bash
npm ci
python -m pipeline.update --mode incremental
npm run dev
```

生產驗證：

```bash
python -m pytest pipeline/tests
npm test
npm run build
```

完整回填入口為 `python -m pipeline.backfill --all`（目前使用與 incremental 相同的安全 collector，後續可按來源擴展歷史窗口）。現有 JSON 可離線 build；來源失敗時 pipeline 保留已提交 series，並標示 `stale`／`error`，永不以零代替缺失。

## 數據覆蓋

- 自動：NY Fed SOFR/EFFR/OBFR/TGCR/BGCR、FRED IORB/WRESBAL/WALCL/WTREGEN、Treasury TGA。
- 明確缺口：ON RRP、SRF operation parser、市場結構代理及季度 CapEx，UI 以 `missing` 顯示。
- 付費／人工：gamma flip、0DTE、skew、forward P/E、產業合約訊號，絕不生成代替數字。

## GitHub Pages 部署

1. 將 repo 推送到 GitHub，於 **Settings → Pages → Source** 選擇 **GitHub Actions**。
2. 執行 `Update data and deploy Pages` workflow；workflow 亦會在美國工作日兩次排程更新。
3. 如啟用 SEC collector，設定 repository variable `SEC_USER_AGENT` 為可識別的專案名稱及聯絡電郵。
4. 預設 `GITHUB_TOKEN` 已足夠；workflow 只需要 `contents: write`、`pages: write`、`id-token: write`，不需要 API secret。

GitHub Pages URL 會是 `https://<owner>.github.io/<repository>/`。Vite 及 data fetch 使用相對 base path，可支援 project subpath。

## 故障排查

- `snapshot.json` 載入失敗：先跑 pipeline，確認 `public/data/snapshot.json` 存在。
- 某來源 stale：開啟儀錶板「來源狀態」查看 as-of 與官方連結；重新 dispatch workflow。
- Pages 404：確認 Pages source 為 GitHub Actions，並查看 `deploy-pages` job artifact。
- Pipeline schema failure：外部欄位可能已變；不要部署，先更新 collector contract/fixture。

本工具只供研究，唔提供投資建議。操作門檻、相關性及代理指標不代表因果。
