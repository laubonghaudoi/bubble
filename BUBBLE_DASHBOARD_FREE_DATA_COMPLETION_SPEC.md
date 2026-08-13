# Bubble 美元流動性儀錶板：免費數據補完 Implementation Spec

> 交付對象：Codex／本地 coding agent<br>
> 目標網站：<https://laubonghaudoi.github.io/bubble/><br>
> 原始影片：<https://www.youtube.com/watch?v=MrnjBdgQPLU><br>
> 基線審查日期：2026-08-12<br>
> 核心限制：**目前只使用免費、公開、合法取得嘅數據；唔購買數據，亦唔將 proxy 冒充原指標。**

---

## 0. 畀 Codex 嘅執行指令

請先完整閱讀本文件，再檢查現有 repository、資料 schema、GitHub Actions、測試及 frontend。**唔好重建整個網站**；應沿用現有設計、元件、色彩、三個 switch、JSON pipeline 同 GitHub Pages 部署方式，逐步補完缺口。

工作方式：

1. 先用 `rg --files`、`rg`、現有 tests 同 workflow 理解 repo，唔好假設下文建議嘅路徑已經存在。
2. 保存現有已接通指標及用戶修改；唔覆蓋無關改動。
3. 將每個指標歸入以下其中一種狀態：
   - `ACTIVE_FREE`：免費來源、已自動更新；
   - `ACTIVE_PROXY`：免費 proxy、已自動更新，畫面必須寫明 proxy；
   - `MANUAL_READY`：已完成 schema、UI、校驗及人工匯入接口；
   - `UNAVAILABLE_FREE`：免費數據不足，清楚解釋原因；
   - `STALE`：曾成功更新，但最新抓取失敗／未發布；
   - `ERROR`：格式或校驗失敗，唔可以當成零。
4. **任何缺失值必須係 `null`，絕對唔可以係 `0`。**
5. 免費 proxy 唔可以沿用付費原指標名稱。例如 `CFTC leveraged-funds positioning proxy` 唔可以顯示成「CTA 實際倉位」；`VIX/VIX3M proxy` 唔可以顯示成完整 VIX futures curve。
6. 每個新增指標都要有：來源、頻率、as-of、updated-at、單位、計算方法、資料品質、freshness、限制、粵文解釋及測試。
7. 逐 phase 完成，每個 phase 都要跑測試及 build；唔好等全部寫完先驗證。

---

## 1. 現況基線及今次真正要解決嘅問題

2026-08-12 審查 live site 時，首頁顯示：

- `11 ACTIVE`
- `20 NOT WIRED`
- source health `3/7`
- `Liquidity Fuel` 有資料，但 `Market Ignition` 同 `Fundamental Exit` 係 `UNAVAILABLE`

現時已接通：

- SOFR、IORB、SOFR−IORB
- EFFR、OBFR、TGCR、BGCR
- Daily TGA
- Reserve Balances、Fed Total Assets、H.4.1 TGA

現時問題唔係「畫面有冇指標名」，而係：

1. 部分核心免費數據仍未接通，例如 ON RRP、SRF；
2. 已有原始數據，但欠缺影片要求嘅衍生統計、趨勢及警報；
3. 技術日期只係文字 caveat，未成為可計算嘅 calendar context；
4. 市場結構、泡沫及 CapEx 模組大部分仍然只係 placeholder；
5. 幾個指標本身依賴付費／專有資料，必須用清楚標籤嘅免費 proxy 或保留 unavailable，唔可以偽造；
6. methodology modal 太通用，未能解釋每個指標本身嘅金融意義。

### 1.1 今次完成後嘅定義

完成後，頁面唔應再有模糊嘅 `NOT WIRED`：

- 可以免費自動化嘅指標全部變成 `ACTIVE_FREE`；
- 有合理免費替代嘅變成 `ACTIVE_PROXY`；
- 只可由公開文件人工整理嘅變成 `MANUAL_READY`；
- 真正無可靠免費數據嘅變成 `UNAVAILABLE_FREE`，並顯示原因同可接受嘅未來 provider interface。

換句話講，「全部包含」唔代表每張卡都有一個假數字，而係每項都有**真實可審核嘅 implementation state**。

---

## 2. 不可妥協嘅資料原則

### 2.1 免費來源優先次序

1. 美國官方來源：Federal Reserve、New York Fed、Treasury FiscalData、SEC、FINRA、CFTC；
2. 指標／產品官方發布者：Cboe、State Street、交易所公開 API；
3. FRED 作官方或來源方數據嘅便利分發層；
4. 有清楚標示嘅免費 proxy；
5. 人工輸入公開披露數據；
6. 付費數據接口只保留 schema，唔抓取、唔估算。

禁止：

- scrape 需要登入或規避限制嘅頁面；
- 使用未授權 key、cookie 或付費 API；
- 將搜尋結果摘要當數據；
- 將 stale value 當今日值；
- 將 fetch error、未發布、休市同真實零值混埋；
- 以名稱相近但定義唔同嘅免費 series 冒充原指標。

### 2.2 Last-good-value policy

Collector 失敗時：

- 保留上一個成功值；
- `quality.status = "STALE"`；
- 保存 `last_success_at`、`expected_next_update`、`failure_reason`；
- UI 顯示「沿用最後成功值」，唔可以顯示成正常更新；
- switch 計分時，過期超過容許窗口嘅值視為 unavailable，而唔係 neutral。

### 2.3 日期與單位

- 市場／操作日期一律保存 `America/New_York` date；
- pipeline timestamp 用 ISO-8601 UTC；
- 利率原值保存百分點，例如 `3.64` 代表 3.64%；
- 利差保存 bp；
- Fed/Treasury amount 統一保存 `USD billions`；
- 股票／宏觀月度與季度 series 唔可以 forward-fill 後假裝成每日新 observation；
- UI 同時顯示 observation date、source release time 同 pipeline update time。

