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

- Python fixture／scenario／publication gates：`153 passed`（staged schema `2.0.0` publication；41 metrics、41 series、8 automated collectors）。
- Frontend Vitest：`31 passed`；TypeScript／Vite production build：passed（只保留已知嘅 >500 kB chunk advisory）。
- Official PRE live-value reconciliation：passed。2026-08-04 四條 series 分別為 ES Asset Manager `44.281570%`、ES Leveraged Funds `-15.594834%`、Nasdaq-100 Consolidated Asset Manager `19.492872%`、Nasdaq-100 Consolidated Leveraged Funds `-30.064407%`；8W／12W／156-observation population z-score 同獨立計算一致。
- 1440×1000、1024×1000、390×844 rendered QA：passed。三個 viewport 均無橫向溢出或 console error／warning；4 張 CFTC cards、4 個 evidence blocks、6 個 rights-hold cards、12W range、hash history、drawer focus／Escape、CFTC notice及 JSON 下載均正常。
- Actions、generated-data commit、Pages deployment、live QA：pending。

final result: pending deployment and live QA
