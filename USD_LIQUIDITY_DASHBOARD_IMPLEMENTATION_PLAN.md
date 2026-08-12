# 美元流動性監測儀錶板：詳細 Implementation Plan

## 0. 文件用途

呢份文件係可以直接交畀本地 Codex 執行嘅產品及工程規格。目標係建立一個：

- 由 GitHub Pages 托管嘅靜態網站；
- 由 GitHub Actions 定時抓取及整理公開數據；
- 前端只讀取 repo 內生成嘅 JSON，唔直接向第三方 API 發請求；
- 自動計算趨勢、異常、技術性扭曲同粵文解釋；
- 清楚區分官方數據、衍生指標、代理指標、人工輸入及付費數據缺口；
- 唔生成假數據，來源失敗時保留上一個成功版本並顯示 stale/error 狀態。

第一版係日頻／週頻風險監測工具，唔係低延遲交易系統。

---

## 1. 產品目標與非目標

### 1.1 產品目標

1. 每個美國工作日更新 SOFR、IORB、EFFR、OBFR、TGA、ON RRP、SRF 等核心流動性數據。
2. 計算 SOFR−IORB 利差、上一個有效觀察日變化、5 日趨勢同持續異常。
3. 每星期更新 H.4.1：Reserve Balances、Fed Total Assets，以及 1 週／4 週變化。
4. 以 Treasury 發債結算、月尾、季尾及主要稅期標記技術性扭曲，而唔係刪除觀察值。
5. 包含影片討論過嘅市場結構、泡沫、CapEx 二階導數及產業「真實需求」指標。
6. 每個指標顯示來源、as-of date、抓取時間、更新頻率、品質級別及 freshness。
7. 用 deterministic rule engine 產生粵文解釋，唔依賴 LLM API。
8. 將同一份 `snapshot.json` 當成儀錶板同日後 ChatGPT daily job 嘅單一真相來源。

### 1.2 非目標

- 唔做秒級 real-time 行情。
- 唔落盤、唔發交易指令、唔提供自動買賣建議。
- 唔繞過付費牆、登入、授權或供應商 redistribution 限制。
- 唔將 gamma flip、CTA positioning、forward P/E 等非公開數據偽裝成官方數據。
- 第一版唔設 database、登入系統或私人帳戶資料。

---

## 2. 金融背景、判讀框架與指標存在理由

呢一章唔只係畀用戶睇，亦係 rule engine、tooltip、methodology drawer 同每日粵文解釋嘅產品規格。Codex 實作時唔可以只將數字同 chart 放上畫面；每個指標都要回答：

1. 佢實際量度緊乜？
2. 點解理論上同美元流動性、擁擠交易或 AI 資本開支循環有關？
3. 數值上升／下降通常意味乜？
4. 有邊啲常見假陽性或替代解釋？
5. 要同邊啲獨立指標一齊出現，先可以提高結論信心？
6. 呢個指標無論點變，都唔足以單獨證明乜？

### 2.1 儀錶板真正要回答嘅問題

儀錶板唔係嘗試用一個神奇數字預測「泡沫幾時爆」。佢係分三層回答三個條件式問題：

#### Switch A：流動性燃料（Liquidity Fuel）

> 銀行體系同 Treasury financing market 嘅美元現金，係咪開始由「充裕而便宜」變成「較稀缺而昂貴」？

核心觀察：

- 價格：SOFR−IORB、EFFR−IORB、OBFR−IORB、TGCR/BGCR−IORB；
- 數量：Reserve Balances、Fed assets、TGA、ON RRP；
- backstop：SRF usage；
- 預期流量：Treasury settlement、稅期、Fed 資產變化。

#### Switch B：市場引信（Market Ignition）

> 如果出現流動性或宏觀衝擊，市場倉位、衍生品 hedging 同槓桿結構會吸收衝擊，定係放大衝擊？

核心觀察：

- VIX term structure、put skew；
- dealer gamma／gamma flip；
- 0DTE 活動；
- crypto perpetual funding；
- CTA/leveraged-fund proxy；
- price-position divergence、cross-asset correlation。

#### Switch C：基本面逃生門（Fundamental Exit）

> 即使估值昂貴，AI／雲端投資是否仍有真實訂單、合約同現金支出支持；抑或投資增長開始失速？

核心觀察：

- hyperscaler CapEx level、growth、acceleration；
- upstream orders、backlog、prepayments、take-or-pay；
- forward valuation、concentration、margin leverage 等慢速脆弱度背景。

三個 switch 係互補而非替代：流動性收緊唔必然令股市即跌；市場結構脆弱唔代表一定有衝擊；CapEx 減速亦唔等於整個 AI thesis 失敗。高信心警報應要求至少兩層互相確認。

### 2.2 美國 ample-reserves 制度：點解要同時睇「數量」同「價格」

2008 年後，美國由 scarce-reserves regime 轉向 ample-reserves regime。Fed 唔再主要靠每日微調準備金數量控制利率，而係用 administered rates 將隔夜市場利率錨定喺政策區間：

- **IORB**：Fed 支付畀合資格銀行準備金嘅利率，係銀行持有現金喺 Fed 嘅機會收益基準；
- **ON RRP offering rate**：為有資格但未必可以收 IORB 嘅 money-market counterparties 提供地板工具；
- **SRF rate**：以 Treasury/agency collateral 提供隔夜現金嘅 backstop，協助限制 repo 壓力向 EFFR 傳導。

因此「準備金有幾多」同「市場資金幾貴」要一齊睇：

- Reserve Balances 係 aggregate stock，但準備金分布、銀行內部最低需求、監管要求同支付需要都會變；
- Money-market spreads 係市場價格訊號，可以反映邊際現金或 dealer balance-sheet capacity；
- 單睇數量會忽略分布同需求，單睇價格又會受月尾、collateral、發債結算等技術因素影響。

官方背景：

- Fed ample-reserves basics：https://www.federalreserve.gov/econres/notes/feds-notes/implementing-monetary-policy-in-an-ample-reserves-regime-the-basics-note-1-of-3-20200701.html
- Fed market-based reserve indicators：https://www.federalreserve.gov/econres/notes/feds-notes/market-based-indicators-on-the-road-to-ample-reserves-20250131.html
- NY Fed reference-rate definitions：https://www.newyorkfed.org/markets/reference-rates

### 2.3 Fed balance-sheet 傳導鏈

Fed balance sheet 嘅簡化關係係：

```text
Fed assets
  = bank reserve balances
  + TGA
  + ON RRP and other reverse repos
  + currency
  + other liabilities and capital
```

所以喺其他項目不變下：

```text
TGA 上升                    → reserve balances 傾向下降
TGA 下降                    → reserve balances 傾向上升
ON RRP 下降                 → 可以吸收部分 balance-sheet runoff / TGA 上升
Fed assets 因 runoff 而下降 → 最終會壓低某類 Fed liabilities
Fed repo/SRF lending 上升   → 暫時增加市場可用現金／Fed assets
```

必須寫「其他項目不變下」，因為同一日 TGA、ON RRP、currency、Fed assets 同其他負債可以同時變動。唔可以將 `Fed assets − TGA − ON RRP` 當作完整、機械式、可以直接預測股票嘅「net liquidity」真理。

### 2.4 核心流動性指標：意義、理由同限制

