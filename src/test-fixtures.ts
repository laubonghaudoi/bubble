import {
  CONFIRMATION_SPREAD_IDS,
  OVERVIEW_SERIES_IDS,
  P1_CFTC_CONFIG,
  P1_RIGHTS_GATED_IDS,
  P2_ACTIVE_IDS,
  P2_HELD_IDS,
  SCHEMA_VERSION,
  type SeriesFile,
} from './dashboard';
import type { Availability, CatalogMetric, Layer, Metric, Phase, Snapshot } from './types';

const NOW = '2026-08-12T17:32:49Z';

export function makeMetric(
  id: string,
  overrides: Partial<Metric> = {},
): Metric {
  const frequency = id.includes('weekly') || ['reserve_balances', 'fed_total_assets'].includes(id)
    ? 'weekly'
    : id.includes('margin') ? 'monthly' : id.includes('capex') ? 'quarterly' : 'business_daily';
  return {
    metric_id: id,
    label: id.toUpperCase(),
    availability: 'ACTIVE_FREE',
    value: 1,
    unit: id.includes('spread') ? 'bp' : 'percent',
    frequency,
    observation_date: '2026-08-11',
    released_at: '2026-08-12T12:00:00Z',
    updated_at: NOW,
    expected_next_update: '2026-08-13',
    changes: {
      one_observation: 0.1,
      five_observations: 0.5,
      one_week: frequency === 'weekly' ? 0.2 : undefined,
      one_month: frequency === 'monthly' ? 0.3 : undefined,
      one_quarter: frequency === 'quarterly' ? 0.4 : undefined,
    },
    statistics: { mean_20_observations: 0.75, z_score_20_observations: 0.4 },
    quality: { status: 'OK', freshness: 'FRESH', last_attempt_at: NOW, last_success_at: NOW, failure_reason: null, sample_size: 40 },
    context: { technical_flags: [], is_proxy: false, confidence: 'HIGH' },
    source: { name: 'Official source', url: 'https://example.com/data', tier: 'OFFICIAL', retrieved_at: NOW, rights_note: 'Public official data.' },
    methodology: {
      question: '回答咩問題？',
      definition: '精確定義。',
      why_it_matters: '金融意義。',
      direction: '方向解讀。',
      calculation: '計算方法。',
      frequency_and_lag: '發布頻率。',
      common_misreads: '常見誤判。',
      technical_distortions: '技術扭曲。',
      confirm_with: ['SOFR', 'IORB'],
      cannot_infer: '不可以單獨推論市場方向。',
      source_and_license_note: '公開來源。',
      proxy_disclosure: '',
    },
    short_series: [{ date: '2026-08-10', value: 0.9 }, { date: '2026-08-11', value: 1 }],
    ...overrides,
  };
}

