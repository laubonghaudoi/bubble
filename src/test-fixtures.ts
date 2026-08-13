import {
  CONFIRMATION_SPREAD_IDS,
  OVERVIEW_SERIES_IDS,
  P1_CFTC_CONFIG,
  P1_RIGHTS_GATED_IDS,
  P2_ACTIVE_IDS,
  P2_HELD_IDS,
  P3_AUTOMATED_IDS,
  P3_MANUAL_IDS,
  P3_METRIC_IDS,
  SCHEMA_VERSION,
  type SeriesFile,
} from './dashboard';
import type { Availability, CatalogMetric, FormulaClause, FundamentalCompanyDetail, Layer, ManualEvidenceRecord, Metric, Phase, Snapshot, VideoP0Model } from './types';

const NOW = '2026-08-12T17:32:49Z';

const VIDEO_SOURCE_URL = 'https://www.youtube.com/watch?v=MrnjBdgQPLU';

function videoClause(
  clause_id: string,
  order: number,
  label: string,
  metric: Metric | null,
  operator: FormulaClause['operator'],
  threshold: FormulaClause['threshold'],
  threshold_unit: string | null,
  current_value: FormulaClause['current_value'],
  current_unit: string | null,
  met: boolean | null,
  sourceSegmentId: string | null,
  evaluation_state: FormulaClause['evaluation_state'] = 'CURRENT',
): FormulaClause {
  return {
    clause_id, order, label, metric_id: metric?.metric_id ?? null, operator,
    threshold, threshold_unit, current_value, current_unit, met,
    observation_date: metric?.observation_date ?? null,
    released_at: metric?.released_at ?? null,
    quality_status: metric?.quality.status ?? 'NOT_APPLICABLE',
    freshness: metric?.quality.freshness ?? 'UNKNOWN',
    evaluation_state,
    basis: [
      {
        kind: 'VIDEO_SOURCE_RULE',
        label: 'Cited video rule',
        source_segment_id: sourceSegmentId,
        note: 'The video supplies the editorial rule; the dashboard shows a separate operationalization.',
      },
      {
        kind: metric ? 'DASHBOARD_OPERATIONALIZATION' : 'MANUAL_CONTEXT',
        label: metric ? 'Dashboard operationalization' : 'Version-controlled crisis-context review',
        source_segment_id: sourceSegmentId,
        note: metric ? 'Threshold and measurement are explicit in the decision-model contract.' : 'No automatic news or API inference.',
      },
    ],
    note: '',
  };
}

