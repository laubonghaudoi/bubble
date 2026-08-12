import {
  CONFIRMATION_SPREAD_IDS,
  OVERVIEW_SERIES_IDS,
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
    'vix_vix3m_proxy',
    'finra_margin_debt',
    'hyperscaler_capex',
  ])];
  const metrics = Object.fromEntries(ids.map((id) => [id, makeMetric(id, metricOverrides[id])]));
  metrics.vix_vix3m_proxy = makeMetric('vix_vix3m_proxy', { availability: 'ACTIVE_PROXY', context: { technical_flags: [], is_proxy: true, confidence: 'MEDIUM' }, ...metricOverrides.vix_vix3m_proxy });
  metrics.finra_margin_debt = makeMetric('finra_margin_debt', { availability: 'MANUAL_READY', value: null, quality: { status: 'NOT_APPLICABLE', freshness: 'UNKNOWN', last_attempt_at: null, last_success_at: null, failure_reason: null, sample_size: null }, ...metricOverrides.finra_margin_debt });
  metrics.hyperscaler_capex = makeMetric('hyperscaler_capex', { availability: 'UNAVAILABLE_FREE', value: null, quality: { status: 'NOT_APPLICABLE', freshness: 'UNKNOWN', last_attempt_at: null, last_success_at: null, failure_reason: null, sample_size: null }, ...metricOverrides.hyperscaler_capex });
  const evidence = (prefix: string) => [{ id: `${prefix}-1`, label: 'Evidence 1', available: true, triggered: false, status: 'OK', summary: '有新鮮資料。' }];
  return {
    schema_version: SCHEMA_VERSION,
    generated_at: NOW,
    pipeline_updated_at: NOW,
    market_date: '2026-08-11',
    overall_assessment: 'NEUTRAL',
    switches: {
      liquidity_fuel: { mode: 'ACTIVE', assessment: 'NEUTRAL', available_blocks: 4, total_blocks: 4, confidence: 'HIGH', evidence_blocks: evidence('p0'), summary: 'P0 完整。' },
      market_ignition: { mode: 'PARTIAL', assessment: null, available_blocks: 1, total_blocks: 4, confidence: 'LOW', evidence_blocks: evidence('p1'), summary: '免費代理逐步接通。' },
      fundamental_exit: { mode: 'UNAVAILABLE', assessment: null, available_blocks: 0, total_blocks: 4, confidence: 'LOW', evidence_blocks: evidence('p3'), summary: '季度資料未足夠。' },
    },
    metrics,
    technical_context: [],
    alerts: [],
    explanations: {
      headline: '美元流動性保持中性。',
      bullets: [{ metric_id: 'sofr_iorb_spread_bp', observation: '最新為 1 bp。', meaning: '融資成本略高。', alternative: '可能係結算日。', confirmation: '其他利差平穩。', judgment: '未足以證明壓力。', confidence: 'HIGH' }],
    },
    source_health: { ok: 1, stale: 0, error: 0, not_released_yet: 0, not_applicable: 1 },
    sources: {
      nyfed_rates: {
        name: 'New York Fed rates', url: 'https://example.com/nyfed', tier: 'OFFICIAL', rights_note: 'Public official data.', status: 'OK', freshness: 'FRESH', observation_date: '2026-08-11', released_at: '2026-08-12T12:00:00Z', updated_at: NOW, last_attempt_at: NOW, last_success_at: NOW, expected_next_update: '2026-08-13', failure_reason: null,
      },
      manual: {
        name: 'Manual interface', url: null, tier: 'MANUAL', rights_note: 'No value published.', status: 'NOT_APPLICABLE', freshness: 'UNKNOWN', observation_date: null, released_at: null, updated_at: NOW, last_attempt_at: null, last_success_at: null, expected_next_update: null, failure_reason: null,
      },
    },
    active_free_count: Object.values(metrics).filter((metric) => metric.availability === 'ACTIVE_FREE').length,
    active_proxy_count: 1,
    manual_ready_count: 1,
    unavailable_free_count: 1,
    stale_count: 0,
  };
}

function catalogMetric(metricId: string, layer: Layer, phase: Phase, availability: Availability): CatalogMetric {
  return { metric_id: metricId, label: metricId.toUpperCase(), unit: metricId.includes('spread') ? 'bp' : 'percent', frequency: 'business_daily', layer, phase, role: 'driver', availability, series_path: `data/series/${metricId}.json` };
}

export function makeCatalog(): CatalogMetric[] {
  return [
    ...LIQUIDITY_IDS().map((id) => catalogMetric(id, 'liquidity_fuel', 'P0', 'ACTIVE_FREE')),
    catalogMetric('vix_vix3m_proxy', 'market_ignition', 'P1', 'ACTIVE_PROXY'),
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