export function makeSnapshot(metricOverrides: Record<string, Partial<Metric>> = {}): Snapshot {
  const ids = [...new Set([
    ...OVERVIEW_SERIES_IDS,
    ...CONFIRMATION_SPREAD_IDS,
    ...P1_CFTC_CONFIG.map(({ id }) => id),
    ...P1_RIGHTS_GATED_IDS,
    ...P2_ACTIVE_IDS,
    ...P2_HELD_IDS,
    'hyperscaler_capex',
  ])];
  const metrics = Object.fromEntries(ids.map((id) => [id, makeMetric(id, metricOverrides[id])]));
  P1_CFTC_CONFIG.forEach(({ id }, index) => {
    metrics[id] = makeMetric(id, {
      label: id.toUpperCase(),
      availability: id.includes('leveraged_funds') ? 'ACTIVE_PROXY' : 'ACTIVE_FREE',
      value: index % 2 === 0 ? 12.34 : -4.56,
      unit: 'percent_open_interest',
      frequency: 'weekly',
      changes: { one_observation: 0.25, five_observations: 1.1, one_week: 0.25, eight_weeks: index % 2 === 0 ? 1.25 : -0.75, twelve_weeks: index % 2 === 0 ? 2.5 : -1.5 },
      statistics: {
        net_position: index % 2 === 0 ? 123456 : -45678,
        net_percent_open_interest: index % 2 === 0 ? 12.34 : -4.56,
        change_8_weeks: index % 2 === 0 ? 1.25 : -0.75,
        change_12_weeks: index % 2 === 0 ? 2.5 : -1.5,
        z_score_3_year: index % 2 === 0 ? 0.8 : -0.4,
        z_score_3_year_sample_size: 156,
        open_interest: 987654,
        sample_size: 156,
      },
      quality: { status: 'OK', freshness: 'FRESH', last_attempt_at: NOW, last_success_at: NOW, failure_reason: null, sample_size: 156 },
      context: {
        technical_flags: [],
        is_proxy: id.includes('leveraged_funds'),
        confidence: 'HIGH',
        direction: index % 2 === 0 ? 'MORE_NET_LONG' : 'MORE_NET_SHORT',
      },
      source: { name: 'CFTC TFF Futures Only', url: 'https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm', tier: 'OFFICIAL', retrieved_at: NOW, rights_note: 'Official CFTC TFF public report.' },
      short_series: [{ date: '2026-06-16', value: index % 2 === 0 ? 9.84 : -3.06 }, { date: '2026-08-11', value: index % 2 === 0 ? 12.34 : -4.56 }],
      ...metricOverrides[id],
    });
  });
  const rightsReasons: Record<string, string> = {
    vix_vix3m_term_structure_proxy: 'No redistribution-cleared Cboe feed is configured.',
    cboe_skew_tail_risk_proxy: 'No redistribution-cleared Cboe feed is configured.',
    crypto_funding_btc: 'Public endpoints do not provide redistribution rights for this public dashboard.',
    crypto_funding_eth: 'Public endpoints do not provide redistribution rights for this public dashboard.',
    trend_following_positioning_proxy: 'Redistribution-cleared equity and cross-asset price inputs are not configured.',
    cross_asset_correlation: 'Several planned FRED series carry third-party redistribution restrictions.',
  };
  P1_RIGHTS_GATED_IDS.forEach((id) => {
    const reason = rightsReasons[id];
    metrics[id] = makeMetric(id, {
      availability: 'UNAVAILABLE_FREE',
      value: null,
      quality: { status: 'NOT_APPLICABLE', freshness: 'UNKNOWN', last_attempt_at: null, last_success_at: null, failure_reason: reason, sample_size: null },
      context: { technical_flags: [], is_proxy: id.includes('proxy'), confidence: 'UNKNOWN' },
      source: { name: id.includes('crypto') ? 'Crypto market-data interface' : 'Rights-gated provider interface', url: null, tier: 'PERMISSION_REQUIRED', retrieved_at: null, rights_note: reason },
      methodology: { ...makeMetric(id).methodology, direction: 'No direction is published while the value is null.', calculation: `${reason} Future provider interface remains disabled until rights pass.`, source_and_license_note: reason },
      short_series: [],
      ...metricOverrides[id],
    });
  });
  metrics.nonfinancial_equities_gdp_proxy = makeMetric('nonfinancial_equities_gdp_proxy', {
    label: 'Nonfinancial corporate equities / GDP proxy',
    availability: 'ACTIVE_PROXY',
    value: 184.25,
    unit: 'percent',
    frequency: 'quarterly',
    observation_date: '2026-03-31',
    released_at: '2026-06-25T12:00:00Z',
    changes: { one_observation: 3.1, five_observations: 8.4, one_quarter: 3.1 },
    statistics: {
      equity_usd_bn: 56800,
      gdp_usd_bn: 30828,
      qoq_percent_change: 1.71,
      yoy_percent_change: 9.42,
      percentile_10y: 88.5,
      percentile_10y_sample_size: 40,
    },
    quality: { status: 'OK', freshness: 'FRESH', last_attempt_at: NOW, last_success_at: NOW, failure_reason: null, sample_size: 40 },
    context: {
      technical_flags: [], is_proxy: true, confidence: 'MEDIUM', direction: 'HIGHER',
      equity_observation_date: '2026-03-31', gdp_observation_date: '2026-03-31', common_quarter: '2026-Q1',
    },
    source: { source_id: 'fred_government', name: 'Official source', url: 'https://example.com/data', tier: 'OFFICIAL', retrieved_at: NOW, rights_note: 'Public official data.' },
    methodology: {
      ...makeMetric('nonfinancial_equities_gdp_proxy').methodology,
      definition: 'Nonfinancial corporate equity liabilities divided by GDP; not total U.S. equity market capitalization.',
      common_misreads: 'This proxy is not total U.S. equity market capitalization and does not prove a bubble.',
      proxy_disclosure: 'Nonfinancial corporate equity liabilities are not total U.S. equity market capitalization.',
    },
    short_series: [{ date: '2025-12-31', value: 181.15 }, { date: '2026-03-31', value: 184.25 }],
    ...metricOverrides.nonfinancial_equities_gdp_proxy,
  });
  metrics.sec_form4_nonderivative_ps_count_ratio_20d = makeMetric('sec_form4_nonderivative_ps_count_ratio_20d', {
    label: 'SEC Form 4 non-derivative P/S count ratio · 20D',
    availability: 'ACTIVE_PROXY',
    value: 0.42,
    unit: 'ratio',
    frequency: 'business_daily',
    changes: { one_observation: -0.03, five_observations: 0.08, twenty_observations: -0.12 },
    statistics: {
      ratio_5d: 0.55,
      count_ratio_20d: 0.42,
      purchase_count_5d: 10,
      sale_count_5d: 19,
      purchase_count_20d: 41,
      sale_count_20d: 99,
      dollar_ratio_5d: null,
      dollar_ratio_20d: 0.08,
      dollar_coverage_rate_5d: 0.76,
      dollar_coverage_rate_20d: 0.84,
      ex_explicit_false_count_ratio_5d: 0.75,
      ex_explicit_false_count_ratio_20d: 0.61,
      ex_explicit_false_coverage_5d: 0.72,
      ex_explicit_false_coverage_20d: 0.81,
      eligible_transaction_count_20d: 138,
      priced_transaction_count_20d: 116,
      unique_accessions_20d: 104,
      unique_issuers_20d: 88,
      filings_processed_20d: 107,
      form4_count_20d: 103,
      form4a_count_20d: 4,
      amendments_linked_20d: 2,
      amendments_review_count_20d: 2,
      parse_failures_20d: 1,
      tenb5_true_filings_20d: 44,
      tenb5_false_filings_20d: 51,
      tenb5_unknown_filings_20d: 12,
    },
    quality: { status: 'OK', freshness: 'FRESH', last_attempt_at: NOW, last_success_at: NOW, failure_reason: null, sample_size: 20 },
    context: {
      technical_flags: [], is_proxy: true, confidence: 'MEDIUM', direction: 'MORE_SALES',
      window_start_5d: '2026-08-05', window_end_5d: '2026-08-11',
      window_start_20d: '2026-07-15', window_end_20d: '2026-08-11',
      dollar_status_5d: 'INSUFFICIENT_PRICE_COVERAGE', dollar_status_20d: 'PUBLISHED',
      ex_10b5_scope: 'EXPLICIT_FALSE_ONLY',
    },
    source: { source_id: 'sec_edgar', name: 'SEC EDGAR Form 4', url: 'https://www.sec.gov/Archives/edgar/daily-index/', tier: 'OFFICIAL', retrieved_at: NOW, rights_note: 'Public EDGAR filing content; cite SEC and filing accessions.' },
    methodology: {
      ...makeMetric('sec_form4_nonderivative_ps_count_ratio_20d').methodology,
      definition: 'Counts non-derivative Table I P/S rows. SEC defines P/S as open-market or private purchases/sales.',
      common_misreads: 'P/S includes open-market or private transactions and is not an open-market-only signal.',
      proxy_disclosure: 'Transaction-row proxy; filings can contain private transactions, amendments, and filing-level 10b5-1 flags.',
    },
    short_series: [{ date: '2026-08-08', value: 0.45 }, { date: '2026-08-11', value: 0.42 }],
    ...metricOverrides.sec_form4_nonderivative_ps_count_ratio_20d,
  });
  const p2HeldReasons: Record<(typeof P2_HELD_IDS)[number], string> = {
    finra_margin_debt: 'FINRA terms do not clear automated database construction or public redistribution.',
    spy_holdings_top10_weight_proxy: 'State Street terms do not clear an automated public redistribution workflow.',
    spx_0dte_share: 'No redistribution-cleared free source exposes a definition-consistent same-day-expiration numerator.',
    ndx_forward_pe: 'A consistent reproducible forward-earnings consensus is proprietary.',
    m2_nasdaq_divergence: 'Nasdaq series redistribution rights are not cleared by access through FRED.',
    gamma_flip: 'Reliable dealer net-gamma and trade-direction inputs are not publicly available.',
  };
  P2_HELD_IDS.forEach((id) => {
    const reason = p2HeldReasons[id];
    metrics[id] = makeMetric(id, {
      availability: 'UNAVAILABLE_FREE', value: null,
      observation_date: null, released_at: null, updated_at: null, expected_next_update: null,
      quality: { status: 'NOT_APPLICABLE', freshness: 'UNKNOWN', last_attempt_at: null, last_success_at: null, failure_reason: reason, sample_size: null },
      context: { technical_flags: [], is_proxy: id.includes('proxy'), confidence: 'UNKNOWN' },
      source: { source_id: null, name: 'Rights-gated or incomplete provider interface', url: null, tier: 'PERMISSION_REQUIRED', retrieved_at: null, rights_note: reason },
      methodology: { ...makeMetric(id).methodology, calculation: `${reason} Provider interface remains fail-closed.`, source_and_license_note: reason },
      short_series: [],
      ...metricOverrides[id],
    });
  });
  metrics.hyperscaler_capex = makeMetric('hyperscaler_capex', { availability: 'UNAVAILABLE_FREE', value: null, quality: { status: 'NOT_APPLICABLE', freshness: 'UNKNOWN', last_attempt_at: null, last_success_at: null, failure_reason: null, sample_size: null }, ...metricOverrides.hyperscaler_capex });
  const evidence = (prefix: string) => [{ id: `${prefix}-1`, label: 'Evidence 1', available: true, triggered: null, status: 'OK', direction: 'FLAT', confidence: 'HIGH', summary: '有新鮮資料。' }];
  const p1Evidence = [
    { id: 'volatility_term_structure', label: 'Volatility term structure', available: false, triggered: null, status: 'UNAVAILABLE_FREE', direction: 'UNKNOWN', confidence: 'UNKNOWN', summary: rightsReasons.vix_vix3m_term_structure_proxy },
    { id: 'trend_positioning', label: 'Trend / positioning', available: true, triggered: null, status: 'MIXED', direction: 'MIXED', confidence: 'LOW', summary: '四條 CFTC TFF series 新鮮；合約同類別方向混合。' },
    { id: 'options_tail_risk', label: 'Options / tail-risk proxy', available: false, triggered: null, status: 'UNAVAILABLE_FREE', direction: 'UNKNOWN', confidence: 'UNKNOWN', summary: rightsReasons.cboe_skew_tail_risk_proxy },
    { id: 'crypto_cross_asset', label: 'Crypto funding / cross-asset', available: false, triggered: null, status: 'UNAVAILABLE_FREE', direction: 'UNKNOWN', confidence: 'UNKNOWN', summary: rightsReasons.crypto_funding_btc },
  ];
  const macro = metrics.nonfinancial_equities_gdp_proxy;
  const form4 = metrics.sec_form4_nonderivative_ps_count_ratio_20d;
  return {
    schema_version: SCHEMA_VERSION,
    generated_at: NOW,
    pipeline_updated_at: NOW,
    market_date: '2026-08-11',
    overall_assessment: 'NEUTRAL',
    switches: {
      liquidity_fuel: { mode: 'ACTIVE', assessment: 'NEUTRAL', available_blocks: 4, total_blocks: 4, confidence: 'HIGH', evidence_blocks: evidence('p0'), summary: 'P0 完整。' },
      market_ignition: { mode: 'EVIDENCE_ONLY', assessment: null, available_blocks: 1, total_blocks: 4, confidence: 'LOW', evidence_blocks: p1Evidence, summary: '只展示 evidence coverage、方向同信心；不設綜合嚴重度。' },
      fundamental_exit: { mode: 'UNAVAILABLE', assessment: null, available_blocks: 0, total_blocks: 4, confidence: 'LOW', evidence_blocks: evidence('p3'), summary: '季度資料未足夠。' },
    },
    metrics,
    technical_context: [],
    alerts: [],
    explanations: {
      headline: '美元流動性保持中性。',
      bullets: [{ metric_id: 'sofr_iorb_spread_bp', observation: '最新為 1 bp。', meaning: '融資成本略高。', alternative: '可能係結算日。', confirmation: '其他利差平穩。', judgment: '未足以證明壓力。', confidence: 'HIGH' }],
    },
    source_health: { ok: 4, stale: 0, error: 0, not_released_yet: 0, not_applicable: 1 },
    sources: {
      nyfed_rates: {
        name: 'New York Fed rates', url: 'https://example.com/nyfed', tier: 'OFFICIAL', rights_note: 'Public official data.', status: 'OK', freshness: 'FRESH', observation_date: '2026-08-11', released_at: '2026-08-12T12:00:00Z', updated_at: NOW, last_attempt_at: NOW, last_success_at: NOW, expected_next_update: '2026-08-13', failure_reason: null,
      },
      manual: {
        name: 'Manual interface', url: null, tier: 'MANUAL', rights_note: 'No value published.', status: 'NOT_APPLICABLE', freshness: 'UNKNOWN', observation_date: null, released_at: null, updated_at: NOW, last_attempt_at: null, last_success_at: null, expected_next_update: null, failure_reason: null,
      },
      cftc_tff_futures_only: {
        name: 'CFTC TFF Futures Only', url: 'https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm', tier: 'OFFICIAL', rights_note: 'Official CFTC public report.', status: 'OK', freshness: 'FRESH', observation_date: '2026-08-11', released_at: '2026-08-12T12:00:00Z', updated_at: NOW, last_attempt_at: NOW, last_success_at: NOW, expected_next_update: '2026-08-13', failure_reason: null,
      },
      fred_nonfinancial_equities_gdp: {
        collector_id: 'fred_nonfinancial_equities_gdp', name: macro.source.name ?? '',
        url: macro.source.url, tier: macro.source.tier, rights_note: macro.source.rights_note,
        status: macro.quality.status, freshness: macro.quality.freshness,
        observation_date: macro.observation_date, released_at: macro.released_at,
        updated_at: NOW, last_attempt_at: macro.quality.last_attempt_at,
        last_success_at: macro.quality.last_success_at,
        expected_next_update: macro.expected_next_update, failure_reason: macro.quality.failure_reason,
      },
      sec_form4_daily_index: {
        collector_id: 'sec_form4_daily_index', name: form4.source.name ?? '',
        url: form4.source.url, tier: form4.source.tier, rights_note: form4.source.rights_note,
        status: form4.quality.status, freshness: form4.quality.freshness,
        observation_date: form4.observation_date, released_at: form4.released_at,
        updated_at: NOW, last_attempt_at: form4.quality.last_attempt_at,
        last_success_at: form4.quality.last_success_at,
        expected_next_update: form4.expected_next_update, failure_reason: form4.quality.failure_reason,
      },
    },
    active_free_count: Object.values(metrics).filter((metric) => metric.availability === 'ACTIVE_FREE').length,
    active_proxy_count: Object.values(metrics).filter((metric) => metric.availability === 'ACTIVE_PROXY').length,
    manual_ready_count: Object.values(metrics).filter((metric) => metric.availability === 'MANUAL_READY').length,
    unavailable_free_count: Object.values(metrics).filter((metric) => metric.availability === 'UNAVAILABLE_FREE').length,
    stale_count: 0,
  };
}