export function makeVideoP0Model(metrics: Record<string, Metric>): VideoP0Model {
  const spread = metrics.sofr_iorb_spread_bp;
  const reserves = metrics.reserve_balances;
  const tga = metrics.tga_daily;
  const srf = metrics.srf_accepted;
  const yellowClauses = [
    videoClause('sofr_positive_streak', 1, 'SOFR−IORB positive streak', spread, '>=', 3, 'observations', 0, 'observations', false, 'yellow_red'),
    videoClause('reserve_below_yellow', 2, 'Reserve balances below Yellow level', reserves, '<', 2900, 'USD bn', reserves.value, 'USD bn', false, 'yellow_red'),
    videoClause('reserve_change_4w_negative', 3, 'Reserve balances 4W change below zero', reserves, '<', 0, 'USD bn', -100, 'USD bn', true, 'reserve_exit_1'),
    videoClause('tga_near_1t', 4, 'TGA at operational floor', tga, '>=', 950, 'USD bn', tga.value, 'USD bn', true, 'yellow_red'),
  ];
  const redClauses = [
    videoClause('sofr_spread_above_red', 1, 'SOFR−IORB above Red spread', spread, '>', 3, 'bp', spread.value, 'bp', false, 'yellow_red'),
    videoClause('reserve_below_red', 2, 'Reserve balances below Red level', reserves, '<', 2800, 'USD bn', reserves.value, 'USD bn', false, 'yellow_red'),
    videoClause('srf_positive_days', 3, 'SRF nontechnical positive days', srf, '>=', 2, 'days in latest 3 completed days', 0, 'days', false, 'yellow_red'),
  ];
  const extremeClauses = [
    videoClause('reserve_below_extreme', 1, 'Reserve balances below Extreme level', reserves, '<', 2500, 'USD bn', reserves.value, 'USD bn', false, 'reserve_exit_2'),
    videoClause('reserve_rapid_decline', 2, '4W decline at or below trailing 5Y p10', reserves, '<=', -200, 'USD bn', -100, 'USD bn', false, 'reserve_exit_2'),
    videoClause('no_major_crisis', 3, 'No major crisis context', null, '=', 'NO_MAJOR_CRISIS', null, 'UNKNOWN', null, null, null, 'REVIEW_REQUIRED'),
  ];
  return {
    model_id: 'henren778_p0_liquidity',
    label: '影片 P0 黃／紅流動性警報',
    enabled: true,
    status: 'GREEN',
    data_status: 'CURRENT',
    confidence: 'HIGH',
    availability_reason: null,
    evaluated_at: NOW,
    source: {
      title: '一個月前全網喊AI泡沫要崩，我說鬼故事是洗盤不是葬禮，二波窗口鎖死7月底8月初！對賭：納指洗完近一成，道指標普齊創新高，美光單日暴拉18.4%！復盤釘死，二波打法五步三開關全套交付',
      display_title: '一個月前全網喊 AI 泡沫要崩',
      author: '一个狠人',
      url: VIDEO_SOURCE_URL,
      segments: [
        { segment_id: 'yellow_red', label: 'Yellow / Red formula', start_seconds: 1380, end_seconds: 1440, timestamp_url: `${VIDEO_SOURCE_URL}&t=1380s` },
        { segment_id: 'reserve_exit_1', label: 'Reserve exit context I', start_seconds: 1140, end_seconds: 1200, timestamp_url: `${VIDEO_SOURCE_URL}&t=1140s` },
        { segment_id: 'reserve_exit_2', label: 'Reserve exit context II', start_seconds: 1560, end_seconds: 1620, timestamp_url: `${VIDEO_SOURCE_URL}&t=1560s` },
      ],
    },
    thresholds: {
      yellow: { spread_positive_bp: 0, positive_streak_observations: 3, reserve_usd_bn: 2900, reserve_change_4w_usd_bn: 0, tga_operational_floor_usd_bn: 950 },
      red: { spread_bp: 3, reserve_usd_bn: 2800, srf_positive_days_required: 2, srf_window_completed_days: 3 },
      extreme: { reserve_usd_bn: 2500, decline_percentile: 'TRAILING_5Y_P10' },
      tga_source_target_usd_bn: 1000,
    },
    operationalizations: {
      rapid_reserve_decline_rule: 'TRAILING_5Y_P10',
      exclude_technical_srf_exercises: true,
      srf_aggregate_same_day_operations: true,
    },
    crisis_context: { status: 'UNKNOWN', as_of: null, reviewed_at: null, reviewer: null, note: null },
    formulas: {
      yellow: { expression: 'PERSIST(S>0) ∧ R<2.9T ∧ ΔR4W<0 ∧ TGA≥0.95T', triggered: false, clauses: yellowClauses },
      red: {
        expression: '[(S>+3bp) ∧ R<2.8T] ∨ SRF↑', triggered: false, clauses: redClauses,
        routes: [
          { route_id: 'spread_and_reserves', label: 'Spread and reserves', expression: '(S>+3bp) ∧ R<2.8T', triggered: false, clauses: redClauses.slice(0, 2) },
          { route_id: 'srf_2_of_3', label: 'SRF 2-of-3', expression: 'SRF↑', triggered: false, clauses: redClauses.slice(2) },
        ],
      },
      extreme: { expression: 'R<2.5T ∧ RAPID_DECLINE ∧ NO_MAJOR_CRISIS', triggered: false, candidate: false, context_required: false, clauses: extremeClauses },
    },
    technical_flags: [],
    notes: ['This is a liquidity-source model, not a structural top or trading recommendation.'],
  };
}