| 指標 | 實際量度 | 點解要睇 | 上升／惡化通常意味 | 常見誤判 | 應同時確認 |
|---|---|---|---|---|---|
| SOFR | 以 Treasury 作抵押嘅廣泛隔夜現金融資成本 | 反映 repo 現金供求同 dealer/intermediation 條件 | 相對 IORB 持續上升表示 repo cash 變貴 | quarter-end、Treasury settlement、collateral specials、dealer balance-sheet window dressing | TGCR/BGCR、EFFR−IORB、SRF、settlement calendar |
| IORB | Fed 付畀銀行準備金嘅 administered rate | 提供銀行無信用風險 reserve return benchmark | 本身改變多數係政策設定改變，唔係市場壓力 | 將政策減息造成 spread 變化誤當 liquidity shock | 使用同日 rate regime，分開標記 FOMC reset |
| SOFR−IORB | Repo cash cost 相對銀行準備金收益 | 將 SOFR 由政策利率水平中抽離，較容易睇邊際 repo 壓力 | 持續轉正／升高表示 repo financing 相對 IORB 偏貴 | SOFR 包含非銀行同 secured-market segmentation；唔係「準備金稀缺」純指標 | EFFR−IORB、TGCR/BGCR−IORB、reserves、SRF |
| EFFR−IORB | 聯邦基金無抵押隔夜交易相對 IORB | 同 reserve-market arbitrage 及 Fed rate control 更直接相關 | 由長期穩定負 spread 向上移，較符合由 abundant 向 ample 過渡 | EFFR 市場成交參與者同量有限；一兩 bp 可受組成影響 | EFFR percentiles/volume、SOFR、reserve elasticity |
| OBFR−IORB | 較廣泛銀行無抵押隔夜 funding 相對 IORB | 補充 EFFR，只睇 fed funds 可能太窄 | 同 EFFR 一齊向上，代表銀行 funding 壓力較廣泛 | Eurodollar/selected-deposit 組成轉變 | EFFR、SOFR、交易量／percentiles |
| Reserve Balances | 銀行喺 Federal Reserve 嘅 aggregate balances | 係支付、結算、流動性管理同政策實施嘅基礎 stock | 快速下降會減少 aggregate cushion | 絕對門檻會隨名義經濟、銀行資產及需求改變；aggregate 足夠不代表分布均勻 | spreads、SFOS、payment timing、SRF |
| TGA | 美國財政部喺 Fed 嘅現金戶口 | 稅收同發債結算將現金轉入 TGA，其他不變會抽走 reserves | TGA 快速上升通常係短期 reserve drain | Treasury 支出、ON RRP 同其他負債可能抵消；TGA 上升唔等於股市必跌 | reserves、ON RRP、auction/settlement、tax dates |
| ON RRP balance | 合資格 counterparties 將現金放喺 Fed 隔夜嘅使用量 | 高 balance 代表大量現金停泊喺 Fed；下降曾經為 runoff/TGA 提供 liability-side cushion | 當 ON RRP 已接近低位，未來再下降可抵消 reserve drain 嘅空間較少 | 下降亦可能只係 bills/repo 回報更吸引，唔一定係 risk-on liquidity injection | TGA、reserves、money-fund assets、bill supply |
| SRF usage | Counterparties 以合資格 collateral 向 Fed 借隔夜現金 | Backstop 真正被使用，表示 private repo rate 已有足夠誘因轉向設施 | 非技術日持續使用，並伴隨 spreads 上升，係較強壓力確認 | Fed 設計 SRF 就係希望市場喺合適時使用；quarter-end 單日 usage 唔等於危機 | SOFR/TGCR、EFFR、日期 context、usage persistence |
| Fed Total Assets | Fed balance-sheet asset side | 中期決定可由邊類 liabilities 承受資產增減 | Runoff 係持續 reserve drain 候選來源；repo/purchases 可增加 reserves | Asset composition、currency/TGA/ON RRP 會改變 reserve pass-through | H.4.1 liability decomposition |
| Treasury settlement / tax dates | 預先可知嘅現金流事件 | 解釋點解某日 TGA 上升、reserves 或 repo rate 受壓 | 大額 settlement/tax flow 可能造成短暫 spike | 將可逆技術日當成 structural shortage | 技術日後 2–3 日 persistence |

重要結論：

- `SOFR−IORB > 0` 係有資訊嘅 watch signal，但唔係充分條件；
- `EFFR−IORB` 持續向上、repo spreads 廣泛上升、SRF 使用同 reserves 下降一齊出現，先係較可信嘅收緊組合；
- `+3 bp` 係用戶指定、可操作嘅 early-warning threshold，唔係跨時期不變嘅自然定律；必須同 rolling percentile、政策 regime 同歷史分布一齊顯示；
- Reserve Balances 2.9T、2.8T、2.5T 只係 reference zones，唔係自動危機線。

Fed 亦明確指出 tax dates 同 Treasury settlement 可能令 TGA 上升並令 reserves 下降，而 repo rate、EFFR 相對 IORB 向上係 reserve conditions 變化嘅市場確認。因此 rule engine 必須同時使用 flow、stock 同 price，而唔係單指標決策。

### 2.5 點解月尾／季尾唔可以直接刪除

Dealer 同銀行會喺 reporting dates 調整 balance sheet，令 repo intermediation capacity 下降，SOFR 喺 quarter-end 往往較高。呢類 spike 可以係技術性，但佢亦揭示系統面對同樣 cash demand 時有幾多緩衝。

因此正確處理係：

- 保留原始觀察；
- 加 `technical_flag`；
- 降低單日 alert confidence；
- 觀察技術日後 2–3 個有效日有冇回復；
- 如果 EFFR、SRF、reserve quantity 同時惡化，唔可因為「季尾」而完全 suppress。

NY Fed 背景：https://tellerwindow.newyorkfed.org/2025/01/16/monitoring-money-market-dynamics-around-year-end/

### 2.6 市場結構指標：佢哋量度「放大器」，唔係美元存量

| 指標 | 點解有用 | 危險方向可能意味 | 最大限制／guardrail |
|---|---|---|---|
| VIX term structure | 比較短期同較長期 implied volatility，辨識急性事件風險 | 短端高過長端、曲線倒掛通常代表即期 hedging demand 急升 | 只反映 options-implied volatility，唔指明股價方向；已知事件可造成暫時倒掛 |
| Put/call skew | 比較 downside puts 相對其他 strikes 嘅隱含波動率，反映 tail protection 價格 | Put skew 變陡可代表 crash protection demand 增加 | 結構性 hedging mandate、供求同 vol level 都會影響；普通 put/call volume ratio 唔等於 skew |
| Gamma flip | 估計 dealer aggregate gamma 由正轉負嘅 spot level | 負 gamma regime 下 dealer hedging 可能順勢放大 intraday move | Dealer net position 唔公開；只用 open interest 無法可靠判斷買賣方向，結果高度 model/vendor dependent |
| SPX 0DTE share | 反映即日到期 options 喺 SPX 活動中嘅重要性 | 高 share 代表更多極短期 convexity 同 intraday hedging channel | **高 gross volume 不等於高 net risk**；Cboe 研究亦指出買賣平衡時淨 gamma 可以很低，所以必須配合 net gamma |
| Crypto funding | Perpetual swap 多空之間支付嘅 funding，反映槓桿方向及擁擠度 | 極端正 funding 通常係 leveraged longs 擁擠；極端負值則相反 | Exchange-specific、crypto-specific，唔係美元銀行 liquidity 官方指標 |
| CTA proxy | CFTC leveraged-funds/asset-manager futures positioning 嘅公開 proxy | 倉位極端或快速反轉可能預示 systematic deleveraging | COT 每週、滯後、分類粗糙；CFTC 唔知道每一倉位動機，唔可以命名成真實 CTA exposure |
| Price/position consolidation | 比較價格仍高企但倉位、momentum 或 breadth 是否停止擴張 | 價格橫行而 crowded positioning 未清理，可能保留脆弱度；價格穩定兼倉位下降則可能係健康消化 | 係綜合 proxy，定義必須固定並顯示 constituent inputs |
| Cross-asset correlation | 壓力時多種風險資產可能因共同 deleveraging 而一齊郁 | 股、信用、crypto 等 correlation 急升可反映 single risk factor 主導 | Correlation 對窗口敏感，亦可能由共同宏觀消息造成；唔代表因果 |

8–12 週窗口用作將每日 noise 同中期 regime 分開，唔係聲稱市場一定喺 8–12 週內轉向。前端要同時顯示短期（日／週）同 8–12 週趨勢，並標示 window choice。

官方 guardrails：

- Cboe VIX term structure：https://www.cboe.com/tradable-products/vix/term-structure
- Cboe 0DTE「high volume ≠ high risk」分析：https://www.cboe.com/insights/posts/volatility-insights-evaluating-the-market-impact-of-spx-0-dte-options
- CFTC COT classification limitations：https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm

### 2.7 泡沫／脆弱度指標：適合判斷脆弱度，唔適合單獨擇時