function catalogMetric(metricId: string, layer: Layer, phase: Phase, availability: Availability): CatalogMetric {
  return { metric_id: metricId, label: metricId.toUpperCase(), unit: metricId.includes('spread') ? 'bp' : 'percent', frequency: 'business_daily', layer, phase, role: 'driver', availability, series_path: `data/series/${metricId}.json` };
}

export function makeCatalog(): CatalogMetric[] {
  return [
    ...LIQUIDITY_IDS().map((id) => catalogMetric(id, 'liquidity_fuel', 'P0', 'ACTIVE_FREE')),
    ...P1_CFTC_CONFIG.map(({ id }) => catalogMetric(id, 'market_ignition', 'P1', id.includes('leveraged_funds') ? 'ACTIVE_PROXY' : 'ACTIVE_FREE')),
    ...P1_RIGHTS_GATED_IDS.map((id) => catalogMetric(id, 'market_ignition', 'P1', 'UNAVAILABLE_FREE')),
    ...P2_ACTIVE_IDS.map((id) => catalogMetric(id, 'market_ignition', 'P2', 'ACTIVE_PROXY')),
    ...P2_HELD_IDS.map((id) => catalogMetric(id, 'market_ignition', 'P2', 'UNAVAILABLE_FREE')),
    catalogMetric('hyperscaler_capex', 'fundamental_exit', 'P3', 'UNAVAILABLE_FREE'),
  ];
}

function LIQUIDITY_IDS() {
  return [...new Set([...OVERVIEW_SERIES_IDS, ...CONFIRMATION_SPREAD_IDS])];
}

export function makeSeriesFile(metric: Metric): SeriesFile {
  return {
    schema_version: SCHEMA_VERSION,
    metric_id: metric.metric_id,
    label: metric.label,
    unit: metric.unit,
    frequency: metric.frequency,
    availability: metric.availability,
    quality: metric.quality,
    observation_date: metric.observation_date,
    released_at: metric.released_at,
    updated_at: metric.updated_at,
    source: metric.source,
    observations: metric.short_series,
  };
}

export function jsonResponse(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } });
}