export function makeManualEvidenceRecord(
  metricId: (typeof P3_MANUAL_IDS)[number] = 'ai_upstream_orders_backlog',
  overrides: Partial<ManualEvidenceRecord> = {},
): ManualEvidenceRecord {
  return {
    company_id: 'microsoft',
    period_end: '2026-06-30',
    metric_id: metricId,
    direction: 'DOWN',
    value: 0,
    unit: 'USD bn',
    yoy_pct: 0,
    comparable: true,
    source_type: '10-Q',
    source_url: 'https://www.sec.gov/Archives/edgar/data/789019/000078901926123456/msft-20260630.htm',
    filing_accession: '0000789019-26-123456',
    filing_accepted_at: '2026-07-30T20:15:00Z',
    as_of: '2026-08-01',
    reviewer: 'Release reviewer',
    reviewed_at: '2026-08-02T12:00:00Z',
    paraphrase: 'Comparable reviewed backlog disclosure moved down year over year.',
    review_note: 'Definition and period were checked against the linked public filing.',
    ...overrides,
  };
}

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

function fundamentalCompany(
  companyId: 'microsoft' | 'alphabet' | 'amazon' | 'meta',
  ticker: string,
  cik: string,
  cashCapex: number,
  yoyAcceleration: number,
  financeLease: number | null,
): FundamentalCompanyDetail {
  return {
    date: '2026-06-30',
    company_id: companyId,
    ticker,
    cik,
    fiscal_quarter: companyId === 'microsoft' ? 'FY2026Q4' : 'FY2026Q2',
    calendar_period_end: '2026-06-30',
    cash_capex_usd_bn: cashCapex,
    qoq_percent_change: 8.2,
    yoy_percent_change: 42.4,
    qoq_acceleration_pp: 3.1,
    yoy_acceleration_pp: yoyAcceleration,
    direction: yoyAcceleration > 0 ? 'ACCELERATING' : 'DECELERATING',
    tag: companyId === 'amazon' ? 'PaymentsToAcquireProductiveAssets' : 'PaymentsToAcquirePropertyPlantAndEquipment',
    namespace: 'us-gaap',
    unit: 'USD',
    accession: `${cik}-26-000001`,
    form: companyId === 'microsoft' ? '10-K' : '10-Q',
    filed_at: '2026-07-30',
    accepted_at: '2026-07-30T20:15:00Z',
    filing_url: `https://www.sec.gov/Archives/edgar/data/${Number(cik)}/${`${cik}-26-000001`.replaceAll('-', '')}/filing.htm`,
    frame: companyId === 'microsoft' ? 'CY2026Q2' : null,
    context_start: '2026-04-01',
    context_end: '2026-06-30',
    quarterization_method: companyId === 'microsoft' ? 'FY_MINUS_9M' : 'H1_MINUS_Q1',
    manual_review_required: false,
    finance_lease_additions_usd_bn: financeLease,
    finance_lease_tag: financeLease == null ? null : 'RightOfUseAssetObtainedInExchangeForFinanceLeaseLiability',
    finance_lease_accession: financeLease == null ? null : `${cik}-26-000001`,
    finance_lease_quarterization_method: financeLease == null ? null : companyId === 'microsoft' ? 'FY_MINUS_9M' : 'H1_MINUS_Q1',
  };
}

const FUNDAMENTAL_COMPANIES = [
  fundamentalCompany('microsoft', 'MSFT', '0000789019', 8.7, -3.2, 1.1),
  fundamentalCompany('alphabet', 'GOOGL', '0001652044', 10.2, 4.6, null),
  fundamentalCompany('amazon', 'AMZN', '0001018724', 12.4, -8.1, 2.5),
  fundamentalCompany('meta', 'META', '0001326801', 7.2, -1.4, null),
] satisfies FundamentalCompanyDetail[];

const FUNDAMENTAL_STATISTICS = {
  aggregate_cash_capex_usd_bn: 38.5,
  qoq_percent_change: 8.2,
  yoy_percent_change: 42.4,
  qoq_acceleration_pp: 3.1,
  yoy_acceleration_pp: -4.2,
  company_breadth: 3,
  company_total: 4,
  company_breadth_ratio: 0.75,
  finance_lease_disclosure_breadth: 2,
  manual_review_count: 0,
  quarter_count: 12,
};