| 指標 | 理論用途 | 正確判讀 | 主要限制 |
|---|---|---|---|
| FINRA margin debt | 量度證券 margin accounts 客戶 debit balances，捕捉槓桿參與 | 絕對額、YoY growth、相對 market cap 同歷史 percentile 一齊睇；高而加速代表 forced-selling capacity 增加 | 月頻而滯後；會隨市場規模同名義價格自然增長；唔涵蓋所有衍生品／prime brokerage leverage |
| SPX 0DTE share | 反映極短期 options channel 嘅市場重要性 | 當作市場結構／放大器背景，唔直接當作泡沫水平 | Gross volume 唔等於 dealer net exposure；產品普及本身可推高 share |
| S&P 500 top-10 weight | 量度指數回報同估值集中喺少數公司嘅程度 | 高集中度令一小撮公司業績／估值變化對指數影響更大 | 高集中度可以由盈利同 free-float market cap 合理造成；唔代表 imminent crash |
| Buffett indicator proxy | 公開上市股票總市值相對 GDP，作 aggregate valuation scale | 用長期 percentile 同利率 regime 判讀，唔用單一固定倍數 | 美國上市公司海外收入、私營／上市結構、利率、會計同 GDP 頻率都會改變比率 |
| M2 vs Nasdaq | 檢查貨幣總量增長同科技股價格是否大幅脫節 | 只作 exploratory liquidity narrative；顯示 YoY growth gap、lead/lag sensitivity | M2 唔會機械流入股票，因果同 lag 不穩定；應列為低權重 heuristic |
| Insider buy/sell proxy | 公司內部人 open-market 買賣可能包含對估值／前景嘅私人訊息 | 只計明確 open-market P/S code，分 count-based 同 dollar-based ratio，並睇廣度 | 10b5-1、稅務、分散風險、薪酬股權令 insider sales 常態化；aggregate ratio 唔係精確 timing tool |
| NDX forward P/E | 價格相對未來盈利預期嘅估值 | 同 real yields、earnings revisions、growth expectations 同歷史 percentile 一齊睇 | Consensus forecast 可快速修訂；高增長公司合理 P/E 可以較高；付費數據定義會不同 |

FINRA 官方只係每月發布 aggregate margin balances，而且明確指出 reporting-method changes 亦可能影響月度變化。因此 margin debt 必須係慢速脆弱度背景，唔可成為每日 alarm trigger。

來源：

- FINRA Margin Statistics：https://www.finra.org/rules-guidance/key-topics/margin-accounts/margin-statistics
- S&P 500 constituents/weights：https://www.spglobal.com/spdji/en/indices/equity/sp-500/
- SEC Form 4 data/API：https://www.sec.gov/search-filings/edgar-application-programming-interfaces

### 2.8 點解要睇 CapEx 二階導數同產業真實需求

估值同股價講緊市場願意相信乜；CapEx、orders 同 contractual commitments 則較接近企業實際花錢同客戶承諾。

#### CapEx level

回答：「公司實際投放幾多現金落 property、equipment、data centers、servers 同 network？」

限制：公司披露嘅總 CapEx 未必全部屬於 AI；cash CapEx、finance leases 同供應商融資定義亦可不同。

#### CapEx growth（一階變化）

回答：「投資額仍然增長，定開始收縮？」

#### CapEx acceleration（二階變化）

回答：「CapEx 增長速度係加快定放慢？」

例子：

```text
上季 CapEx YoY growth = +50%
今季 CapEx YoY growth = +30%
acceleration           = -20 percentage points
```

呢個情況係「仍增長，但增速放慢」，唔係 CapEx 跌 20%，亦唔係投資已經收縮。二階導數有用，因為市場往往先對增長速度轉折重新定價；但佢亦較 noisy，所以應要求連續兩季或者同 orders/backlog 一齊確認。

#### Orders / backlog / prepayments / take-or-pay

- **Orders**：客戶新增採購意向；要分 firm order、booking 同 forecast。
- **Backlog**：已簽但未確認收入嘅工作量；要睇 cancellability、交付期同 backlog conversion。
- **Prepayments/customer advances**：客戶已先付現金，承諾通常強過口頭需求；但會計分類不統一。
- **Take-or-pay**：客戶承諾不論實際使用量都支付最低金額，理論上係更強嘅需求支持；但仍有 counterparty credit、重談同 termination clause 風險。

最可信嘅基本面轉弱組合係：CapEx acceleration 連續轉負、upstream orders/backlog growth 同時下降、prepayments／contract commitments 減弱。單一公司一季 CapEx timing 唔足以判斷整個 AI cycle。

### 2.9 指標層級：Primary、Driver、Guardrail

為免將所有數字平均成一個冇意義嘅「大雜燴分數」，指標要分角色：

#### Primary state metrics

1. **Funding pressure**：SOFR−IORB，但必須由 EFFR−IORB／TGCR−IORB 等確認；
2. **Reserve cushion**：Reserve Balances 水平與 1w/4w 變化；
3. **Backstop dependence**：非技術性、持續 SRF usage。

#### Driver metrics

- TGA、ON RRP、Fed assets；
- Treasury settlement、tax dates；
- market positioning、volatility structure；
- CapEx growth/acceleration。

#### Guardrails / alternative explanations

- month/quarter/year end；
- FOMC policy-rate reset；
- data stale/revision；
- known options expiry/earnings/macro events；
- public proxy、manual data、vendor-model uncertainty。

### 2.10 五個標準判讀例子

1. **SOFR−IORB 單日 +4 bp，但係 quarter-end；EFFR−IORB 無變、SRF 下一日回零**  
   判讀：技術性 repo 壓力，保留 watch，但 confidence 低；唔判定 structural shortage。

2. **Reserves 4w 下跌、TGA 上升，但 ON RRP 同幅下降；money-market spreads 穩定**  
   判讀：liability composition 暫時吸收咗 drain；reserve cushion 下降，但市場價格未確認壓力。

3. **SOFR−IORB 連續三日轉正、EFFR−IORB 上移、SRF 非月尾持續使用**  
   判讀：較可信嘅廣泛 funding tightening；提高 liquidity switch severity。

4. **VIX 曲線倒掛、gamma estimate 轉負，但 reserves/spreads 正常**  
   判讀：市場事件／衍生品放大風險上升，但唔叫美元流動性危機。

5. **Aggregate CapEx acceleration 轉負一季，但 backlog 仍增長、prepayments 穩定**  
   判讀：可能係投資增速正常化或 timing；等待第二季同 upstream confirmation，唔直接宣告 AI bust。

### 2.11 每個 metric 必須具備嘅知識 metadata

`metrics.yml` 除咗技術欄位，必須加入：

```yaml
sofr_iorb_spread:
  role: primary
  layer: liquidity_fuel
  question_answered: "Treasury repo 現金融資相對 IORB 是否變得昂貴？"
  measures: "SOFR minus IORB, in basis points"
  transmission_channel: "repo cash demand, dealer intermediation, reserve and balance-sheet conditions"
  why_track: "將 repo rate 從政策利率水平抽離，監測邊際 funding pressure"
  interpretation_up: "融資壓力可能增加，但需要持續性及其他 markets 確認"
  interpretation_down: "repo cash 相對充裕或技術性壓力消退"
  false_positives:
    - quarter-end balance-sheet reporting
    - large Treasury settlement
    - collateral-specific effects
  confirm_with:
    - effr_iorb_spread
    - tgcr_iorb_spread
    - srf_usage
    - reserve_balances
  cannot_conclude: "唔可以單獨證明銀行準備金短缺、金融危機或股市即將下跌"
  evidence_grade: high
```

前端 tooltip、methodology drawer 同 explanation engine 必須由呢啲 metadata 生成或引用，避免 UI 文案同分析邏輯日後分叉。

---

## 3. 建議技術棧

雖然部署結果係純靜態 HTML/CSS/JS，但資料密集型儀錶板建議用：

- Frontend：React + TypeScript + Vite
- Charts：Apache ECharts
- Styling：原生 CSS variables + CSS modules，或者一個集中 `styles.css`；唔需要大型 UI framework
- Data pipeline：Python 3.12
- Python packages：`httpx`、`pandas`、`pydantic`、`PyYAML`、`tenacity`、`python-dateutil`
- Tests：`pytest`、`vitest`、React Testing Library
- Hosting：GitHub Pages，以 GitHub Actions artifact 部署
- Storage：repo 內 `public/data/*.json`

React/Vite 最終仍然輸出靜態 `dist/index.html`，唔需要伺服器。前端所有 fetch 必須以 `import.meta.env.BASE_URL` 建立相對路徑，避免 GitHub Pages repo 子目錄部署出錯。

---

## 4. 系統架構

```text
Official APIs / public filings / configured manual data
                         │
                         ▼
              Python source collectors
                         │
                         ▼
       normalize → validate → retain last-good data
                         │
                         ▼
      derived metrics → event flags → alert rules
                         │
                         ▼
 public/data/manifest.json + snapshot.json + series/*.json
                         │
                         ▼
              Vite static production build
                         │
                         ▼
                    GitHub Pages
```

核心原則：

- Collector 只負責取得及標準化來源數據。
- Calculator 只處理數學計算。
- Rule engine 只處理狀態、警報同文字解釋。
- Frontend 唔重新計算金融邏輯，只負責顯示已驗證結果。
- 每個輸出都要有 provenance，唔可以只得一個冇來源嘅數字。

