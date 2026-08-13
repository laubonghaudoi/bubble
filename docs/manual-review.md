# Manual review policy

人工 workflow 用嚟保存可審核嘅公開披露，唔係繞過 rights gate 或用手抄數字填滿 dashboard。未通過下列檢查前，metric value 保持 `null`。

## 適用狀態

- `MANUAL_READY`：schema、validation 同 UI 已準備好，但每項輸入需要人手核對；
- `UNAVAILABLE_FREE`：缺少定義一致、可重現或獲准再發布嘅 input，人工亦唔可以偽造；
- 未實作 phase：registry `implemented: false`，published output 映射為 `UNAVAILABLE_FREE / NOT_APPLICABLE / UNKNOWN`。

P0–P2 人工資料唔會自動變成 `ACTIVE_FREE` 或 `ACTIVE_PROXY`。Availability 改動需要 code/config review、來源權利覆核同測試。P3 只有通過下列 reviewed-public-filing CSV contract 嘅 record 先可以動態標記為 `ACTIVE_FREE`；來源仍然係 `network_enabled: false`，程式唔會由 filing prose 猜數字。

## 每筆 manual record 必須有

- canonical `metric_id`；
- period end／session date 同 as-of date；
- `value` 或明確 `null`，以及 unit；
- 定義一致嘅 numerator／denominator（適用時）；
- official/public source URL；
- filing accession 或文件版本（適用時）；
- reviewer、review date 同短 review note；
- comparability flag；
- 定義變更、coverage 或 rights caveat。

禁止用搜尋摘要、新聞二手數字、無 URL spreadsheet、登入後/付費內容、未授權 key/cookie，或者名稱相近但定義不同嘅 proxy。

## Review sequence

1. 核對來源係原始官方／issuer 文件，並保存可重開嘅 URL。
2. 核對 period、observation time、unit、scale 同 scope。
3. 對照 metric methodology；proxy 必須用 proxy 名稱及 disclosure。
4. 檢查缺失值保持 `null`，真實零值要有來源證據。
5. 核對 rights：manual input 唔會令被禁止再發布嘅內容變得合法。
6. 由第二位 reviewer 覆核高影響定義變更、numerator/denominator 或公司 disclosure mapping。
7. 執行 Python contract tests、frontend tests 同 build；只喺全部通過後發布完整 data directory。

## Specific manual interfaces

### SPX 0DTE share

必須有同一 session、定義一致嘅 SPX same-day-expiry contracts numerator 同 all-SPX contracts denominator，以及 Cboe/source URL。SPY、QQQ、全市場 options 或新聞報導比例唔可以冒充 SPX 0DTE share。

### Industry signals

Orders、backlog、prepayments、take-or-pay 等非標準披露只可以由公開 filing 人手整理。可以記錄 `UP / FLAT / DOWN / UNKNOWN` 同短 factual paraphrase；唔好長篇複製 issuer narrative。定義轉變時設 `comparable: false`。

正式輸入係 `data/manual/industry_signals.csv`，header 必須保留以下 17 欄及次序：

```text
company_id,period_end,metric_id,direction,value,unit,yoy_pct,comparable,source_type,source_url,filing_accession,filing_accepted_at,as_of,reviewer,reviewed_at,paraphrase,review_note
```