const FUNDAMENTAL_DETAILS = {
  fundamental: {
    aggregate_direction: 'DECELERATING' as const,
    company_breadth: 3,
    company_total: 4 as const,
    companies: FUNDAMENTAL_COMPANIES,
    caveats: [
      'Cash CapEx is kept separate from equipment acquired through finance leases.',
      'Microsoft fiscal quarters do not align with calendar-year quarters.',
    ],
  },
};

const FUNDAMENTAL_SHORT_SERIES = Array.from({ length: 12 }, (_, index) => ({
  date: `${2023 + Math.floor((index + 2) / 4)}-${['03-31', '06-30', '09-30', '12-31'][(index + 2) % 4]}`,
  value: Number((22 + index * 1.5).toFixed(1)),
}));

export function makeSnapshot(metricOverrides: Record<string, Partial<Metric>> = {}): Snapshot {
  const ids = [...new Set([
    ...OVERVIEW_SERIES_IDS,
    ...CONFIRMATION_SPREAD_IDS,
    ...P1_CFTC_CONFIG.map(({ id }) => id),
    ...P1_RIGHTS_GATED_IDS,
    ...P2_ACTIVE_IDS,
    ...P2_HELD_IDS,
    ...P3_METRIC_IDS,
  ])];
  const metrics = Object.fromEntries(ids.map((id) => [id, makeMetric(id, metricOverrides[id])]));
  metrics.sofr_iorb_spread_bp = makeMetric('sofr_iorb_spread_bp', {
    value: 1,
    unit: 'bp',
    statistics: { latest: 1, positive_streak: 0 },
    ...metricOverrides.sofr_iorb_spread_bp,
  });
  metrics.reserve_balances = makeMetric('reserve_balances', {
    value: 3000,
    unit: 'USD bn',
    changes: { one_observation: -25, five_observations: -100, four_weeks: -100 },
    statistics: { latest: 3000, change_4w: -100, trailing_5y_p10: -200 },
    short_series: [{ date: '2026-08-04', value: 3025 }, { date: '2026-08-11', value: 3000 }],
    ...metricOverrides.reserve_balances,
  });
  metrics.tga_daily = makeMetric('tga_daily', {
    value: 997,
    unit: 'USD bn',
    short_series: [{ date: '2026-08-10', value: 980 }, { date: '2026-08-11', value: 997 }],
    ...metricOverrides.tga_daily,
  });
  const srfShortSeries = [
    { date: '2026-08-07', value: 0, accepted_amount_usd_bn: 0, alert_eligible_accepted_amount_usd_bn: 0, exercise_accepted_amount_usd_bn: 0, has_technical_exercise: false, technical_exercise: false, classification_complete: true as const },
    { date: '2026-08-08', value: 0, accepted_amount_usd_bn: 0, alert_eligible_accepted_amount_usd_bn: 0, exercise_accepted_amount_usd_bn: 0, has_technical_exercise: false, technical_exercise: false, classification_complete: true as const },
    { date: '2026-08-11', value: 0, accepted_amount_usd_bn: 0, alert_eligible_accepted_amount_usd_bn: 0, exercise_accepted_amount_usd_bn: 0, has_technical_exercise: false, technical_exercise: false, classification_complete: true as const },
  ];
  metrics.srf_accepted = makeMetric('srf_accepted', {
    value: 0,
    unit: 'USD bn',
    statistics: { sample_size: 3, positive_nontechnical_latest_3: 0, nontechnical_positive_use_streak: 0 },
    short_series: srfShortSeries,
    ...metricOverrides.srf_accepted,
  });
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
  metrics.hyperscaler_aggregate_cash_capex = makeMetric('hyperscaler_aggregate_cash_capex', {
    label: 'Hyperscaler aggregate cash CapEx',
    availability: 'ACTIVE_FREE',
    value: FUNDAMENTAL_STATISTICS.aggregate_cash_capex_usd_bn,
    unit: 'USD bn',
    frequency: 'quarterly',
    observation_date: '2026-06-30',
    released_at: '2026-07-30T20:15:00Z',
    expected_next_update: null,
    changes: { one_observation: 2.9, five_observations: 11.5, one_quarter: 2.9 },
    statistics: { ...FUNDAMENTAL_STATISTICS },
    quality: { status: 'OK', freshness: 'FRESH', last_attempt_at: NOW, last_success_at: NOW, failure_reason: null, sample_size: 12 },
    context: { technical_flags: [], is_proxy: false, confidence: 'MEDIUM', direction: 'DECELERATING' },
    source: { source_id: 'sec_edgar', name: 'SEC Company Facts and filings', url: 'https://data.sec.gov/api/xbrl/companyfacts/', tier: 'OFFICIAL', retrieved_at: NOW, rights_note: 'Official public-company filing data with accession-level provenance.' },
    details: FUNDAMENTAL_DETAILS,
    short_series: FUNDAMENTAL_SHORT_SERIES,
    ...metricOverrides.hyperscaler_aggregate_cash_capex,
  });
  metrics.hyperscaler_aggregate_cash_capex.provenance = [
    { ...metrics.hyperscaler_aggregate_cash_capex.source },
  ];
  metrics.hyperscaler_aggregate_cash_capex.unavailability_reason = null;
  metrics.hyperscaler_aggregate_cash_capex_yoy_acceleration_pp = makeMetric('hyperscaler_aggregate_cash_capex_yoy_acceleration_pp', {
    ...metrics.hyperscaler_aggregate_cash_capex,
    metric_id: 'hyperscaler_aggregate_cash_capex_yoy_acceleration_pp',
    label: 'Hyperscaler aggregate cash CapEx YoY acceleration',
    value: FUNDAMENTAL_STATISTICS.yoy_acceleration_pp,
    unit: 'percentage_points',
    changes: { ...metrics.hyperscaler_aggregate_cash_capex.changes },
    statistics: { ...FUNDAMENTAL_STATISTICS },
    quality: { ...metrics.hyperscaler_aggregate_cash_capex.quality, sample_size: 7 },
    context: { ...metrics.hyperscaler_aggregate_cash_capex.context, technical_flags: [] },
    source: { ...metrics.hyperscaler_aggregate_cash_capex.source },
    details: {
      fundamental: {
        ...FUNDAMENTAL_DETAILS.fundamental,
        companies: FUNDAMENTAL_DETAILS.fundamental.companies.map((company) => ({ ...company })),
        caveats: [...FUNDAMENTAL_DETAILS.fundamental.caveats],
      },
    },
    short_series: FUNDAMENTAL_SHORT_SERIES.map((point) => ({ ...point, value: FUNDAMENTAL_STATISTICS.yoy_acceleration_pp })),
    ...metricOverrides.hyperscaler_aggregate_cash_capex_yoy_acceleration_pp,
  });
  metrics.hyperscaler_aggregate_cash_capex_yoy_acceleration_pp.provenance = [
    { ...metrics.hyperscaler_aggregate_cash_capex_yoy_acceleration_pp.source },
  ];
  metrics.hyperscaler_aggregate_cash_capex_yoy_acceleration_pp.unavailability_reason = null;
  P3_MANUAL_IDS.forEach((id) => {
    const reason = 'Non-standard public-filing disclosure requires a reviewed manual row.';
    metrics[id] = makeMetric(id, {
      availability: 'MANUAL_READY',
      value: null,
      unit: 'mixed',
      frequency: 'quarterly',
      observation_date: null,
      released_at: null,
      updated_at: null,
      expected_next_update: null,
      changes: {
        one_observation: null,
        five_observations: null,
        twenty_observations: null,
        eight_weeks: null,
        twelve_weeks: null,
        one_quarter: null,
      },
      statistics: {},
      quality: { status: 'NOT_APPLICABLE', freshness: 'UNKNOWN', last_attempt_at: null, last_success_at: null, failure_reason: reason, sample_size: null },
      context: { technical_flags: [], is_proxy: false, confidence: 'UNKNOWN', direction: 'UNKNOWN' },
      source: { source_id: 'manual_public_filings', name: 'Manual public-filing review interface', url: null, tier: 'MANUAL', retrieved_at: null, rights_note: reason },
      methodology: { ...makeMetric(id).methodology, calculation: `${reason} Reviewed CSV rows must retain filing provenance.`, source_and_license_note: reason },
      short_series: [],
      ...metricOverrides[id],
    });
    metrics[id].provenance = [{ ...metrics[id].source }];
    metrics[id].unavailability_reason = reason;
  });
  const evidence = (prefix: string) => [{ id: `${prefix}-1`, label: 'Evidence 1', available: true, triggered: null, status: 'OK', direction: 'FLAT', confidence: 'HIGH', summary: '有新鮮資料。' }];
  const p1Evidence = [
    { id: 'volatility_term_structure', label: 'Volatility term structure', available: false, triggered: null, status: 'UNAVAILABLE_FREE', direction: 'UNKNOWN', confidence: 'UNKNOWN', summary: rightsReasons.vix_vix3m_term_structure_proxy },
    { id: 'trend_positioning', label: 'Trend / positioning', available: true, triggered: null, status: 'MIXED', direction: 'MIXED', confidence: 'LOW', summary: '四條 CFTC TFF series 新鮮；合約同類別方向混合。' },
    { id: 'options_tail_risk', label: 'Options / tail-risk proxy', available: false, triggered: null, status: 'UNAVAILABLE_FREE', direction: 'UNKNOWN', confidence: 'UNKNOWN', summary: rightsReasons.cboe_skew_tail_risk_proxy },
    { id: 'crypto_cross_asset', label: 'Crypto funding / cross-asset', available: false, triggered: null, status: 'UNAVAILABLE_FREE', direction: 'UNKNOWN', confidence: 'UNKNOWN', summary: rightsReasons.crypto_funding_btc },
  ];
  const p3Evidence = [
    { id: 'aggregate_capex_acceleration', label: 'Aggregate CapEx acceleration', available: true, triggered: null, status: 'DECELERATING', direction: 'DECELERATING', confidence: 'MEDIUM', summary: 'YoY growth remains positive, while YoY acceleration is negative.' },
    { id: 'orders_backlog', label: 'Orders / backlog', available: false, triggered: null, status: 'MANUAL_READY', direction: 'UNKNOWN', confidence: 'UNKNOWN', summary: 'No reviewed manual filing row is published.' },
    { id: 'prepayments_commitments', label: 'Prepayments / commitments', available: false, triggered: null, status: 'MANUAL_READY', direction: 'UNKNOWN', confidence: 'UNKNOWN', summary: 'No reviewed prepayments or take-or-pay row is published.' },
    { id: 'company_breadth', label: 'Company breadth', available: true, triggered: null, status: 'MIXED', direction: 'MIXED', confidence: 'MEDIUM', summary: 'Four of four companies have comparable cash CapEx quarters; directions are mixed.' },
  ];
  const macro = metrics.nonfinancial_equities_gdp_proxy;
  const form4 = metrics.sec_form4_nonderivative_ps_count_ratio_20d;
  const collectorSource = (collectorId: string, name: string) => ({
    collector_id: collectorId,
    name,
    url: `https://example.com/${collectorId}`,
    tier: 'OFFICIAL',
    rights_note: 'Public official data.',
    status: 'OK' as const,
    freshness: 'FRESH' as const,
    observation_date: '2026-08-11',
    released_at: '2026-08-12T12:00:00Z',
    updated_at: NOW,
    last_attempt_at: NOW,
    last_success_at: NOW,
    expected_next_update: '2026-08-13',
    failure_reason: null,
  });
  return {
    schema_version: SCHEMA_VERSION,
    generated_at: NOW,
    pipeline_updated_at: NOW,
    market_date: '2026-08-11',
    overall_assessment: 'NEUTRAL',
    switches: {
      liquidity_fuel: { mode: 'ACTIVE', assessment: 'NEUTRAL', available_blocks: 4, total_blocks: 4, confidence: 'HIGH', evidence_blocks: evidence('p0'), summary: 'P0 完整。' },
      market_ignition: { mode: 'EVIDENCE_ONLY', assessment: null, available_blocks: 1, total_blocks: 4, confidence: 'LOW', evidence_blocks: p1Evidence, summary: '只展示 evidence coverage、方向同信心；不設綜合嚴重度。' },
      fundamental_exit: { mode: 'EVIDENCE_ONLY', assessment: null, available_blocks: 2, total_blocks: 4, confidence: 'LOW', evidence_blocks: p3Evidence, summary: '只展示 CapEx 同人工 filing evidence coverage、方向及信心；不設綜合嚴重度。' },
    },
    metrics,
    technical_context: [],
    alerts: [],
    explanations: {
      headline: '美元流動性保持中性。',
      bullets: [{ metric_id: 'sofr_iorb_spread_bp', observation: '最新為 1 bp。', meaning: '融資成本略高。', alternative: '可能係結算日。', confirmation: '其他利差平穩。', judgment: '未足以證明壓力。', confidence: 'HIGH' }],
    },
    source_health: { ok: 11, stale: 0, error: 0, not_released_yet: 0, not_applicable: 0 },
    decision_models: { p0_video_liquidity: makeVideoP0Model(metrics) },
    sources: {
      nyfed_rates: collectorSource('nyfed_rates', 'New York Fed rates'),
      fred_iorb: collectorSource('fred_iorb', 'FRED IORB'),
      fred_h41: collectorSource('fred_h41', 'Federal Reserve H.4.1'),
      treasury_tga: collectorSource('treasury_tga', 'Treasury General Account'),
      nyfed_on_rrp: collectorSource('nyfed_on_rrp', 'New York Fed ON RRP'),
      nyfed_srf: collectorSource('nyfed_srf', 'New York Fed SRF'),
      treasury_auctions: collectorSource('treasury_auctions', 'Treasury auctions'),
      cftc_tff_futures_only: {
        collector_id: 'cftc_tff_futures_only',
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
      sec_companyfacts_capex: {
        collector_id: 'sec_companyfacts_capex',
        name: 'SEC Company Facts and filings',
        url: 'https://data.sec.gov/api/xbrl/companyfacts/',
        tier: 'OFFICIAL',
        rights_note: 'Official public-company filing data with accession-level provenance.',
        status: 'OK', freshness: 'FRESH', observation_date: '2026-06-30',
        released_at: '2026-07-30T20:15:00Z', updated_at: NOW,
        last_attempt_at: NOW, last_success_at: NOW,
        expected_next_update: null, failure_reason: null,
      },
    },
    active_free_count: Object.values(metrics).filter((metric) => metric.availability === 'ACTIVE_FREE').length,
    active_proxy_count: Object.values(metrics).filter((metric) => metric.availability === 'ACTIVE_PROXY').length,
    manual_ready_count: Object.values(metrics).filter((metric) => metric.availability === 'MANUAL_READY').length,
    unavailable_free_count: Object.values(metrics).filter((metric) => metric.availability === 'UNAVAILABLE_FREE').length,
    stale_count: 0,
  };
}

export function makeSnapshotWithReviewedManualEvidence(
  metricId: (typeof P3_MANUAL_IDS)[number] = 'ai_upstream_orders_backlog',
  recordOverrides: Partial<ManualEvidenceRecord> = {},
): Snapshot {
  const snapshot = makeSnapshot();
  const record = makeManualEvidenceRecord(metricId, recordOverrides);
  const metric = snapshot.metrics[metricId];
  metric.availability = 'ACTIVE_FREE';
  metric.observation_date = record.as_of;
  metric.released_at = record.filing_accepted_at;
  metric.updated_at = record.reviewed_at;
  metric.quality = { status: 'OK', freshness: 'FRESH', last_attempt_at: record.reviewed_at, last_success_at: record.reviewed_at, failure_reason: null, sample_size: 1 };
  metric.context = { technical_flags: [], is_proxy: false, confidence: 'MEDIUM', direction: record.direction };
  metric.statistics = { record_count: 1, company_count: 1, comparable_count: record.comparable ? 1 : 0 };
  metric.source = { source_id: 'manual_public_filings', name: 'Reviewed public filing', url: record.source_url, tier: 'MANUAL_REVIEWED', retrieved_at: record.reviewed_at, rights_note: 'Human-reviewed public filing with short paraphrase.' };
  metric.provenance = [{ ...metric.source }];
  metric.details = {
    manual_evidence: {
      source_id: 'manual_public_filings',
      network_enabled: false,
      observation_date: record.as_of,
      direction: record.direction,
      record_count: 1,
      company_count: 1,
      comparable_count: record.comparable ? 1 : 0,
      latest_filing_accepted_at: record.filing_accepted_at,
      latest_reviewed_at: record.reviewed_at,
      records: [record],
    },
  };
  metric.short_series = [{ date: record.as_of, value: null }];
  snapshot.active_free_count += 1;
  snapshot.manual_ready_count -= 1;
  const blockIndex = metricId === 'ai_upstream_orders_backlog' ? 1 : 2;
  snapshot.switches.fundamental_exit.evidence_blocks[blockIndex] = {
    ...snapshot.switches.fundamental_exit.evidence_blocks[blockIndex],
    available: true,
    status: record.direction,
    direction: record.direction,
    confidence: 'MEDIUM',
    summary: 'Reviewed public-filing evidence is available.',
  };
  snapshot.switches.fundamental_exit.available_blocks = 3;
  snapshot.switches.fundamental_exit.confidence = 'MEDIUM';
  return snapshot;
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
    ...P3_AUTOMATED_IDS.map((id) => ({ ...catalogMetric(id, 'fundamental_exit', 'P3', 'ACTIVE_FREE'), unit: id.endsWith('_pp') ? 'percentage_points' : 'USD bn', frequency: 'quarterly' })),
    ...P3_MANUAL_IDS.map((id) => ({ ...catalogMetric(id, 'fundamental_exit', 'P3', 'MANUAL_READY'), unit: 'mixed', frequency: 'quarterly' })),
  ];
}