---

## 5. Repository 結構

```text
usd-liquidity-dashboard/
├── README.md
├── LICENSE
├── package.json
├── package-lock.json
├── tsconfig.json
├── vite.config.ts
├── index.html
├── src/
│   ├── App.tsx
│   ├── main.tsx
│   ├── types.ts
│   ├── styles/
│   │   ├── tokens.css
│   │   ├── global.css
│   │   └── dashboard.css
│   ├── data/
│   │   ├── client.ts
│   │   └── guards.ts
│   ├── lib/
│   │   ├── format.ts
│   │   ├── dates.ts
│   │   └── chartOptions.ts
│   ├── components/
│   │   ├── AppHeader.tsx
│   │   ├── SystemStatus.tsx
│   │   ├── SwitchSummary.tsx
│   │   ├── MetricHero.tsx
│   │   ├── MetricTable.tsx
│   │   ├── MetricChart.tsx
│   │   ├── AlertFeed.tsx
│   │   ├── ExplanationPanel.tsx
│   │   ├── TechnicalEvents.tsx
│   │   ├── DataQualityBadge.tsx
│   │   └── SourceDrawer.tsx
│   └── features/
│       ├── liquidity/
│       ├── market-structure/
│       ├── bubble/
│       ├── capex/
│       └── industry-signals/
├── public/
│   └── data/
│       ├── manifest.json
│       ├── snapshot.json
│       ├── events.json
│       ├── alerts.json
│       ├── series/
│       │   ├── sofr.json
│       │   ├── iorb.json
│       │   ├── sofr_iorb_spread.json
│       │   └── ...
│       └── manual/
│           └── README.json
├── pipeline/
│   ├── update.py
│   ├── backfill.py
│   ├── models.py
│   ├── io.py
│   ├── logging_config.py
│   ├── collectors/
│   │   ├── base.py
│   │   ├── nyfed.py
│   │   ├── fred.py
│   │   ├── fiscaldata.py
│   │   ├── federal_reserve.py
│   │   ├── treasury_auctions.py
│   │   ├── cboe.py
│   │   ├── cftc.py
│   │   ├── finra.py
│   │   ├── sec_edgar.py
│   │   ├── crypto.py
│   │   └── manual.py
│   ├── transforms/
│   │   ├── spreads.py
│   │   ├── trends.py
│   │   ├── correlations.py
│   │   ├── capex.py
│   │   └── percentiles.py
│   ├── rules/
│   │   ├── engine.py
│   │   ├── liquidity.py
│   │   ├── market_structure.py
│   │   ├── bubble.py
│   │   ├── explanations_zh_hk.py
│   │   └── technical_events.py
│   ├── config/
│   │   ├── metrics.yml
│   │   ├── thresholds.yml
│   │   ├── sources.yml
│   │   ├── companies.yml
│   │   └── known_events.yml
│   └── tests/
│       ├── fixtures/
│       ├── test_collectors.py
│       ├── test_spreads.py
│       ├── test_trends.py
│       ├── test_capex.py
│       ├── test_rules.py
│       └── test_schema.py
└── .github/
    └── workflows/
        ├── update-and-deploy.yml
        └── pull-request-checks.yml
```

---

## 6. 統一資料模型

### 6.1 `series/<metric_id>.json`

每個指標一個檔案，方便 lazy loading，亦避免每次前端載入全部歷史。

```json
{
  "schema_version": "1.0.0",
  "metric_id": "sofr_iorb_spread",
  "label": "SOFR−IORB 利差",
  "description": "SOFR 減 IORB，以基點表示。",
  "unit": "bp",
  "frequency": "business_daily",
  "quality": "derived_official",
  "status": "ok",
  "as_of": "2026-08-10",
  "retrieved_at": "2026-08-11T22:15:20Z",
  "expected_next_update": "2026-08-12",
  "source_ids": ["nyfed_sofr", "fred_iorb"],
  "methodology": "(SOFR_pct - IORB_pct) * 100",
  "knowledge": {
    "role": "primary",
    "layer": "liquidity_fuel",
    "question_answered": "Treasury repo 現金融資相對 IORB 是否變得昂貴？",
    "why_track": "監測邊際 secured-funding pressure。",
    "interpretation_up": "壓力可能增加，但需要持續性及其他市場確認。",
    "cannot_conclude": "唔可以單獨證明準備金短缺、金融危機或股市即將下跌。"
  },
  "observations": [
    {"date": "2026-08-07", "value": -2.0},
    {"date": "2026-08-10", "value": 1.0}
  ]
}
```

### 6.2 `snapshot.json`

首頁只載入呢個檔案。佢包含最新值、變化、狀態、解釋同短期 series；完整歷史先按需要載入。

```json
{
  "schema_version": "1.0.0",
  "generated_at": "2026-08-11T22:16:03Z",
  "market_date": "2026-08-10",
  "overall_status": "neutral",
  "switches": {
    "liquidity_fuel": {"status": "neutral", "score": 1, "confidence": "high"},
    "market_ignition": {"status": "watch", "score": 2, "confidence": "medium"},
    "fundamental_exit": {"status": "neutral", "score": 1, "confidence": "low"}
  },
  "metrics": {
    "sofr_iorb_spread": {
      "value": 1.0,
      "unit": "bp",
      "as_of": "2026-08-10",
      "previous": -2.0,
      "delta_1d": 3.0,
      "change_5d": 2.0,
      "trend_5d": "rising",
      "consecutive_positive": 1,
      "quality": "derived_official",
      "status": "ok",
      "flags": ["positive_spread"],
      "short_series": []
    }
  },
  "technical_context": [],
  "alerts": [],
  "explanations": {
    "headline": "美元資金面整體中性，但短期融資利差有所上升。",
    "bullets": []
  },
  "source_health": {
    "ok": 8,
    "stale": 1,
    "error": 0,
    "missing": 3
  }
}
```

### 6.3 Quality enum

只准使用以下值：

- `official`：來源直接發布值。
- `derived_official`：只由官方數據以公開公式計算。
- `public_vendor`：交易所／資產管理公司等公開但非政府來源。
- `proxy`：用公開數據估算一個非公開概念。
- `manual`：人工輸入並附來源與日期。
- `paid_required`：定義咗指標，但冇合法免費數據。

### 6.4 Status enum

- `ok`
- `stale`
- `missing`
- `error`
- `not_released`
- `manual_update_due`
- `paid_data_unavailable`

`0` 係真實數值；缺失必須用 `null`，唔准將 missing 寫成零。

### 6.5 `manifest.json`

Pipeline 要將 `metrics.yml` 編譯成前端可讀嘅 catalog。每個項目最少包括：

- metric ID、label、unit、frequency；
- layer 同 role（primary/driver/guardrail）；
- source IDs、quality、availability；
- question answered、why track、up/down interpretation；
- false positives、confirm-with、cannot-conclude；
- methodology、source URL、data-license/redistribution note；
- series JSON path。

React tooltip、Sources & Methodology 頁面同每日 explanation engine 必須共享呢份 catalog，唔准各自維護三套互相矛盾嘅文案。

---

## 7. 指標清單、來源及實作優先次序

### 7.1 Tier A：第一版必須全自動完成

| Metric ID | 指標 | 來源 | 頻率 | 計算／備註 |
|---|---|---|---|---|
| `sofr` | SOFR | NY Fed Markets API | 工作日 | 官方值 |
| `iorb` | IORB | Federal Reserve/FRED | 利率調整日、7-day series | 對 SOFR 日期做 backward as-of join，唔插值 |
| `sofr_iorb_spread` | SOFR−IORB | 衍生 | 工作日 | `(SOFR−IORB)×100` bp |
| `effr` | EFFR | NY Fed Markets API | 工作日 | 官方值 |
| `effr_iorb_spread` | EFFR−IORB | 衍生 | 工作日 | Fed reserve-market confirmation spread |
| `obfr` | OBFR | NY Fed Markets API | 工作日 | 官方值 |
| `obfr_iorb_spread` | OBFR−IORB | 衍生 | 工作日 | 較廣泛 unsecured bank-funding confirmation |
| `tgcr` | TGCR | NY Fed Markets API | 工作日 | Tri-party Treasury general-collateral repo rate |
| `tgcr_iorb_spread` | TGCR−IORB | 衍生 | 工作日 | 分辨 tri-party repo 同 broader SOFR 壓力 |
| `bgcr` | BGCR | NY Fed Markets API | 工作日 | TGCR 加 GCF repo 嘅 broader GC rate |
| `bgcr_iorb_spread` | BGCR−IORB | 衍生 | 工作日 | 第二個 secured-market confirmation |
| `tga_daily` | TGA closing balance | Treasury FiscalData DTS | 工作日 | 單位由百萬美元轉十億美元 |
| `on_rrp` | ON RRP accepted amount | NY Fed Markets API | 工作日 | 同日 operation aggregate |
| `srf_usage` | Standing Repo Facility usage | NY Fed repo results | 工作日 | 將 morning/afternoon repo operation accepted amounts 合計 |
| `reserve_balances` | Reserve Balances with Federal Reserve Banks | H.4.1 / FRED `WRESBAL` | 每週 | 顯示水平、1w、4w 變化 |
| `fed_total_assets` | Fed Total Assets | H.4.1 / FRED `WALCL` | 每週 | 水平、1w、4w 變化 |
| `tga_weekly_h41` | Treasury General Account weekly | H.4.1 / FRED `WTREGEN` | 每週 | 用作同 daily DTS cross-check |
| `treasury_settlements` | Treasury issue/settlement amount | Treasury Auctions Data | 按需要 | 以 `issue_date` 聚合當日 settlement |

