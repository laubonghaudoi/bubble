# Release 2 — P1 Market Ignition QA record

Date: 2026-08-12<br>
Scope: CFTC TFF Futures Only positioning、rights-gated P1 interfaces、Market Ignition evidence-only UI<br>
Baseline commit: `0bb7fbda981cb2d287fe4df95f0647c52df8be0e`

## Locked contract

- CFTC E-mini S&P 500 `13874A` 同 Nasdaq-100 Consolidated `20974+` 分開。
- Asset Manager／Institutional 同 Leveraged Funds 分開；四條 canonical series 唔會合併成「CTA」數字。
- Scalar value 係 net percent open interest；statistics 保存 net contracts、open interest、8W／12W change、156-observation population z-score同 sample size。
- Market Ignition 只輸出四個 evidence blocks 嘅 coverage、direction 同 confidence；`assessment` 必須係 `null`，唔會產生 `WATCH`／`STRESS`。
- Cboe、crypto、third-party FRED、trend 同 cross-asset interfaces 在 production rights gate 下保持 `UNAVAILABLE_FREE`、零 network、value `null`。

## Verification status

- Python fixture／scenario／publication gates：最終 `157 passed`（staged schema `2.0.0` publication；41 metrics、41 series、8 automated collectors）。
- Frontend Vitest：`31 passed`；TypeScript／Vite production build：passed（只保留已知嘅 >500 kB chunk advisory）。
- Official PRE live-value reconciliation：passed。2026-08-04 四條 series 分別為 ES Asset Manager `44.281570%`、ES Leveraged Funds `-15.594834%`、Nasdaq-100 Consolidated Asset Manager `19.492872%`、Nasdaq-100 Consolidated Leveraged Funds `-30.064407%`；8W／12W／156-observation population z-score 同獨立計算一致。
- 1440×1000、1024×1000、390×844 rendered QA：passed。三個 viewport 均無橫向溢出或 console error／warning；4 張 CFTC cards、4 個 evidence blocks、6 個 rights-hold cards、12W range、hash history、drawer focus／Escape、CFTC notice及 JSON 下載均正常。
- Phase commit `f412072` 嘅 run `31640994760` 成功，並產生 data commit `72bb8c5`；首次 live probe 發現 FRED 預先發布翌日生效 IORB observation，令 P0 狀態錯誤變成 unavailable，因此未當作通過。
- 修正 commit `590a5df` 加入 FRED `observation_end` 同 publication-boundary 雙重過濾；run `31641698104` 成功，產生最終 data commit `53e95b1` 並重新部署 Pages。
- 最終 live QA：schema `2.0.0`、41 metrics／41 series、`SRC 8/8`；IORB `2026-08-12 / OK / FRESH`，五條 IORB spreads 全部 `OK / FRESH`，Liquidity Fuel `NEUTRAL 4/4`。Market Ignition 維持 `assessment: null`、`1/4 / MIXED / LOW`；四條 CFTC series 數值與 staged／官方重算一致，六個 rights-held interfaces 全部保持 `null / UNAVAILABLE_FREE / NOT_APPLICABLE`。Live browser 無 console error／warning或橫向溢出。

final result: passed