function LIQUIDITY_IDS() {
  return [...new Set([...OVERVIEW_SERIES_IDS, ...CONFIRMATION_SPREAD_IDS])];
}

export function makeSeriesFile(metric: Metric): SeriesFile {
  const fundamental = metric.details?.fundamental;
  const manual = metric.details?.manual_evidence;
  const observations = P3_AUTOMATED_IDS.includes(metric.metric_id as (typeof P3_AUTOMATED_IDS)[number]) && fundamental
    ? metric.short_series.map((point) => {
        const aggregate = metric.metric_id === P3_AUTOMATED_IDS[0]
          ? point.value : metric.statistics.aggregate_cash_capex_usd_bn;
        const scale = (aggregate ?? 0) / (metric.statistics.aggregate_cash_capex_usd_bn ?? 1);
        return {
        ...point,
        aggregate_cash_capex_usd_bn: aggregate,
        qoq_percent_change: metric.statistics.qoq_percent_change,
        yoy_percent_change: metric.statistics.yoy_percent_change,
        qoq_acceleration_pp: metric.statistics.qoq_acceleration_pp,
        yoy_acceleration_pp: metric.statistics.yoy_acceleration_pp,
        aggregate_direction: fundamental.aggregate_direction,
        company_breadth: fundamental.company_breadth,
        company_total: fundamental.company_total,
        company_breadth_ratio: metric.statistics.company_breadth_ratio,
        finance_lease_disclosure_breadth: metric.statistics.finance_lease_disclosure_breadth ?? 0,
        manual_review_count: metric.statistics.manual_review_count ?? 0,
        companies: fundamental.companies.map((company) => ({
          ...company, cash_capex_usd_bn: Number((company.cash_capex_usd_bn * scale).toFixed(6)),
          date: point.date, calendar_period_end: point.date, context_start: point.date, context_end: point.date,
        })),
      };
      })
    : manual
      ? [...new Set(manual.records.map(({ as_of }) => as_of))].map((date) => {
          const records = manual.records.filter(({ as_of }) => as_of === date);
          const directions = records.map(({ direction }) => direction);
          return {
            date,
            value: null,
            direction: directions.includes('UNKNOWN') ? 'UNKNOWN' : new Set(directions).size === 1 ? directions[0] : 'MIXED',
            record_count: records.length,
            company_count: new Set(records.map(({ company_id }) => company_id)).size,
            comparable_count: records.filter(({ comparable }) => comparable).length,
            records,
          };
        })
      : metric.short_series;
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
    observations,
  };
}

export function jsonResponse(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } });
}