主要端點：

```text
https://markets.newyorkfed.org/api/rates/all/latest.json
https://markets.newyorkfed.org/api/rates/secured/sofr/search.json
https://markets.newyorkfed.org/api/rates/secured/tgcr/search.json
https://markets.newyorkfed.org/api/rates/secured/bgcr/search.json
https://markets.newyorkfed.org/api/rates/unsecured/effr/search.json
https://markets.newyorkfed.org/api/rates/unsecured/obfr/search.json
https://markets.newyorkfed.org/api/rp/reverserepo/propositions/search.json
https://markets.newyorkfed.org/api/rp/repo/all/results/last/20.json
https://fred.stlouisfed.org/graph/fredgraph.csv?id=IORB
https://fred.stlouisfed.org/graph/fredgraph.csv?id=WRESBAL
https://fred.stlouisfed.org/graph/fredgraph.csv?id=WALCL
https://fred.stlouisfed.org/graph/fredgraph.csv?id=WTREGEN
https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/dts/operating_cash_balance
https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/od/auctions_query
```

實作時唔可以假定外部 JSON field 永遠不變。每個 collector 要：

1. 保存 response fixture；
2. 驗證必要欄位；
3. 對數值字串、逗號、`null` 做明確轉換；
4. 對 endpoint 做 smoke test；
5. API schema 改變時報 `source_schema_error`，唔好靜默產生錯數。

### 7.2 Tier B：公開數據，可以自動化，但更新較慢或只係 proxy

| Metric ID | 指標 | 來源 | 頻率 | 品質／做法 |
|---|---|---|---|---|
| `vix_curve` | VIX term structure | Cboe | 日內／日頻 | `public_vendor`；保存 VIX9D/VIX/VIX3M/VIX6M 或官方 term structure snapshot |
| `vix_inversion` | VIX 曲線倒掛 | 衍生 | 日頻 | 短期限值高過長期限值即標記，清楚列出用咗邊兩個 tenor |
| `crypto_funding_btc` | BTC perp funding | Bybit public market API | 每 8 小時／每日 snapshot | `public_vendor`，唔係美元銀行流動性官方數據 |
| `crypto_funding_eth` | ETH perp funding | Bybit public market API | 每 8 小時／每日 snapshot | 同上 |
| `risk_asset_price_regime` | 風險資產價格趨勢／整固 | 可配置合法市場數據來源 | 日頻 | `public_vendor`；SPX/NDX 20d return、drawdown、realized vol、距 20d high |
| `cta_proxy` | CTA/leveraged funds positioning proxy | CFTC TFF/COT | 每週 | `proxy`；以 selected equity index futures net positioning 做 z-score |
| `positioning_consolidation_proxy` | 倉位整固 proxy | CFTC + price regime | 每週 | `proxy`；比較 4w positioning change、price range 同 realized vol，唔可稱為真實 CTA book |
| `cross_asset_corr` | 風險資產相關性 | 可配置市場數據供應商 | 日頻 | 20d/60d rolling correlation；必須標明 price provider |
| `finra_margin_debt` | Customer margin debit | FINRA Excel | 每月 | FINRA 通常下月第三週發布；冇 data feed，下載官方 Excel |
| `m2_vs_nasdaq` | M2 與 Nasdaq divergence | FRED `M2SL`, `NASDAQCOM` | 月／日 | 同基準日 index=100；同比增長差及 z-score |
| `buffett_indicator_proxy` | 美國股票市值/GDP proxy | Fed Z.1/FRED + BEA/FRED GDP | 每季 | `derived_official`，名稱必須帶 proxy，記錄 exact series IDs |
| `insider_ratio_proxy` | Insider buy/sell proxy | SEC Form 4 | 日／週 | `proxy`；只計 open-market `P`/`S` transactions，排除 grants/options/tax withholding |
| `hyperscaler_capex` | Hyperscaler CapEx | SEC Company Facts + filings | 每季 | 逐公司 tag mapping，必要時人工覆核 |
| `capex_acceleration` | CapEx 二階導數 | 衍生 | 每季 | 詳見第 10 節 |

官方／公開來源：

- Cboe VIX term structure：https://www.cboe.com/tradable-products/vix/term-structure
- CFTC COT：https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm
- FINRA Margin Statistics：https://www.finra.org/rules-guidance/key-topics/margin-accounts/margin-statistics
- SEC EDGAR APIs：https://www.sec.gov/search-filings/edgar-application-programming-interfaces

### 7.3 Tier C：畫面及 schema 必須存在，但第一版唔好偽造數值

| Metric ID | 指標 | 第一版狀態 | 升級路徑 |
|---|---|---|---|
| `gamma_flip` | Gamma flip level | `paid_data_unavailable` | 接入 SpotGamma、SqueezeMetrics 或合法 options-chain model |
| `spx_0dte_share` | SPX 0DTE volume share | `manual` 或 `paid_data_unavailable` | Cboe 可下載數據若授權允許，否則接入供應商 |
| `put_call_skew` | Put/call skew | `manual`/`proxy` | 用 Cboe SKEW 或合法 options vendor；唔好將普通 put/call ratio 冒充 skew |
| `sp500_top10_weight` | S&P 500 Top 10 weight | `manual` | 官方 S&P factsheet 或按合法 ETF holdings 近似；兩者不可混稱 |
| `ndx_forward_pe` | Nasdaq-100 forward P/E | `paid_data_unavailable` | FactSet/Bloomberg/LSEG/S&P Capital IQ 等供應商 |
| `upstream_backlog` | AI 上游 backlog/orders | `manual` | 公司 10-Q/10-K/earnings materials，逐公司配置 extraction |
| `prepayments` | Prepayments/customer advances | `manual` | 公司 filings，非標準化 XBRL tag |
| `take_or_pay` | Take-or-pay commitments | `manual` | 合約及 filings text extraction，人工核實 |

Tier C UI 必須顯示「數據未公開／需要供應商」，而唔係顯示空白 chart 或數字零。

### 7.4 人工數據接口

Tier C 唔應寫死喺 React。`pipeline/collectors/manual.py` 讀取一個受版本控制嘅 `pipeline/config/manual_observations.yml`：

```yaml
observations:
  - metric_id: sp500_top10_weight
    as_of: 2026-06-30
    value: 38.2
    unit: percent
    source_url: https://example.com/original-source
    source_title: Official quarterly factsheet
    retrieved_at: 2026-07-05T18:00:00Z
    entered_by: manual
    notes: "Definition: top ten constituents by index weight."
```

Validation：

- `metric_id` 必須已經存在 `metrics.yml`；
- `source_url`、`as_of`、`unit` 必填；
- 新 observation 唔可以早過現有 latest 而覆蓋佢；
- 每個 metric 有 configurable expiry，過期後自動變 `manual_update_due`；
- 人工值同自動值不可混入同一 series 而唔標 quality change；
- 對 PDF/factsheet，只保存來源 URL、頁碼及摘錄方法，唔將整份有版權文件 commit 入 repo。

---

## 8. 更新排程與 GitHub Actions

### 8.1 Schedule

建議同一個 workflow 每個美國工作日跑兩次：

```yaml
on:
  schedule:
    - cron: "15 22 * * 1-5"
    - cron: "45 23 * * 1-5"
  workflow_dispatch:
```

原因：

- 22:15 UTC 全年都遲過紐約時間 H.4.1 星期四 4:30 p.m. 發布；
- 第二次係補抓，應付 Treasury/Fed 延遲或 GitHub 排程延誤；
- pipeline 必須 idempotent，數據冇變就唔 commit。