---

## 3. Phase P0：先補完整核心美元流動性

P0 係最高優先級。完成前，網站唔應宣稱影片核心流動性監測已完整。

### 3.1 完成 SOFR−IORB 及其他 confirmation spreads

#### 必須輸出

對以下每條 rate series：SOFR、EFFR、OBFR、TGCR、BGCR，與同一有效 observation date 嘅 IORB 做 backward as-of join；不可線性插值。

```text
spread_bp(t) = (market_rate_pct(t) - IORB_pct(asof t)) * 100
```

新增：

- `sofr_iorb_spread_bp`
- `effr_iorb_spread_bp`
- `obfr_iorb_spread_bp`
- `tgcr_iorb_spread_bp`
- `bgcr_iorb_spread_bp`

每條 spread 要保存：

```json
{
  "latest": -1.0,
  "change_1obs": 1.0,
  "change_5obs": 2.0,
  "mean_5obs": -0.4,
  "slope_5obs_bp_per_obs": 0.4,
  "positive_streak": 0,
  "above_3bp_streak": 0,
  "observations_used": 5
}
```

`1obs`、`5obs` 係有效發布觀察值，唔係自然日。

#### 初始 alert 規則

- `WATCH`：SOFR−IORB 連續 3 個 observation > 0；或最新 > +3 bp；
- `ELEVATED`：SOFR−IORB 連續 3 個 observation > 0，而且 EFFR−IORB／TGCR−IORB／BGCR−IORB 至少一項同時向上；
- `STRESS`：上述條件再加非技術日 SRF 使用、Reserve Balances 4w 明顯下降，或多個 funding spread 同時惡化；
- 單日 spike 唔可直接判成危機。

`+3 bp` 只係可配置操作門檻：

```yaml
alerts:
  sofr_iorb_watch_bp: 3
  positive_streak_observations: 3
  confirmation_required_for_elevated: true
```

### 3.2 接通 ON RRP 使用量

首選來源：New York Fed Markets Data API。可用 FRED `RRPONTSYD` 作 no-key fallback／cross-check：

- <https://markets.newyorkfed.org/static/docs/markets-api.html>
- <https://fred.stlouisfed.org/series/RRPONTSYD>
- <https://www.newyorkfed.org/markets/desk-operations/reverse-repo>

實作要求：

- 使用 accepted amount，而唔係 offering limit；
- 同日多個 operation 要按定義 aggregate；
- 保存 source-specific raw value，同時產生 canonical `on_rrp_accepted_usd_bn`；
- 輸出 level、1 observation change、5 observation change、20 observation percentile／trend；
- 加 `near_floor_context`，但唔使用硬編碼「低過某數字就一定危險」；
- 說明：ON RRP 下降可以為 QT/TGA 上升提供 liability-side cushion，但下降亦可能只係 bills/repo 回報更吸引。

### 3.3 接通 SRF 使用量

首選來源：New York Fed repo operation results：

- <https://www.newyorkfed.org/markets/desk-operations/repo>
- <https://markets.newyorkfed.org/static/docs/markets-api.html>
- <https://www.newyorkfed.org/markets/repo-agreement-ops-faq>

實作要求：

1. 按 operation date aggregate 同一日早上及下午 operation；
2. 按 Treasury、agency debt、agency MBS 保存 breakdown；
3. 保存 submitted、accepted、rate（來源有提供先保存）；
4. 識別 small-value／operational-readiness exercise；呢類值保存，但標記 `technical_exercise=true`，唔計入壓力 alert；
5. 真正警報使用 `accepted_amount`，唔使用 facility rate；
6. `RPONTSYD` 只可作「Fed repo operations total」fallback。若無法證明數值只屬 SRF，**唔可以改名做 SRF usage**；
7. 顯示 1d、5d、positive-use streak、technical-day flag。

SRF 判讀：

- 技術日／演習單日使用：降低信心，唔自動報警；
- 非技術日持續使用，而且 SOFR/TGCR spread 同時升：較強 funding pressure confirmation；
- 使用後下一日回零：通常弱過持續使用。

### 3.4 技術性扭曲 calendar

建立 canonical event calendar，例如：

```json
{
  "date": "2026-09-30",
  "flags": ["MONTH_END", "QUARTER_END", "TREASURY_SETTLEMENT"],
  "treasury_settlement_usd_bn": 125.0,
  "tax_window": false,
  "confidence_adjustment": -1,
  "sources": []
}
```

#### 自動事件

- `MONTH_END`：每月最後一個美國有效工作日；
- `QUARTER_END`：3、6、9、12 月最後一個有效工作日；
- `YEAR_END`；
- `TREASURY_SETTLEMENT`：Treasury auction dataset 嘅 `issue_date`／settlement date；
- `LARGE_TREASURY_SETTLEMENT`：按該日可用金額合計及自身歷史 percentile 標示，門檻要 configurable；
- `TAX_WINDOW`：由 version-controlled calendar 維護官方報稅／估算稅期限及相鄰工作日；
- 美國假期／非發布日。

Treasury 來源：

- <https://fiscaldata.treasury.gov/datasets/treasury-securities-auctions-data/>
- <https://fiscaldata.treasury.gov/datasets/upcoming-auctions/>
- <https://fiscaldata.treasury.gov/api-documentation/>

Tax calendar 由 `config/us_tax_dates.yml` 人工審核；每項必須有 IRS source URL、tax type、original deadline、observed deadline。唔好只靠「每年固定 4 月 15 日」推算，因為周末、假期及災區延期會改變日期。

IRS 參考：<https://www.irs.gov/businesses/small-businesses-self-employed/tax-calendar>

#### Alert 處理

- 技術日期**唔刪除數據**；
- 只將 confidence 降一級；
- 若 EFFR、repo spreads、SRF、reserves 同時惡化，不可因季尾而完全 suppress；
- 每日解釋要列出具體 event，而唔係永遠顯示同一句 boilerplate。

