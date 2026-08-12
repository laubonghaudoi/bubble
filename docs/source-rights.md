# Source rights and automation policy

呢個 dashboard 將「公開可讀」同「可以自動抓取、製作衍生資料及公開再發布」分開處理。`config/source_registry.yml` 係 production gate；collector 只可以請求同時符合以下條件嘅 source：

- `enabled: true`；
- `network_eligible: true`；
- `rights.status: CLEARED`；
- `rights.automated_fetch: true`；
- `rights.public_redistribution: true`；
- 如 source 有 series allowlist，metric 必須逐項聲明並命中 allowlist。

任何一項唔成立都會 fail closed，唔會因 endpoint 無需登入就視為獲得再發布權。呢份工程分類按公開條款建立，唔係法律意見；條款或用途改變時要重新覆核。

## Production network sources

| Source | Auth／識別 | Production policy |
| --- | --- | --- |
| New York Fed Markets Data API | 無 key | P0 rates、ON RRP、SRF 可自動化；低頻存取、保存 observation date，並遵守 attribution/disclaimer。 |
| Treasury FiscalData | 無 key | Daily TGA 同 auction settlement 可自動化；`"null"` 字串要當缺失，並保留 dataset/as-of attribution。 |
| FRED government-origin allowlist | `FRED_API_KEY` repository secret | 只容許 IORB、WRESBAL、WALCL、WTREGEN；registry 已預留之後覆核嘅 NCBEILQ027S/GDP。每項仍要標示 FRED 同原發布機構。 |
| SEC EDGAR | `SEC_USER_AGENT` repository variable | 目前 P0 唔會抓 SEC，但 production workflow 要預先提供可識別 User-Agent；之後 Form 4/CompanyFacts 必須限速、cache 同引用 accession。 |
| CFTC PRE | 無 key | Release 2 只讀官方 TFF Futures Only dataset；E-mini S&P 500 同 Nasdaq-100 Consolidated、Asset Manager 同 Leveraged Funds 分開發布，並保留 weekly release lag。 |

## CFTC attribution and interpretation limits

CFTC 政府資料可按其 Web Policy 分發及複製，但要適當 acknowledgement；dashboard 會連結官方 PRE／COT 頁面，唔使用 CFTC seal，亦唔暗示 CFTC 認可、推薦或保證本工具。

Production 只會請求 TFF Futures Only dataset `gpe5-46if` 嘅兩個固定 CFTC contract market codes：

- `13874A`：E-mini S&P 500；
- `20974+`：Nasdaq-100 Consolidated。

數據係一般以星期二持倉、星期五 15:30 ET 發布；假期或官方 catch-up schedule 可以改變日期，所以 observation、release 同 retrieval timestamps 必須分開。Asset Manager／Institutional 同 Leveraged Funds 係 CFTC Form 40 business classifications，唔等於所有 CTA、唔代表實際 model exposure，亦唔係價格預測。

## FRED attribution and limits

使用 FRED API 嘅頁面／文件應清楚表示資料經 FRED API 取得，並且產品未獲 Federal Reserve Bank of St. Louis 認可或認證。FRED access 只係傳輸途徑；series owner 嘅 rights 仍然適用。

Release 1 禁止透過 FRED 自動抓取／公開再發布以下第三方 series：

- S&P 500 (`SP500`)；
- Nasdaq Composite (`NASDAQCOM`)；
- Cboe VIX/VIX3M (`VIXCLS`、`VXVCLS`)；
- Coinbase Bitcoin (`CBBTCUSD`)；
- 任何其他未加入 `fred_government.series_allowlist` 嘅 series。

新增 FRED series 時必須先確認原 publisher、再發布權、正確 attribution 同 metric definition；唔可以只擴闊 allowlist 來繞過 rights review。

Public dashboard 必須顯眼展示 FRED API 指定嘅 non-endorsement notice、Terms link、使用者受 Terms 約束嘅說明，以及靜態站 privacy disclosure。

## SEC fair-access identification

Production `SEC_USER_AGENT` 固定使用：

```text
Bubble USD Liquidity Dashboard laubonghaudoi@icloud.com
```

唔好提交真實 key 或個人 secret 到 Git。Collector 必須保持低於 SEC 公布 aggregate access ceiling、採用 cache/backoff，並以 filing URL／accession 引用 factual extraction。Issuer 撰寫嘅長篇 narrative 唔應原文再發布。

## Rights-held sources

以下來源即使技術上有公開 download/API，production 都係 disabled、`network_eligible: false`：

- FINRA margin statistics：公開條款未清除 automated database construction、bulk monitoring 同 redistribution；
- Cboe indices/options statistics：未有適合本公開 dashboard 嘅 storage/derived-publication licence；
- State Street SPY holdings：未有自動再發布同第三方 disclosure permission；
- Coinbase/Bybit funding：公開 endpoint 唔等於 derived chart redistribution licence；
- future proprietary provider：未有合約前保持 disabled。

呢啲 metric 只可以顯示 `MANUAL_READY` 或 `UNAVAILABLE_FREE` 及準確原因，value 必須為 `null`。取得書面 permission 後，先更新 source rights record、methodology note、fixture/contract tests，再啟用 collector。

## Required attribution in published metadata

每個 active metric/source 應帶：

- source name、official URL、tier；
- observation/release/retrieval timestamps；
- `rights_note`；
- metric methodology 內嘅 `source_and_license_note`；
- proxy metric 嘅明確 `proxy_disclosure`。

New York Fed reference-rate series亦應按其條款顯示指定 attribution/disclaimer，包括 publisher 名稱、non-endorsement、no-liability 同 Terms link；唔可以暗示 New York Fed、St. Louis Fed、SEC 或其他機構認可本 dashboard。