GitHub scheduled Actions 並非精確計時，唔應該喺 UI 寫「保證於某分鐘更新」。UI 應顯示實際 `generated_at` 同每個來源 `as_of`。

### 8.2 Workflow steps

`update-and-deploy.yml` 應依序：

1. Checkout default branch 完整 history。
2. Setup Python 3.12，同時 cache pip。
3. 安裝 `pipeline/requirements.txt`。
4. 執行 `python -m pipeline.update --mode incremental`。
5. 執行 `pytest pipeline/tests`。
6. 執行 JSON schema validation。
7. Setup Node LTS、`npm ci`。
8. 執行 `npm run test`、`npm run build`。
9. 將生成數據 commit 回 default branch，但只限 `public/data/**`；無變化就跳過 commit。
10. 喺同一個 workflow 直接 upload `dist/` Pages artifact 並 deploy。
11. Upload pipeline log 同 source-health report 做短期 Actions artifact。

將 update、commit 同 Pages deploy 放喺同一個 workflow，避免由 `GITHUB_TOKEN` 推送嘅 commit 未必再觸發另一個 Pages workflow。

最低權限：

```yaml
permissions:
  contents: write
  pages: write
  id-token: write
```

加入：

```yaml
concurrency:
  group: pages
  cancel-in-progress: false
```

### 8.3 Failure policy

- 核心數學或 schema validation 失敗：停止 deploy。
- 單一非核心來源失敗：保留上一版本，將該來源標成 `error` 或 `stale`，其餘數據照常部署。
- 核心來源第一次執行就失敗、冇 last-good data：顯示 `missing`，唔生成 0。
- 星期四 H.4.1 未發布：`not_released`，保留上星期值，唔視為程式錯誤。
- Retry：timeout 20 秒，最多 3 次 exponential backoff；唔准無限 retry。
- SEC requests 必須有識別身份嘅 `User-Agent`，並低於官方 fair-access 上限。

---

## 9. 核心計算規則

### 9.1 Overnight-rate spreads to IORB

```python
spread_bp = round((market_rate_pct - iorb_pct) * 100, 2)
```

- 對 SOFR、EFFR、OBFR、TGCR、BGCR 使用相同單位公式，但保存成獨立 series，唔好平均原始 rates。
- Market rate/IORB 原值以百分比表示，例如 3.67、3.65。
- 每個 spread 嘅 `previous` 係上一個有該 market-rate fixing 嘅有效交易日，唔係上一個 calendar day。
- IORB 用當日或當日前最近一個有效 rate；唔可以做線性插值。
- 保留至少最近 5 年歷史；SOFR 可由可用起始日開始。
- SOFR−IORB 係首頁 early-warning spread；EFFR−IORB 係較直接 reserve-market confirmer；TGCR/BGCR−IORB 用作判斷 repo 壓力係咪跨 segment。
- 每個 rate 同時保存 1st/25th/75th/99th percentiles 及 transaction volume（來源有提供時），避免 median 不變掩蓋 distribution 轉差。

### 9.2 1-day 及 5-day trend

- `delta_1d = latest − previous_valid`
- `change_5d = latest − fifth_previous_valid`
- `trend_5d` 用最近 5 個有效觀察值做 OLS slope：
  - slope 大過 configurable epsilon：`rising`
  - slope 細過負 epsilon：`falling`
  - 其餘：`flat`
- 同時輸出 `positive_days_last_5` 同 `consecutive_positive`，唔好只靠 slope。

### 9.3 H.4.1

```python
change_1w = latest - previous_observation
change_4w = latest - fourth_previous_observation
```

2.9、2.8、2.5 萬億美元只係參考區間：

- UI 畫水平 reference lines；
- 唔可以單憑跌穿某線就判定危機；
- 解釋必須同 SOFR−IORB、TGA、ON RRP、SRF 一齊判斷。

### 9.4 TGA

- 讀取 `account_type == "Treasury General Account (TGA) Closing Balance"`。
- FiscalData 數值以百萬美元發布；內部 normalize 成十億美元。
- DTS table schema 曾出現「Closing Balance」row 嘅數值存放於 `open_today_bal`、而 `close_today_bal` 為空嘅情況。Collector 必須先按最新官方 data dictionary 同 live fixture 確認欄位；可採用 `close_today_bal` 非空時優先，否則讀 closing row 嘅 `open_today_bal`，但一定要用 `opening + deposits − withdrawals = closing` 做 tolerance check。驗證失敗時標成 schema/data error，唔好發布。
- TGA 上升通常係由私人／銀行體系向 Treasury 收款，短期抽走準備金；TGA 下跌通常係 Treasury 支出回流。
- 呢個係方向性解釋，唔等於資產價格必然升跌。

### 9.5 SRF

- 每個日期將 morning 及 afternoon operation accepted amount 合計。
- 保留 collateral breakdown 同 operation count。
- `usage > 0` 係需要留意，但唔自動等於危機。
- 月尾、季尾、年尾 usage 要加 technical flag；如果離開技術日仍持續使用，先提高 severity。

### 9.6 ON RRP

- 顯示水平、1d、5d 變化。
- ON RRP 下跌可以暫時吸收 TGA 上升／QT 對準備金嘅影響；當 ON RRP 已經好低，呢個 cushion 亦較少。
- 唔應將 ON RRP 單獨加入簡化「Fed assets − TGA − RRP」公式後當作完整市場流動性真相。

---

## 10. CapEx 二階導數

### 10.1 公司範圍

初始配置：

- Alphabet (`GOOGL`)
- Microsoft (`MSFT`)
- Amazon (`AMZN`)
- Meta (`META`)
- Oracle (`ORCL`，可列為次級，因 fiscal calendar 不同)

`companies.yml` 要保存 CIK、fiscal year end、首選 XBRL tag、fallback tag、公司自定義 CapEx 定義及人工覆核備註。

### 10.2 SEC extraction

- 優先用 `data.sec.gov/api/xbrl/companyfacts/CIK##########.json`。
- 常見 tag 係 `PaymentsToAcquirePropertyPlantAndEquipment`，但唔可假定所有公司一致。
- 10-Q cash-flow facts 經常係 fiscal-year-to-date；單季值要用本季 YTD 減上季 YTD。
- Q4 通常用全年 10-K 減頭三季 YTD。
- 同一 period 如果有 amended/recast filings，以最新 accepted filing 為準，但保留 accession number。
- 每個公司輸出 `extraction_confidence` 同 filing URL。

### 10.3 計算

同時顯示兩種加速度，避免「二階導數」定義含糊：

```python
qoq_growth_t = capex_t / capex_t_minus_1 - 1
qoq_acceleration_t = qoq_growth_t - qoq_growth_t_minus_1

yoy_growth_t = capex_t / capex_t_minus_4 - 1
yoy_acceleration_t = yoy_growth_t - yoy_growth_t_minus_1
```

Aggregate：

- 先將各公司 dollar CapEx 相加，再計 aggregate growth；
- 唔好直接平均公司百分比，避免細公司權重過大；
- 同時顯示各公司 contribution。

解釋規則：

- acceleration > 0：CapEx 增長加速；
- acceleration < 0 但 growth > 0：CapEx 仍然增長，只係增速放慢；
- growth < 0：CapEx 絕對值收縮；
- 連續兩季 acceleration < 0 先列作較強 slowdown signal。

---

## 11. 技術性扭曲事件

### 11.1 唔刪數據，只加 context

每個 observation 可以有：

```json
{
  "technical_flags": ["month_end", "large_treasury_settlement"],
  "alert_confidence_modifier": -1,
  "note": "月尾 balance-sheet window dressing 可能推高 secured funding rate。"
}
```

### 11.2 自動事件

- `month_end`：每月最後一個有效美國工作日。
- `quarter_end`：3、6、9、12 月最後一個有效工作日。
- `year_end`：12 月最後一個有效工作日。
- `treasury_settlement`：按 Treasury Auctions Data `issue_date` 聚合。
- `large_treasury_settlement`：settlement 金額超過 configurable threshold；threshold 放 `thresholds.yml`，UI 顯示實際金額。
- `major_tax_date`：由 `known_events.yml` 配置個人／企業主要繳稅日及週邊一個工作日。

### 11.3 Alert suppression

「排除扭曲」唔代表完全 suppress：

- 技術日單日 spike：保留 alert，但降一級並標記 low/medium confidence。
- 同一信號喺技術日後兩個有效日仍持續：恢復正常 severity。
- SOFR−IORB、SRF 同 reserves 同時惡化：即使係季尾亦唔可以完全消除警報。