- `company_id` 只接受 `microsoft`、`alphabet`、`amazon`、`meta`；
- `metric_id` 只接受 `ai_upstream_orders_backlog`、`customer_prepayments_contract_commitments`、`take_or_pay_commitments`；
- `direction` 只接受大寫 `UP`、`FLAT`、`DOWN`、`UNKNOWN`；
- 無數值時 `value` 同 `unit` 留空，代表真正 `null`；真實零值填 `0` 並保留來源；
- 有數值時 `unit` 必須精確使用 `USD`、`USD mn`、`USD bn`、`count`、`units`、`percent`、`percentage_points`、`ratio`、`MW` 或 `GW`，pipeline 唔會暗中轉 scale；
- `yoy_pct` 只收 plain decimal；`comparable=false` 時必須留空；
- `comparable` 必須係小寫 `true` 或 `false`；定義、scope 或計量基礎改變時必須係 `false`；
- `source_type` 只收官方 SEC filing 類型；`source_url` 必須係 `www.sec.gov/Archives/edgar/data/...` 嘅直接 filing HTML文件，並同時對應 issuer CIK path同一個 accession；issuer IR、新聞或下載頁唔可以代替 filing URL；
- `filing_accession` 使用 `##########-##-######` canonical 格式；accession prefix 可以係 filing agent CIK，所以公司身份由 SEC Archives URL 嘅 issuer CIK path 核對，唔靠 prefix 猜；
- `filing_accepted_at` 同 `reviewed_at` 必須係以 `Z` 結尾嘅 UTC timestamp；`period_end <= filing accepted date <= as_of <= reviewed date`；
- `reviewer`、短 `paraphrase` 同 `review_note` 全部必填；paraphrase 上限 280 字，review note 上限 500 字，唔可以貼長段原文；
- `(company_id, period_end, metric_id, filing_accession)` 係唯一 identity，重複 row 會令 validation fail closed。

Header-only template 係有效狀態，三項 metric 會保持 `MANUAL_READY`。任何 row validation 失敗都會阻止正常 PR checks／production publication，唔會部分發布。人工更新必須經 PR review；唔好直接改 `public/data/**`。

同一 metric 每個 `as_of` 只發布一個 aggregate observation；入面保存截至當日每間公司最新嘅完整 reviewed record，唔會因同日多家公司而互相覆寫。相對 aggregate date 超過 120 日嘅 carried record 唔計入 current company／comparable count 或方向；aggregate `value` 因 mixed units 永遠係 `null`，真實 `0` 只喺原 record 保存。

`.github/workflows/check-p3-disclosures.yml` 只讀四間公司嘅 SEC submissions metadata，搵出新 filing、缺少 review 或 evidence `as_of` 超過 120 日嘅 review，然後 create／update 同一個由 `github-actions[bot]` 建立嘅 marker-owned GitHub issue。每個未覆核 accession 都會一直留喺 queue，唔會因只 review 最新 filing 而靜默漏掉舊項；180 日內嘅 reviewed row亦會核對 SEC form、acceptance timestamp同primary document URL。佢只有 `contents: read` 同 `issues: write`，唔會下載 filing prose、抽取數值、commit、push 或 deploy。可以用以下方式先睇本地 discovery output：

```bash
SEC_USER_AGENT='Bubble USD Liquidity Dashboard laubonghaudoi@icloud.com' \
  python -m pipeline.check_p3_disclosures --dry-run
```

### SEC Form 4 amendment review

P2 collector只會自動套用能唯一連結嘅 Form 4/A transaction replacement。未能唯一對應 original accession、超出 45 日 ledger或 transaction fingerprint有歧義嘅 amendment會標記 `UNLINKED_REVIEW`、排除於 proxy，並計入 review count；人手唔可以只憑姓名或相近金額強制合併。Row-level parse anomaly亦只會 quarantine相關 row並保留 audit reason，唔會將缺失當零。

### Proprietary metrics

Gamma flip、NDX forward P/E、精確 option skew 等缺少核心 proprietary inputs 時保持 `UNAVAILABLE_FREE`。所謂 manual override 唔可以只填一個無法重現嘅值；日後 provider interface 必須保存 provider、contract entitlement、as-of、method、source identifier 同 audit trail。

## Reviewed calendars

`config/us_tax_dates.yml` 同 `config/nyfed_operational_readiness.yml` 係人手覆核 registry：

- 每筆要有 `reviewed: true`、reviewer、reviewed date 同官方 source URL；
- tax window 以 observed deadline 前後各一個 business day 計；
- weekend、holiday、disaster relief 或官方更正要新增／修改 version-controlled entry；
- NY Fed technical exercise 必須按官方公告日期及 operation type match，唔可以靠金額或時間推斷。

改 calendar 後必須重新跑 contract/scenario tests，並由 diff 清楚顯示來源同日期變更。