### 3.5 補完 H.4.1

來源：

- Reserve Balances：FRED `WRESBAL`
- Fed Total Assets：FRED `WALCL`
- Weekly TGA：FRED `WTREGEN`
- 官方 release：<https://www.federalreserve.gov/releases/h41/>

每條週度 series：

```text
change_1w = value[t] - value[t-1]
change_4w = value[t] - value[t-4]
```

要求：

- 顯示 level、1w、4w；
- 單位由 USD millions 轉 USD billions；
- 週度資料 UI 絕對唔可以寫 `1D`；
- 首頁嘅 2.9、2.8、2.5 萬億美元只係 `reference_zone`，唔係危機門檻；
- reference lines 要清楚寫「參考區間會隨銀行體系規模、監管及 reserve demand 改變」；
- Reserve chart 切換後，ARIA label／alt text 必須跟住變，唔可以仍然講 SOFR−IORB；
- 星期四未發布時顯示 `NOT_RELEASED_YET`，保留上週值；官方通常星期四約 4:30 p.m. ET 發布。

### 3.6 P0 UI 修正

- 將 `1D Δ` 改成依頻率動態顯示 `1 OBS`、`1W`、`1M` 或 `1Q`；
- SOFR−IORB 卡顯示 1obs、5obs、positive streak、technical flag；
- Weekly H.4.1 卡顯示 1w、4w；
- ON RRP、SRF 由 placeholder 移入 active table；
- 今日解讀必須包含：觀察、金融意義、替代解釋、確認訊號、不可推論；
- source health 要以 collector 實際狀態計，唔以 card 數量計。

---

## 4. Phase P1：用免費數據建立 Market Ignition

> 2026-08-12 implementation lock：本節保留完整 provider／transform interface 作未來 permission-ready 路線，但 production 只啟用 rights-cleared CFTC TFF Futures Only positioning。Cboe VIX/VIX3M、SKEW、Coinbase／Bybit funding、third-party FRED price series、trend 同 cross-asset inputs 未獲明確公開再發布權前一律 `UNAVAILABLE_FREE`、value `null`、network disabled。現階段 Market Ignition coverage 預期係 positioning `1/4`，`assessment: null`，只報 direction／confidence，唔產生 `WATCH`／`STRESS`。呢項後來鎖定決定凌駕本節較早嘅 `3/4` 或 active-source驗收描述。

### 4.1 VIX term-structure proxy

免費穩定版本先使用：

- VIX：FRED `VIXCLS`
- 3-month VIX：FRED `VXVCLS`
- Cboe 指標頁：<https://www.cboe.com/us/indices/dashboard/vix3m/>

計算：

```text
vix_vix3m_ratio = VIX / VIX3M
term_spread = VIX3M - VIX
```

初始狀態：

- ratio < 1：近月 vol 低過 3 個月，proxy contango；
- ratio >= 1：proxy inversion／短期壓力；
- 必須配合歷史 percentile，唔好只用一條硬線。

命名必須係 `VIX/VIX3M term-structure proxy`，唔可以叫「VIX futures curve」。如 Cboe 免費 CSV 可穩定取得 VIX9D/VIX1D/VIX6M，可作 supplemental tenors；fetch 失敗要保留兩點 proxy。

### 4.2 Tail-skew proxy

使用 Cboe SKEW Index：

- <https://www.cboe.com/us/indices/dashboard/skew/>

顯示 SKEW level、5d／20d change、3y percentile。名稱使用 `Cboe SKEW tail-risk proxy`。

注意：SKEW Index 唔等於 put/call implied-volatility skew，更唔等於 dealer positioning。因此唔可以將原本 `Put/call skew` 卡直接改名後扮成同一指標；應另建 proxy card，原卡改為 `UNAVAILABLE_FREE` 或 `MANUAL_READY`。

### 4.3 BTC／ETH perpetual funding

使用無需付費嘅公開 exchange API，至少一個 primary 加一個 fallback：

- Bybit funding history：<https://bybit-exchange.github.io/docs/v5/market/history-fund-rate>
- Coinbase public funding history：<https://docs.cdp.coinbase.com/api-reference/market-data/public-get_funding_rate_history>
- 可選 Cboe regulated continuous-futures funding：<https://www.cboe.com/en/tradable-products/cryptocurrency/continuous-futures/funding-rate-data/>

實作 BTC 同 ETH：

- 原始 funding rate；
- funding interval；
- 過去 24h 已結算 funding 合計；
- 7d mean、7d percentile；
- source／venue；
- 多 venue 都可用時顯示 median，同時保存各 venue 值；
- 只有單一 venue 時降低 confidence；
- 唔可以假設全部產品固定 8 小時；按 API interval 正規化。

Crypto funding 係槓桿情緒／擠倉風險指標，唔係美元銀行準備金指標。

### 4.4 CFTC positioning／CTA proxy

來源：

- <https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm>
- <https://www.cftc.gov/MarketReports/CommitmentsofTraders/HistoricalCompressed/index.htm>

使用 Traders in Financial Futures（TFF）或官方 Public Reporting Environment。初始合約：

- S&P 500 consolidated／E-mini S&P 500；
- Nasdaq-100；
- 可選 10Y Treasury、美元指數相關合約。

計算：

```text
net_position = long - short
net_pct_open_interest = (long - short) / open_interest
zscore_3y = zscore(net_pct_open_interest over 156 weeks)
```

至少保存 Asset Manager/Institutional 同 Leveraged Funds 兩組，唔好將佢哋混成一個數字。

命名：

- `CFTC leveraged-funds positioning proxy`
- `CFTC asset-manager positioning`

唔可以叫「CTA 真實倉位」；CFTC category 並唔等於所有 CTA，而且週頻有滯後。

可另外建立 rule-based `trend-following proxy`：