---

## 12. Alert engine 與每日解釋

### 12.1 Alert levels

- `normal`
- `info`
- `watch`
- `warning`
- `critical`

### 12.2 初始 SOFR−IORB 規則

所有數值放入 `thresholds.yml`，唔要散落 code：

- Spread 單日轉正：`info`
- 連續 3 個有效日轉正：`watch`
- Spread > +3 bp：至少 `watch`
- Spread > +3 bp 且連續 2 日、並非純技術扭曲：`warning`
- 單日上升 ≥ 3 bp：`watch`，但要配合 level 解釋
- `+3 bp` 必須標記成 configurable operational threshold，同時顯示最近 1 年/5 年 percentile；唔可將佢描述成學術上固定嘅危機界線
- 如果 EFFR−IORB 或 TGCR/BGCR−IORB 同時向上、SRF > 0，或者 Reserve Balances 4w 明顯下降：severity 可提高一級

唔建議第一版設自動 `critical` 單指標規則；critical 應要求最少兩個獨立壓力來源同時確認。

### 12.3 Liquidity composite

避免將高度相關嘅 rates 重複計分。Composite 分三個 evidence blocks：

1. **Funding price（0–2 分）**
   - 0：SOFR−IORB 無異常；
   - 1：SOFR−IORB 持續轉正／超過 +3 bp，但未有跨市場確認；
   - 2：上述信號再由至少一個獨立 segment（EFFR−IORB、OBFR−IORB、TGCR/BGCR−IORB）或技術日後 persistence 確認。
2. **Reserve stock and drains（0–1 分）**
   - Reserve Balances 1w、4w 同時下降，而且 TGA 上升／Fed assets 下降，而 ON RRP cushion 已低或不足以抵消，計 1 分。
3. **Backstop dependence（0–1 分）**
   - SRF 喺非技術日持續使用，或者技術日後仍未回零，計 1 分。

狀態：

- 0：`ample/normal`
- 1：`neutral`
- 2：`watch`
- 3+：`tightening`

Technical context 最多將 confidence 降低，唔應直接改寫 raw observations。Composite 要同時保存 `raw_score`、`confirmed_score` 同 `confidence`，令用戶睇到警報係因為指標本身，定係因為有跨市場確認。

### 12.4 粵文 explanation payload

Rule engine 產生結構化內容：

```json
{
  "headline": "美元流動性暫時中性，但隔夜融資壓力較昨日上升。",
  "bullets": [
    {
      "metric_id": "sofr_iorb_spread",
      "observation": "SOFR−IORB 上升 3 bp 至 +1 bp。",
      "meaning": "SOFR 升到 IORB 之上，表示 secured overnight funding 相對央行支付嘅準備金利率變得偏貴。",
      "caveat": "今日接近月尾，部分升幅可能係資產負債表調整。",
      "confidence": "medium"
    }
  ]
}
```

必須支援以下模板：

- spread 上升／下降／持續轉正／超過 +3 bp；
- reserves 1w/4w 上升或下降；
- TGA 上升抽走流動性、下降釋放流動性；
- ON RRP cushion 增減；
- SRF 開始使用、持續使用或回落至零；
- H.4.1 尚未發布；
- 技術性扭曲；
- 數據 stale／來源失敗，因而降低結論信心。

所有句子都要描述「通常意味」同限制，避免因果過度推斷。

---

## 13. Dashboard information architecture

### 13.1 第一屏

1. 標題：`美元流動性監測`
2. 實際更新時間、market as-of date、source health。
3. 三個 switch：
   - 流動性燃料
   - 市場引信
   - 基本面逃生門
4. 主指標：SOFR−IORB 最新值、1d change、5d sparkline、異常狀態。
5. 今日粵文解讀。

### 13.2 內容區

#### A. Daily Liquidity

- SOFR、IORB、spread、EFFR、OBFR
- TGA、ON RRP、SRF
- 1M/3M/1Y/Max range selector
- Technical events overlay

#### B. Weekly Fed Balance Sheet

- Reserve Balances
- Fed Total Assets
- TGA weekly cross-check
- 1w/4w change
- 2.9T、2.8T、2.5T 只畫淡色 reference lines

#### C. Market Structure

- VIX curve/inversion
- crypto funding
- SPX/NDX price regime：20 日回報、drawdown、realized vol、20 日區間位置
- CTA proxy 及 positioning consolidation proxy
- cross-asset correlation
- 所有 market-structure charts 提供 8 週／12 週觀察窗，並顯示今期相對過去一年 percentile
- gamma flip、0DTE、skew 缺數時顯示明確 availability state

#### D. Bubble Indicators

- FINRA margin debt
- SPX 0DTE share
- S&P top-10 weight
- Buffett indicator proxy
- M2 vs Nasdaq
- insider ratio proxy
- NDX forward P/E

#### E. CapEx & Industry Reality

- hyperscaler CapEx table
- QoQ/YoY growth
- QoQ/YoY acceleration
- upstream backlog/prepayment/take-or-pay availability and notes

#### F. Sources & Methodology

- 每項來源直達連結
- quality badge
- last retrieved / as-of / expected update
- methodology
- known limitation
- downloadable JSON/CSV

### 13.3 Visual design

- 先生成完整 desktop dashboard concept，再落 code；唔好只設計 header。
- 建議深藍灰背景、白色主文字；green/amber/red 只用作語義狀態。
- 避免將每個數字放入重複 bento cards；主要用 open layout、table、chart rails。
- 金融數值使用 tabular numerals。
- 所有 chart 需有文字摘要，唔以顏色作唯一資訊載體。
- Desktop、tablet、mobile 都唔可以橫向 overflow。
- `prefers-reduced-motion` 下停用非必要動畫。

---

## 14. Data freshness 與 source health

每個 source 喺 `sources.yml` 定義：

```yaml
nyfed_reference_rates:
  expected_frequency: business_daily
  stale_after_hours: 40
  critical: true

h41:
  expected_frequency: weekly_thursday
  expected_release_time_et: "16:30"
  stale_after_days: 9
  critical: true

finra_margin:
  expected_frequency: monthly
  stale_after_days: 50
  critical: false
```

Freshness 應按來源發布頻率計，唔係所有數據超過 24 小時就叫 stale。

首頁 source health 要可以打開 drawer，睇到：

- source name
- last successful fetch
- source as-of date
- HTTP/schema error
- retained last-good version
- next expected update

---

## 15. Backfill 與 incremental update

### 15.1 Initial backfill

- SOFR：由 2018 可用起始日。
- IORB：由 2021-07-29 起；更早歷史如要延伸，必須另行處理 IOER/IORR regime，唔好直接當成 IORB。
- TGA daily：由 FiscalData DTS 可用起始日。
- ON RRP/SRF：盡量由設施可用起始日。
- H.4.1：最少 10 年，方便睇 regime；前端預設只載入短範圍。
- FINRA：由 1997 Excel 可用期開始。
- CapEx：最少 12 季。

Command：

```bash
python -m pipeline.backfill --all
```

### 15.2 Incremental

- 每日重抓最近 90 日 overlap，以捕捉修訂。
- Weekly/monthly/quarterly series 重抓最近 2 年或者最近 12 個 observations。
- 同一 `(metric_id, date)` 新值唔同時，以新值更新，並寫 revision log。
- JSON 排序穩定，避免冇實質變化但每次產生巨大 diff。

---

## 16. 測試要求

### 16.1 Unit tests

- SOFR−IORB 百分比轉 bp 正確。
- IORB as-of join 週末／假期正確。
- 1d/5d 使用有效 observation，而非 calendar day。
- 5d slope direction。
- H.4.1 1w/4w calculation。
- TGA 百萬轉十億。
- SRF 同日兩次 operation aggregate。
- month/quarter/year end event detection。
- Treasury settlement aggregation。
- CapEx YTD 轉單季、Q4 deduction、QoQ/YoY acceleration。
- Technical flag 只改 confidence，唔改 raw value。
- Missing 係 `null`，真零保留為 `0`。
- 每個 metric 都有 `question_answered`、`why_track`、`false_positives`、`confirm_with`、`cannot_conclude`；缺任何一項 schema test 必須失敗。
- Correlated confirmation rates 唔會被 composite 重複逐項計分。

### 16.2 Collector contract tests

- 對保存嘅官方 response fixtures 測試 parser。
- Live API smoke tests 獨立標記，PR 可選，scheduled workflow 必跑。
- 必要 field 缺失要 fail loudly。

### 16.3 Frontend tests

