# Manual review policy

人工 workflow 用嚟保存可審核嘅公開披露，唔係繞過 rights gate 或用手抄數字填滿 dashboard。未通過下列檢查前，metric value 保持 `null`。

## 適用狀態

- `MANUAL_READY`：schema、validation 同 UI 已準備好，但每項輸入需要人手核對；
- `UNAVAILABLE_FREE`：缺少定義一致、可重現或獲准再發布嘅 input，人工亦唔可以偽造；
- 未實作 phase：registry `implemented: false`，published output 映射為 `UNAVAILABLE_FREE / NOT_APPLICABLE / UNKNOWN`。

P0–P2 人工資料唔會自動變成 `ACTIVE_FREE` 或 `ACTIVE_PROXY`。Availability 改動需要 code/config review、來源權利覆核同測試；P3 將另行提供完整 reviewed-public-filing CSV contract，只有通過嗰份 contract 嘅 record先可以動態標記為 manual-reviewed evidence。

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