- 20d／60d price momentum；
- 20d vs 60d moving-average regime；
- CFTC leveraged-funds percentile。

但要將 model inputs 同公式完整顯示，唔好輸出一個神秘「CTA buy/sell level」。

### 4.5 Price／position consolidation 與 8–12 週窗口

加入 40 同 60 個交易日視窗（約 8–12 週）：

- SP500／NASDAQCOM 40d、60d return；
- 20d、60d realized volatility；
- price above/below 20d/60d moving average；
- CFTC positioning 8w/12w change；
- funding 8w percentile（資料足夠先計）；
- SOFR−IORB 40/60-observation trend。

前端範圍加入 `8W`、`12W`，並寫明係 regime window，唔係預測「市場一定在 8–12 週內轉向」。

### 4.6 Cross-asset correlation

可用免費 FRED series，例如：

- `SP500`
- `NASDAQCOM`
- `DGS10`（使用 yield change，唔係 level return）
- `DTWEXBGS`（美元廣義指數）
- `DCOILWTICO`
- `CBBTCUSD`

對價格 series 用 log return；對 yield 用 basis-point change。計算 20d、60d rolling pairwise correlations，至少顯示：

- equity vs USD；
- equity vs 10Y yield change；
- equity vs BTC；
- equity vs oil。

缺少共同日期時使用 inner join；每個 correlation 保存 sample size。`n < 15` 不發布 20d 值，`n < 40` 不發布 60d 值。

### 4.7 Market Ignition switch

四個獨立 evidence blocks：

1. volatility term structure；
2. trend／positioning；
3. options／tail-risk proxy；
4. crypto funding／cross-asset confirmation。

輸出格式唔好只寫 `0/4`，而要分開：

```json
{
  "triggered_blocks": 1,
  "available_blocks": 3,
  "total_blocks": 4,
  "status": "WATCH",
  "confidence": "MEDIUM"
}
```

若少過 3 個 block 有新鮮資料，switch 必須係 `UNAVAILABLE` 或 `LOW_CONFIDENCE`，唔可以 neutral。

---

## 5. Phase P2：七個泡沫／脆弱度指標

> 2026-08-12 implementation lock：production P2 hard-cut為兩項 active proxy加六項 `UNAVAILABLE_FREE`，畫面顯示 `2/8 CONTEXT AVAILABLE`，而唔係本節早期「七個」或全部 active假設。Active IDs係 `nonfinancial_equities_gdp_proxy`同`sec_form4_nonderivative_ps_count_ratio_20d`；rights/input hold係 FINRA margin、SPY Top-10、SPX 0DTE、NDX forward P/E、M2/Nasdaq同 gamma flip。`put_call_vol_skew`由P1 Cboe rights-held interface涵蓋，P2唔重複。SEC官方 code `P`／`S`代表 open-market **或 private** purchase/sale，structured XML無法分離純open-market，因此proxy名稱、methodology同驗收一律用reported non-derivative P/S count，唔作純open-market聲稱。P2只係fragility context，永遠唔改P1 switch、P0 overall或任何 severity；呢項後來鎖定決定凌駕本節舊描述。

### 5.1 免費可自動化

#### A. FINRA margin debt

來源：

- <https://www.finra.org/rules-guidance/key-topics/margin-accounts/margin-statistics>
- 官方 Excel：<https://www.finra.org/sites/default/files/2021-03/margin-statistics.xlsx>

輸出：

- Customer debit balances level；
- MoM、YoY；
- 5y／全歷史 percentile；
- 相對 SP500 market proxy 或 nominal GDP 嘅 ratio（清楚標明衍生）；
- release lag／as-of month。

Excel schema 改變時 fail closed；用欄位名稱 mapping，唔好只靠固定 column number。

#### B. S&P 500 Top-10 weight proxy

免費來源用 SPY daily holdings：

- <https://www.ssga.com/us/en/intermediary/etfs/state-street-spdr-sp-500-etf-trust-spy>
- holdings XLSX：<https://www.ssga.com/library-content/products/fund-data/etfs/us/holdings-daily-us-en-spy.xlsx>

計算 top 10 securities weight sum。名稱必須係 `SPY holdings Top-10 weight proxy`，因為 ETF holdings 未必同官方 S&P index closing weights 完全一致。

要固定定義係「top 10 securities」；GOOG/GOOGL 等 share classes 分開計。如果日後要公司級 concentration，另開 metric，唔好靜默合併。

#### C. Buffett indicator proxy

使用：

- FRED `NCBEILQ027S`：Nonfinancial Corporate Business; Corporate Equities; Liability, Level
- FRED `GDP`：nominal GDP

```text
equity_usd_bn = NCBEILQ027S_usd_mn / 1000
buffett_proxy_pct = equity_usd_bn / GDP_usd_bn * 100
```

名稱：`Nonfinancial corporate equities / GDP proxy`。呢個唔係完整美股總市值，因此唔可以只顯示「Buffett Indicator」而無 proxy 標籤。

顯示 level、QoQ、YoY、10y percentile；註明 Z.1 數據會 revision，而 stock 對 GDP flow ratio 亦受利率及海外收入影響。

#### D. M2 vs Nasdaq divergence

來源：

- FRED `M2SL`
- FRED `NASDAQCOM`

將 NASDAQCOM 轉成 month-end observation，同 M2 月度日期對齊：

```text
m2_yoy_pct = pct_change(M2SL, 12)
nasdaq_yoy_pct = pct_change(NASDAQ_month_end, 12)
divergence_pp = nasdaq_yoy_pct - m2_yoy_pct
divergence_z_10y = rolling_zscore(divergence_pp, 120 months, min 60)
```

顯示兩條 normalized index（base=100）同 divergence；唔可以將 correlation 當 causation。

#### E. Insider buy/sell proxy

來源：SEC EDGAR Form 4 XML：

- <https://www.sec.gov/search-filings/edgar-application-programming-interfaces>
- <https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data>