- snapshot loading/error/empty/stale states。
- quality badges。
- range selector。
- source drawer links。
- 指標 tooltip 能顯示「點解要睇」、「常見誤判」同「唔可以推論乜」。
- missing Tier C metrics 唔顯示為 0。
- mobile layout。
- chart tooltip 同 keyboard focus。

### 16.4 End-to-end acceptance

1. 由乾淨 clone 可以一個 command 生成資料同 build。
2. 關閉網絡後，build 出嚟嘅 dashboard 仍可用現有 JSON 顯示。
3. 模擬一個來源 500 error，網站仍顯示 last-good value 同 stale warning。
4. 模擬 SOFR−IORB 連續三日轉正，警報及粵文解釋正確。
5. 模擬季尾單日 spike，raw alert 保留但 confidence 降低。
6. GitHub Pages repo subpath 下所有 JSON、JS、CSS 路徑正確。

---

## 17. Security、合規與可靠性

- 所有官方 API fetch 喺 GitHub Actions 執行，唔喺 browser 執行。
- 任何未來 vendor API key 只放 GitHub Actions Secrets。
- 禁止將 secret 寫入 `public/`、Vite `VITE_*` variable 或 build log。
- SEC User-Agent 用 repo variable，例如 `ProjectName contact@example.com`；唔一定係秘密，但必須存在。
- 尊重 SEC rate limit，建議低於 5 requests/sec 並做 cache。
- 只重新發布明確容許使用嘅公開數據；對 Cboe、ETF holdings、paid vendor 檢查 terms。
- 所有外部 HTTP call 設 timeout、retry、清楚 error logging。
- JSON write 用 temporary file + atomic replace，避免中途中斷留下半個檔案。
- Generated data commit 用固定 bot identity。

---

## 18. 實作階段

### Phase 0：Repo 與設計確認

- 建立 Vite/React/TypeScript project。
- 建立完整 desktop + mobile visual concept。
- 用 mock `snapshot.json` 做第一屏、所有 section 及 missing/stale state。
- 截圖確認資訊密度、顏色、chart/table 佈局。

完成標準：用戶批准完整 dashboard concept，而唔只係 header。

### Phase 1：Core liquidity MVP

- NY Fed、IORB、FiscalData、H.4.1、Treasury auctions collectors。
- SOFR−IORB、1d、5d、H.4.1 changes。
- technical events、alerts、粵文 explanation。
- 完成 Daily Liquidity、Weekly H.4.1、Sources pages。
- GitHub Actions update + deploy。

完成標準：Tier A 全部自動化；來源失敗有 last-good fallback。

### Phase 2：Market structure

- VIX curve、crypto funding、CFTC CTA proxy、cross-asset correlations。
- 完成 Market Structure switch。
- Tier C 缺口顯示 availability state。

### Phase 3：Bubble metrics

- FINRA monthly margin debt。
- M2/Nasdaq、Buffett indicator proxy。
- SEC Form 4 proxy。
- top-10、0DTE、forward P/E 先做 manual/provider interface。

### Phase 4：CapEx 與 industry truth signals

- SEC companyfacts adapter、company mappings、12-quarter backfill。
- QoQ/YoY growth、acceleration、aggregate contribution。
- backlog/prepayment/take-or-pay manual schema 同 filing links。

### Phase 5：整合現有 daily job

- Daily job 優先讀取部署網站嘅 `data/snapshot.json`。
- Job 只負責補充自然語言分析，唔重新獨立計算數值。
- Job 引用 snapshot 內來源及 as-of date。
- Dashboard 同 job 結論唔一致時，以 snapshot 規則結果為 baseline，並記錄差異。

---

## 19. Definition of Done

以下全部完成先算第一版可以正式使用：

- [ ] GitHub Pages 公開 URL 可載入。
- [ ] Tier A 指標全部由官方來源自動更新。
- [ ] SOFR−IORB bp、1d、5d、持續轉正及 +3 bp 規則有 tests。
- [ ] 星期四 H.4.1 能顯示 level、1w、4w。
- [ ] TGA、ON RRP、SRF 已納入綜合解釋。
- [ ] 月尾、季尾、Treasury settlement、tax dates 有 context。
- [ ] 每個數據有 as-of、retrieved-at、source link、quality、status。
- [ ] 每個指標都有可見嘅「量度乜／點解要睇／常見誤判／確認指標／不可單獨推論」說明。
- [ ] Liquidity composite 將 price、stock/flow、backstop 分組，冇重複計算高度相關 rates。
- [ ] Source failure 唔會將數據變 0 或清空歷史。
- [ ] Tier C 指標清楚顯示 unavailable/manual，冇假數據。
- [ ] Desktop/mobile 無 overflow，chart/table 可讀。
- [ ] Frontend、pipeline、schema tests 全部通過。
- [ ] GitHub scheduled workflow 冇變化時唔製造無意義 commit。
- [ ] README 有本地開發、backfill、手動更新、部署、故障排查指引。

---

## 20. 可以直接交畀 Codex 嘅執行提示

```text
Implement the repository according to USD_LIQUIDITY_DASHBOARD_IMPLEMENTATION_PLAN.md.

Work in phases. Start by inspecting the repository and reporting any conflicts. Then:
1. Build and obtain approval for the complete desktop and mobile dashboard design using mock data.
2. Implement Phase 1 end to end, including data collectors, schemas, calculations, tests, static frontend, and GitHub Pages deployment workflow.
3. Do not invent or silently substitute financial data. Preserve all unavailable indicators with explicit quality/status metadata.
4. Keep the frontend fully static. Third-party data fetching must happen only in the Python pipeline/GitHub Actions.
5. Validate every external response, retain last-good data on recoverable source failures, and never convert missing values to zero.
6. Use official sources for Tier A. Include source URL, as-of date, retrieval time, and methodology in every metric.
7. Test the rendered dashboard at desktop and mobile widths, compare it against the approved concept, and fix visual or responsive drift before handoff.
8. Do not deploy until unit tests, schema validation, frontend tests, production build, and a local end-to-end update run all pass.
9. Treat Section 2 as an analysis contract: every metric must explain what it measures, why it matters, false positives, confirmation metrics, and what cannot be inferred from it. Generate the UI methodology text and rule-engine explanations from the same metadata catalog.
10. Do not convert correlation, heuristics, reference zones, or user-configured alert thresholds into unsupported causal claims.

After Phase 1, provide:
- the deployed Pages URL;
- a source/metric coverage table;
- test and build results;
- any unavailable or manual metrics;
- exact GitHub repository settings or secrets still required from me.
```

---

## 21. 主要官方參考

- NY Fed Markets Data API：https://markets.newyorkfed.org/static/docs/markets-api.html
- NY Fed Reference Rates definitions：https://www.newyorkfed.org/markets/reference-rates
- NY Fed Repo Operations：https://www.newyorkfed.org/markets/desk-operations/repo
- NY Fed Standing Repo Facility FAQ：https://www.newyorkfed.org/markets/repo-agreement-ops-faq-251210
- NY Fed year-end money-market dynamics：https://tellerwindow.newyorkfed.org/2025/01/16/monitoring-money-market-dynamics-around-year-end/
- Fed ample-reserves implementation basics：https://www.federalreserve.gov/econres/notes/feds-notes/implementing-monetary-policy-in-an-ample-reserves-regime-the-basics-note-1-of-3-20200701.html
- Fed market-based reserve indicators：https://www.federalreserve.gov/econres/notes/feds-notes/market-based-indicators-on-the-road-to-ample-reserves-20250131.html
- Federal Reserve H.4.1：https://www.federalreserve.gov/releases/h41/
- Federal Reserve/FRED IORB：https://fred.stlouisfed.org/series/IORB
- Treasury FiscalData API：https://fiscaldata.treasury.gov/api-documentation/
- Treasury Securities Auctions：https://fiscaldata.treasury.gov/datasets/treasury-securities-auctions-data/
- CFTC COT：https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm
- FINRA Margin Statistics：https://www.finra.org/rules-guidance/key-topics/margin-accounts/margin-statistics
- SEC EDGAR APIs：https://www.sec.gov/search-filings/edgar-application-programming-interfaces
- Cboe VIX term structure：https://www.cboe.com/tradable-products/vix/term-structure
- Cboe 0DTE market-impact guardrail：https://www.cboe.com/insights/posts/volatility-insights-evaluating-the-market-impact-of-spx-0-dte-options
- S&P 500 official index page：https://www.spglobal.com/spdji/en/indices/equity/sp-500/
- GitHub Pages custom workflows：https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages
- GitHub Actions scheduled workflows：https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule
