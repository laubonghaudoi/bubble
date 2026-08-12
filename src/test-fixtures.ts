import {
  CONFIRMATION_SPREAD_IDS,
  OVERVIEW_SERIES_IDS,
  P1_CFTC_CONFIG,
  P1_RIGHTS_GATED_IDS,
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
    'finra_margin_debt',
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
  metrics.finra_margin_debt = makeMetric('finra_margin_debt', { availability: 'MANUAL_READY', value: null, quality: { status: 'NOT_APPLICABLE', freshness: 'UNKNOWN', last_attempt_at: null, last_success_at: null, failure_reason: null, sample_size: null }, ...metricOverrides.finra_margin_debt });
  metrics.hyperscaler_capex = makeMetric('hyperscaler_capex', { availability: 'UNAVAILABLE_FREE', value: null, quality: { status: 'NOT_APPLICABLE', freshness: 'UNKNOWN', last_attempt_at: null, last_success_at: null, failure_reason: null, sample_size: null }, ...metricOverrides.hyperscaler_capex });
  const evidence = (prefix: string) => [{ id: `${prefix}-1`, label: 'Evidence 1', available: true, triggered: null, status: 'OK', direction: 'FLAT', confidence: 'HIGH', summary: '有新鮮資料。' }];
  const p1Evidence = [
    { id: 'volatility_term_structure', label: 'Volatility term structure', available: false, triggered: null, status: 'UNAVAILABLE_FREE', direction: 'UNKNOWN', confidence: 'UNKNOWN', summary: rightsReasons.vix_vix3m_term_structure_proxy },
    { id: 'trend_positioning', label: 'Trend / positioning', available: true, triggered: null, status: 'MIXED', direction: 'MIXED', confidence: 'LOW', summary: '四條 CFTC TFF series 新鮮；合約同類別方向混合。' },
    { id: 'options_tail_risk', label: 'Options / tail-risk proxy', available: false, triggered: null, status: 'UNAVAILABLE_FREE', direction: 'UNKNOWN', confidence: 'UNKNOWN', summary: rightsReasons.cboe_skew_tail_risk_proxy },
    { id: 'crypto_cross_asset', label: 'Crypto funding / cross-asset', available: false, triggered: null, status: 'UNAVAILABLE_FREE', direction: 'UNKNOWN', confidence: 'UNKNOWN', summary: rightsReasons.crypto_funding_btc },
  ];
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
    source_health: { ok: 2, stale: 0, error: 0, not_released_yet: 0, not_applicable: 1 },
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
    },
    active_free_count: Object.values(metrics).filter((metric) => metric.availability === 'ACTIVE_FREE').length,
    active_proxy_count: Object.values(metrics).filter((metric) => metric.availability === 'ACTIVE_PROXY').length,
    manual_ready_count: 1,
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
    catalogMetric('finra_margin_debt', 'market_ignition', 'P2', 'MANUAL_READY'),
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