最低可行定義：

- 只計 non-derivative transactions；
- transaction code `P` = open-market purchase；
- transaction code `S` = open-market sale；
- 排除 `A`、`M`、`F`、`G` 等 grant/exercise/tax/gift；
- count ratio 同 dollar ratio 分開；
- 缺 transaction price 嘅 filing 只入 count，不入 dollar ratio；
- 可辨識 10b5-1 時保存 flag，顯示 inclusive 同 ex-10b5-1 版本；
- 5d、20d aggregation；
- 保存 filings processed、parse failures、dollar-coverage rate。

```text
count_ratio = (purchase_count + 1) / (sale_count + 1)
dollar_ratio = purchase_dollars / sale_dollars
```

Dollar coverage 未達 80% 時，只顯示 count ratio，dollar ratio 標 `LOW_COVERAGE`。

SEC 要求宣告 User-Agent；用 repository variable `SEC_USER_AGENT="project-name contact-email"`，限速、重試及 cache。唔可以平行暴力抓取 filings。

### 5.2 免費資料不足，唔可以偽造

#### F. SPX 0DTE share

正確定義需要一致嘅 SPX option volume by expiration。若 Cboe 有穩定、公開、條款容許自動化嘅下載，先實作：

```text
0dte_share = SPX contracts expiring same day / all SPX option contracts
```

否則：

- 狀態改為 `MANUAL_READY`；
- 提供 CSV import；
- 必須保存 numerator、denominator、session date、Cboe source URL；
- 唔可以用所有市場 0DTE volume、新聞數字或 ETF options 冒充 SPX share。

#### G. NDX forward P/E

一致嘅 consensus forward earnings 通常屬 FactSet／Bloomberg／LSEG／S&P Capital IQ 等專有數據。無可靠免費來源時：

- 保持 `UNAVAILABLE_FREE`；
- UI 解釋「缺少一致、可重現嘅 forward earnings consensus」；
- 可另建 `NDX trailing P/E public proxy`，但名稱、方法及 card 必須同 forward P/E 分開；
- 唔可以從幾篇新聞手動抄一個數字當持續 series。

---

## 6. Phase P3：CapEx 二階導數及產業真實需求

### 6.1 Hyperscaler scope

第一版固定：

- Microsoft
- Alphabet
- Amazon
- Meta

`config/companies.yml` 保存：ticker、CIK、fiscal-year-end、首選 XBRL tags、fallback tags、公司 CapEx 定義、已知披露差異、人工 override。

### 6.2 SEC CapEx collector

來源：

- SEC Company Facts API
- 公司 10-Q／10-K filing
- <https://www.sec.gov/search-filings/edgar-application-programming-interfaces>

首選 cash CapEx tag 通常包括 `PaymentsToAcquirePropertyPlantAndEquipment`，但唔可以假設四間公司永遠用同一 tag。每公司 mapping 要 fixture test。

Quarterization：

```text
Q1 = reported Q1 YTD
Q2 = reported H1 YTD - Q1
Q3 = reported 9M YTD - H1 YTD
Q4 = reported FY - Q1 - Q2 - Q3
```

必須處理：

- fiscal year 非 calendar year；
- 10-K／10-Q amended filings；
- units、scale、duplicate facts；
- FY context 同 YTD context；
- cash CapEx vs finance lease／equipment acquired under leases；
- filing revision；
- 公司改 tag 或改定義。

每個 quarter 保存 extracted fact、source accession、filing URL、tag、frame/context、quarterization method、manual-review flag。

### 6.3 一階及二階導數

對每公司同 aggregate：

```text
qoq_growth_t = CapEx_t / CapEx_(t-1) - 1
yoy_growth_t = CapEx_t / CapEx_(t-4) - 1
qoq_acceleration_t = qoq_growth_t - qoq_growth_(t-1)
yoy_acceleration_t = yoy_growth_t - yoy_growth_(t-1)
```

Aggregate 先加總 dollar CapEx，再計 growth／acceleration；唔好直接平均公司 growth rate。

狀態語言：

- acceleration > 0：增長加速；
- acceleration < 0 且 growth > 0：仍然增長，但增速放慢；
- growth < 0：CapEx 絕對值收縮；
- 呢啲只係evidence direction，唔對應`WATCH`／`STRESS`；連續季度或orders/backlog只會增加coverage／confidence，唔會自動升級severity。

UI 必須顯示 level、QoQ、YoY、QoQ acceleration、YoY acceleration，同時提供至少 12 季歷史。

### 6.4 Orders／backlog／prepayments／take-or-pay

呢啲 disclosure 缺乏標準 XBRL tag，第一版做 `MANUAL_READY`，唔用 LLM 自動猜數字。

建立 `data/manual/industry_signals.csv`：

```csv
company_id,period_end,metric_id,direction,value,unit,yoy_pct,comparable,source_type,source_url,filing_accession,filing_accepted_at,as_of,reviewer,reviewed_at,paraphrase,review_note
microsoft,2026-06-30,ai_upstream_orders_backlog,UNKNOWN,,,,false,10-K,https://www.sec.gov/Archives/edgar/data/789019/000119312526323660/msft-20260630.htm,0001193125-26-323660,2026-07-29T20:08:01Z,2026-07-29,reviewer@example.com,2026-07-30T02:00:00Z,"No comparable numeric disclosure was published for this reviewed scope.","Period scope and comparability checked against the filing."
```

規則：

- value 可以係 `null`；
- 每一行必須有 source URL 同 period；
- 定義轉變要 `comparable=false`；
- narrative disclosure 可用 `direction = UP|FLAT|DOWN|UNKNOWN`，但要保存原始短 paraphrase，唔長篇複製受版權文本；
- UI 顯示 `MANUAL / PUBLIC FILING`；
- 可以建立 filing keyword discovery（order、backlog、remaining performance obligations、purchase commitments、prepayment、take-or-pay），但只用來提示人工覆核，唔直接發布數值。

### 6.5 Fundamental Exit switch

四個 blocks：

1. aggregate CapEx acceleration；
2. upstream orders/backlog；
3. customer prepayments／contract commitments；
4. breadth：至少幾多間 hyperscaler 同方向。

後續鎖定實作將本頁固定為 `EVIDENCE_ONLY`：每個block可以各自報direction同confidence，但switch `assessment`永遠係`null`，唔會輸出`WATCH`／`STRESS`。Coverage只描述可用證據；初始兩個automated blocks為`2/4 / LOW`，並不等於neutral或exit signal。若日後研究高信心exit hypothesis，至少應要求：

- aggregate acceleration 連續兩季轉負；
- 至少兩間公司或一個 upstream signal 確認；
- 唔可以由單一公司單季 timing 判定整個 AI cycle 結束。

---

## 7. 無可靠免費數據嘅指標：正式處理方式

以下唔應再顯示模糊 `NOT WIRED`，而要顯示清楚狀態：

| 原指標 | 免費版處理 | 可否自動宣稱原值 |
|---|---|---:|
| Gamma flip level | `UNAVAILABLE_FREE`；提供 manual/provider schema；可另做明確標示嘅 gross OI proxy | 否 |
| Put/call vol skew | Cboe SKEW 另作 `ACTIVE_PROXY`；原卡 `MANUAL_READY`/`UNAVAILABLE_FREE` | 否 |
| SPX 0DTE share | Cboe 穩定公開下載先自動化，否則 `MANUAL_READY` | 視來源 |
| NDX forward P/E | `UNAVAILABLE_FREE`；可另列 trailing proxy | 否 |
| Proprietary CTA exposure | CFTC + trend model `ACTIVE_PROXY` | 否 |
| Exact industry orders/backlog | SEC filing manual workflow | 否 |

每張 unavailable card 都要顯示：

- 點解免費數據不足；
- 缺少嘅核心 input；
- 點解簡單 proxy 會誤導；
- 如果日後有合法 provider，預期接入嘅 interface；
- `last_value = null`，唔係零。

### 7.1 Manual/provider schema

```json
{
  "metric_id": "gamma_flip",
  "availability": "UNAVAILABLE_FREE",
  "value": null,
  "unit": "SPX index points",
  "as_of": null,
  "provider": null,
  "manual_override": null,
  "reason": "Reliable dealer net gamma and trade-direction inputs are not publicly available.",
  "source_url": null
}
```

---

## 8. 統一 JSON contract

沿用現有 schema；若現有 schema 唔支援以下欄位，做 backward-compatible migration。

```json
{
  "metric_id": "on_rrp_accepted",
  "label": "ON RRP 使用量",
  "availability": "ACTIVE_FREE",
  "value": 10.5,
  "unit": "USD bn",
  "frequency": "business_daily",
  "observation_date": "2026-08-11",
  "released_at": "2026-08-11T18:00:00Z",
  "updated_at": "2026-08-11T18:15:00Z",
  "expected_next_update": "2026-08-12",
  "changes": {
    "one_observation": -1.2,
    "five_observations": -3.4,
    "twenty_observations": -8.1
  },
  "quality": {
    "status": "OK",
    "freshness": "FRESH",
    "last_success_at": "2026-08-11T18:15:00Z",
    "failure_reason": null,
    "sample_size": 250
  },
  "context": {
    "technical_flags": [],
    "is_proxy": false,
    "confidence": "HIGH"
  },
  "source": {
    "name": "Federal Reserve Bank of New York",
    "url": "https://www.newyorkfed.org/markets/desk-operations/reverse-repo",
    "tier": "OFFICIAL",
    "retrieved_at": "2026-08-11T18:15:00Z"
  },
  "methodology": {
    "question": "有幾多合資格現金停泊喺 Fed？",
    "why_it_matters": "ON RRP 下降曾經為 TGA 上升同 QT 提供緩衝。",
    "calculation": "Daily accepted amount aggregated across eligible ON RRP operations.",
    "common_misread": "下降唔一定係 risk-on liquidity injection。",
    "confirm_with": ["TGA", "Reserve Balances", "SOFR−IORB"],
    "cannot_infer": "唔可以單靠 ON RRP 預測股票升跌。"
  }
}
```

### 8.1 Snapshot-level fields

`snapshot.json` 加：

```json
{
  "schema_version": "2.x",
  "market_date": "2026-08-11",
  "pipeline_updated_at": "...",
  "technical_context": {},
  "switches": {},
  "source_health": {},
  "active_free_count": 0,
  "active_proxy_count": 0,
  "manual_ready_count": 0,
  "unavailable_free_count": 0,
  "stale_count": 0
}
```

---

## 9. 每個 metric 嘅專屬知識 metadata

而家 ON RRP modal 類似通用模板。請為每項建立真正專屬內容，最少包括：

1. `question`：個指標回答咩問題；
2. `definition`：精確定義；
3. `why_it_matters`：傳導機制；
4. `direction`：升／跌通常代表乜；
5. `calculation`；
6. `frequency_and_lag`；
7. `common_misreads`；
8. `technical_distortions`；
9. `confirm_with`；
10. `cannot_infer`；
11. `source_and_license_note`；
12. `proxy_disclosure`。

Frontend modal 由 metadata render，唔好 hard-code 同一段文字畀全部 unavailable metrics。

---

## 10. 建議 repository 改動

實際路徑以現有 repo 為準；以下只係責任分層建議：

```text
config/
  alerts.yml
  companies.yml
  metric_registry.yml
  us_tax_dates.yml
data/
  manual/
    industry_signals.csv
    options_metrics.csv
    valuation_metrics.csv
  series/
  snapshot.json
scripts/
  collectors/
    nyfed_operations.py
    fred_series.py
    treasury_auctions.py
    finra_margin.py
    cftc_tff.py
    cboe_indices.py
    crypto_funding.py
    sec_companyfacts.py
    sec_form4.py
    ssga_holdings.py
  transforms/
    spreads.py
    technical_calendar.py
    rolling_metrics.py
    correlations.py
    capex.py
    switches.py
  build_snapshot.py
tests/
  fixtures/
  test_spreads.py
  test_h41.py
  test_srf.py
  test_calendar.py
  test_finra.py
  test_cftc.py
  test_form4.py
  test_capex.py
  test_snapshot_contract.py
```

設計原則：collector 只負責取得及 normalize；金融計算放 transforms；粵文敘述由結構化 evidence 生成；frontend 唔重新計核心數字。

---

## 11. GitHub Actions 排程

GitHub cron 用 UTC，亦可能延遲；collector 必須依 source as-of 判斷，而唔係假設 job 開始時間就代表數據已發布。

建議拆開：

### Daily business-day job

- NY Fed rates、ON RRP、SRF；
- Daily TGA；
- Treasury settlement calendar；
- VIX/VIX3M/SKEW；
- crypto funding；
- cross-asset prices；
- Form 4 incremental index；
- build snapshot。

### Thursday-after-H.4.1 job

- 星期四 4:30 p.m. ET 之後跑；
- WRESBAL、WALCL、WTREGEN；
- 如尚未發布，標 `NOT_RELEASED_YET`，唔報 pipeline error。

### Weekly job

- CFTC COT/TFF；
- source schema contract tests；
- 8–12 week signals。

### Monthly job

- FINRA margin debt；
- M2/Nasdaq；
- Buffett proxy（即使季度更新，都可月度檢查 release）；
- holdings concentration backfill／validation。

### Quarterly job

- SEC Company Facts、10-Q/10-K；
- CapEx quarterization；
- manual-review issue generation。

每個 workflow：

1. fetch 到 temp/cache；
2. schema validate；
3. unit normalize；
4. calculate；
5. build snapshot；
6. run tests；
7. 只有全部通過先 commit generated data；
8. fetch 失敗時保留 last-good snapshot，生成 health metadata。

避免 workflow 自己觸發自己形成 commit loop。使用 concurrency group 防止兩個 job 同時寫 snapshot。

---

## 12. 粵文每日解釋 engine

每日解釋唔可以只重述數字。每個重要變化輸出五層：

```json
{
  "observation": "SOFR−IORB 由 -2 bp 升至 +1 bp。",
  "meaning": "Repo 現金成本相對 IORB 變貴。",
  "alternative": "今日同時係大型 Treasury settlement，可能有技術性需求。",
  "confirmation": "EFFR−IORB 無上移，SRF 仍為零。",
  "judgment": "暫時屬 WATCH，未足以證明廣泛準備金短缺。"
}
```

要求：

- 只根據已計算 evidence templates 生成；
- 缺資料時直講缺資料；
- proxy 必須在句中標明；
- 將「水平」、「變化速度」同「二階變化」分清楚；
- technical event 只改 confidence；
- 不提供買賣指令。

---

## 13. 測試及驗收

### 13.1 Unit tests

必須覆蓋：

- 百分點轉 bp；
- IORB backward as-of join；
- 1obs／5obs change；
- positive streak、+3 bp threshold；
- H.4.1 1w／4w；
- 同日多次 SRF aggregate；
- SRF exercise exclusion；
- month/quarter/year end；
- Treasury settlement daily sum；
- tax-date observed shift；
- VIX/VIX3M ratio；
- CFTC net percent OI；
- correlation 使用 returns／yield changes；
- FINRA Excel column mapping；
- M2/Nasdaq month-end alignment；
- Form 4 P/S classification；
- SEC CapEx YTD quarterization；
- Q4 annual deduction；
- QoQ／YoY acceleration；
- `null` 永不變 `0`；
- stale input 唔可以被 switch 當 neutral。

### 13.2 Fixture／contract tests

每個外部來源保存最少一份小型 fixture，測：

- expected columns／JSON keys；
- date parsing；
- units；
- duplicate observations；
- source schema drift；
- HTML error page 唔會被當 CSV／JSON；
- empty successful HTTP response 會 fail closed。

### 13.3 Frontend tests

- 11 個現有 active metric 仍正常；
- ON RRP／SRF active 後唔再出現在 unavailable list；
- weekly metric 顯示 `1W`，唔係 `1D`；
- metric 切換後 chart title、ARIA label、alt text 同步；
- 8W／12W range 可用；
- proxy badge 明顯；
- unavailable card 顯示原因，不顯示 0；
- stale badge、as-of、last-good time 正確；
- mobile layout 唔橫向溢出；
- keyboard 可開關 modal；
- Bloomberg editorial單一主題嘅圖表、badge、focus同文字對比可讀。

### 13.4 Scenario tests

1. SOFR−IORB 單日 +4 bp，但 quarter-end、EFFR 無變、SRF 回零：`WATCH / lower confidence`；
2. SOFR−IORB 連續三日正、EFFR 同 TGCR 上移、非技術日 SRF 使用：`ELEVATED/STRESS`；
3. Reserves 4w 跌、TGA 升，但 ON RRP 同幅跌、spreads 穩：唔應過度報警；
4. H.4.1 星期四未發布：`NOT_RELEASED_YET`；
5. CapEx YoY 仍正但 acceleration 負：解釋「仍增長但減速」，唔可以寫成 CapEx 下跌；
6. Gamma flip 無免費數據：保持 null，同時整個 dashboard 仍可 build；
7. 所有 Market Ignition proxy stale：switch 變 unavailable，唔係 neutral。

---

## 14. 分階段 Definition of Done

### P0：核心流動性完整

- [x] ON RRP 自動更新；
- [x] SRF 自動更新、同日 operations aggregate、exercise flag；
- [x] SOFR−IORB 1obs／5obs／streak／+3 bp；
- [x] EFFR／OBFR／TGCR／BGCR−IORB confirmation spreads；
- [x] month/quarter/year end、Treasury settlement、tax window；
- [x] H.4.1 level／1w／4w；
- [x] 2.9／2.8／2.5 只作 reference zone；
- [x] weekly `1D` bug 及 stale chart alt text 修正；
- [x] 專屬 methodology metadata；
- [x] tests/build 通過。

### P1：Market Ignition 免費版可用

- [x] VIX/VIX3M、Cboe SKEW、BTC／ETH funding、trend 同 cross-asset provider interfaces／transforms／fixtures 完成，但 production rights gate 關閉、零 network、value `null`；
- [x] CFTC E-mini S&P 500／Nasdaq-100 Consolidated × Asset Manager／Leveraged Funds 四條 positioning series；
- [x] 8W／12W views；
- [x] 四個 evidence blocks 分開報 direction／confidence；現階段 positioning `1/4`，唔輸出 composite severity；
- [x] 所有 proxy 有 badge 及定義。

### P2：泡沫指標免費層

- [x] FINRA margin debt正式`UNAVAILABLE_FREE`，rights未清前零network；
- [x] SPY Top-10 weight正式`UNAVAILABLE_FREE`，rights未清前零network；
- [x] government-origin nonfinancial equities/GDP proxy取代冒充Buffett indicator嘅命名；
- [x] M2/Nasdaq divergence正式`UNAVAILABLE_FREE`；
- [x] SEC Form 4 P/S transaction-row count proxy、privacy ledger同review audit；
- [x] SPX 0DTE正式`UNAVAILABLE_FREE`，保留provider interface；
- [x] NDX forward P/E正式`UNAVAILABLE_FREE`，唔偽造。

### P3：Fundamental Exit

- [x] 四間 hyperscaler 12+ quarters CapEx；
- [x] QoQ／YoY growth；
- [x] QoQ／YoY acceleration；
- [x] aggregate 先加總再計 growth；
- [x] orders/backlog/prepayments/take-or-pay manual workflow；
- [x] Fundamental Exit固定`EVIDENCE_ONLY`，分block報direction／confidence，無composite severity。

### 全局完成

- [ ] `NOT WIRED` 全部轉成可審核狀態；
- [ ] `null != 0`；
- [ ] source health 正確；
- [ ] 所有自動數據有 as-of／updated-at／source；
- [ ] 所有免費 proxy 不冒充原數據；
- [ ] GitHub Pages 無 server dependency；
- [ ] GitHub Actions 無付費 API／未授權 secret；
- [ ] README 說明本地重跑、更新排程、人工 CSV 及 troubleshooting；
- [ ] CI tests 與 production build 通過。

---

## 15. 官方／免費來源索引

### Federal Reserve／New York Fed

- NY Fed Markets API：<https://markets.newyorkfed.org/static/docs/markets-api.html>
- Repo operations：<https://www.newyorkfed.org/markets/desk-operations/repo>
- Reverse repo operations：<https://www.newyorkfed.org/markets/desk-operations/reverse-repo>
- H.4.1：<https://www.federalreserve.gov/releases/h41/>
- WRESBAL：<https://fred.stlouisfed.org/series/WRESBAL>
- WALCL：<https://fred.stlouisfed.org/series/WALCL>
- WTREGEN：<https://fred.stlouisfed.org/series/WTREGEN>
- RRPONTSYD：<https://fred.stlouisfed.org/series/RRPONTSYD>

### Treasury

- FiscalData API：<https://fiscaldata.treasury.gov/api-documentation/>
- Treasury Securities Auctions：<https://fiscaldata.treasury.gov/datasets/treasury-securities-auctions-data/>
- Upcoming Auctions：<https://fiscaldata.treasury.gov/datasets/upcoming-auctions/>
- IRS Tax Calendar：<https://www.irs.gov/businesses/small-businesses-self-employed/tax-calendar>

### Market structure

- CFTC COT：<https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm>
- CFTC historical files：<https://www.cftc.gov/MarketReports/CommitmentsofTraders/HistoricalCompressed/index.htm>
- Cboe VIX3M：<https://www.cboe.com/us/indices/dashboard/vix3m/>
- Cboe SKEW：<https://www.cboe.com/us/indices/dashboard/skew/>
- Bybit funding API：<https://bybit-exchange.github.io/docs/v5/market/history-fund-rate>
- Coinbase public funding API：<https://docs.cdp.coinbase.com/api-reference/market-data/public-get_funding_rate_history>

### Bubble／fundamentals

- FINRA margin statistics：<https://www.finra.org/rules-guidance/key-topics/margin-accounts/margin-statistics>
- SPY holdings：<https://www.ssga.com/us/en/intermediary/etfs/state-street-spdr-sp-500-etf-trust-spy>
- SEC EDGAR APIs：<https://www.sec.gov/search-filings/edgar-application-programming-interfaces>
- EDGAR access guidance：<https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data>
- NCBEILQ027S：<https://fred.stlouisfed.org/series/NCBEILQ027S>
- M2SL：<https://fred.stlouisfed.org/series/M2SL>
- NASDAQCOM：<https://fred.stlouisfed.org/series/NASDAQCOM>

---

## 16. 最後提醒

呢個 dashboard 目的係將三件事分開：

1. **Liquidity Fuel**：資金市場同 balance-sheet 燃料有冇收緊；
2. **Market Ignition**：市場結構有冇令衝擊容易被放大；
3. **Fundamental Exit**：AI／科技投資嘅真實需求有冇由減速變成廣泛轉弱。

任何單一指標都唔係危機、泡沫爆破或資產方向嘅充分證據。免費版最重要嘅品質標準唔係「每張卡都有數字」，而係：**數值真、定義清、來源可追、缺失坦白、proxy 唔冒充原值。**
