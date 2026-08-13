import type {
  Availability,
  CatalogMetric,
  CollectorSource,
  EvidenceBlock,
  FundamentalCompanyDetail,
  FundamentalDirection,
  FundamentalMetricDetail,
  FundamentalSeriesPoint,
  Freshness,
  HealthStatus,
  Layer,
  Methodology,
  Metric,
  MetricContext,
  ManualDirection,
  ManualEvidenceDetail,
  ManualEvidenceRecord,
  ManualEvidenceSeriesPoint,
  MetricSource,
  Phase,
  Point,
  QualityInfo,
  Snapshot,
  SourceHealthCounts,
  SwitchState,
} from './types';

export type RouteId = 'overview' | 'liquidity-fuel' | 'market-ignition' | 'fundamental-exit' | 'provenance';
export type RangeKey = '1M' | '8W' | '12W' | '3M' | '1Y' | 'MAX';

export interface SeriesFile {
  schema_version: '2.0.0';
  metric_id: string;
  label: string;
  unit: string;
  frequency: string;
  availability: Availability;
  quality: QualityInfo;
  observation_date: string | null;
  released_at: string | null;
  updated_at: string | null;
  source: MetricSource;
  observations: Point[];
}

export type SeriesMap = Record<string, SeriesFile>;

export interface DashboardCore {
  snapshot: Snapshot;
  catalog: CatalogMetric[];
  catalogError: string | null;
}

export interface RouteSeriesResult {
  series: SeriesMap;
  errors: Record<string, string>;
}

export interface OverlayUnion {
  dates: string[];
  values: Record<string, Array<number | null>>;
}

export interface ChangePresentation {
  label: '1 OBS' | '1W' | '1M' | '1Q';
  value: number | null;
}

export const SCHEMA_VERSION = '2.0.0' as const;
export const THRESHOLD_BP = 3;

export const ROUTES = [
  { id: 'overview', href: '#/overview', label: '總覽' },
  { id: 'liquidity-fuel', href: '#/liquidity-fuel', label: '流動性燃料' },
  { id: 'market-ignition', href: '#/market-ignition', label: '市場引信' },
  { id: 'fundamental-exit', href: '#/fundamental-exit', label: '基本面逃生門' },
  { id: 'provenance', href: '#/provenance', label: '來源與方法' },
] as const satisfies ReadonlyArray<{ id: RouteId; href: string; label: string }>;

export const SWITCH_CONFIG = [
  { id: 'liquidity_fuel', route: 'liquidity-fuel', num: '01', kicker: 'LIQUIDITY FUEL', title: '流動性燃料' },
  { id: 'market_ignition', route: 'market-ignition', num: '02', kicker: 'MARKET IGNITION', title: '市場引信' },
  { id: 'fundamental_exit', route: 'fundamental-exit', num: '03', kicker: 'FUNDAMENTAL EXIT', title: '基本面逃生門' },
] as const;

export const RANGE_DAYS: Record<RangeKey, number> = {
  '1M': 31,
  '8W': 56,
  '12W': 84,
  '3M': 93,
  '1Y': 366,
  MAX: 100_000,
};

export const TAPE_GROUPS = [
  {
    label: 'DAILY · 隔夜價格與流量',
    ids: [
      'sofr_iorb_spread_bp', 'sofr', 'iorb', 'effr', 'obfr', 'tgcr', 'bgcr',
      'tga_daily', 'on_rrp_accepted', 'srf_accepted',
    ],
  },
  {
    label: 'WEEKLY · Fed 資產負債表',
    ids: ['reserve_balances', 'fed_total_assets', 'tga_weekly_h41'],
  },
] as const;

export const TICKERS: Readonly<Record<string, string>> = {
  sofr_iorb_spread_bp: 'SOFR−IORB',
  sofr: 'SOFR',
  iorb: 'IORB',
  effr: 'EFFR',
  obfr: 'OBFR',
  tgcr: 'TGCR',
  bgcr: 'BGCR',
  tga_daily: 'TGA · DAILY',
  on_rrp_accepted: 'ON RRP',
  srf_accepted: 'SRF',
  reserve_balances: 'RESERVES',
  fed_total_assets: 'WALCL',
  tga_weekly_h41: 'TGA · H.4.1',
};

export const OVERVIEW_MAIN_TABS = [
  { id: 'sofr_iorb_spread_bp', label: 'SOFR−IORB' },
  { id: 'sofr', label: 'SOFR' },
  { id: 'iorb', label: 'IORB' },
  { id: 'effr', label: 'EFFR' },
  { id: 'tga_daily', label: 'TGA' },
  { id: 'reserve_balances', label: 'RESERVES' },
  { id: 'fed_total_assets', label: 'WALCL' },
] as const;

export const CONFIRMATION_SPREAD_IDS = [
  'sofr_iorb_spread_bp',
  'effr_iorb_spread_bp',
  'obfr_iorb_spread_bp',
  'tgcr_iorb_spread_bp',
  'bgcr_iorb_spread_bp',
] as const;

export const LIQUIDITY_MAIN_TABS = [
  { id: 'sofr_iorb_spread_bp', label: 'SOFR−IORB' },
  { id: 'effr_iorb_spread_bp', label: 'EFFR−IORB' },
  { id: 'obfr_iorb_spread_bp', label: 'OBFR−IORB' },
  { id: 'tgcr_iorb_spread_bp', label: 'TGCR−IORB' },
  { id: 'bgcr_iorb_spread_bp', label: 'BGCR−IORB' },
  { id: 'on_rrp_accepted', label: 'ON RRP' },
  { id: 'srf_accepted', label: 'SRF' },
  { id: 'reserve_balances', label: 'RESERVES' },
] as const;

export const P1_CFTC_CONFIG = [
  {
    id: 'cftc_e_mini_sp500_asset_manager_net_pct_oi',
    contract: 'E-MINI S&P 500',
    category: 'ASSET MANAGER / INSTITUTIONAL',
    availability: 'ACTIVE_FREE',
  },
  {
    id: 'cftc_e_mini_sp500_leveraged_funds_net_pct_oi',
    contract: 'E-MINI S&P 500',
    category: 'LEVERAGED FUNDS · PROXY',
    availability: 'ACTIVE_PROXY',
  },
  {
    id: 'cftc_nasdaq100_consolidated_asset_manager_net_pct_oi',
    contract: 'NASDAQ-100 CONSOLIDATED',
    category: 'ASSET MANAGER / INSTITUTIONAL',
    availability: 'ACTIVE_FREE',
  },
  {
    id: 'cftc_nasdaq100_consolidated_leveraged_funds_net_pct_oi',
    contract: 'NASDAQ-100 CONSOLIDATED',
    category: 'LEVERAGED FUNDS · PROXY',
    availability: 'ACTIVE_PROXY',
  },
] as const;

export const P1_RIGHTS_GATED_IDS = [
  'vix_vix3m_term_structure_proxy',
  'cboe_skew_tail_risk_proxy',
  'crypto_funding_btc',
  'crypto_funding_eth',
  'trend_following_positioning_proxy',
  'cross_asset_correlation',
] as const;

export const P1_EVIDENCE_BLOCK_IDS = [
  'volatility_term_structure',
  'trend_positioning',
  'options_tail_risk',
  'crypto_cross_asset',
] as const;

export const P2_ACTIVE_IDS = [
  'nonfinancial_equities_gdp_proxy',
  'sec_form4_nonderivative_ps_count_ratio_20d',
] as const;

export const P2_HELD_IDS = [
  'finra_margin_debt',
  'spy_holdings_top10_weight_proxy',
  'spx_0dte_share',
  'ndx_forward_pe',
  'm2_nasdaq_divergence',
  'gamma_flip',
] as const;

export const P2_SERIES_IDS = [...P2_ACTIVE_IDS, ...P2_HELD_IDS] as const;

export const P3_AUTOMATED_IDS = [
  'hyperscaler_aggregate_cash_capex',
  'hyperscaler_aggregate_cash_capex_yoy_acceleration_pp',
] as const;

export const P3_MANUAL_IDS = [
  'ai_upstream_orders_backlog',
  'customer_prepayments_contract_commitments',
  'take_or_pay_commitments',
] as const;

export const P3_METRIC_IDS = [...P3_AUTOMATED_IDS, ...P3_MANUAL_IDS] as const;

export const P3_EVIDENCE_BLOCK_IDS = [
  'aggregate_capex_acceleration',
  'orders_backlog',
  'prepayments_commitments',
  'company_breadth',
] as const;

export const COLLECTOR_SOURCE_IDS = [
  'nyfed_rates',
  'fred_iorb',
  'fred_h41',
  'treasury_tga',
  'nyfed_on_rrp',
  'nyfed_srf',
  'treasury_auctions',
  'cftc_tff_futures_only',
  'fred_nonfinancial_equities_gdp',
  'sec_form4_daily_index',
  'sec_companyfacts_capex',
] as const;

const P1_DIRECTIONS = new Set(['MORE_NET_LONG', 'MORE_NET_SHORT', 'FLAT', 'MIXED', 'UNKNOWN']);
const EVIDENCE_CONFIDENCE = new Set(['HIGH', 'MEDIUM', 'LOW', 'UNKNOWN']);
const FUNDAMENTAL_DIRECTIONS = new Set<FundamentalDirection>(['ACCELERATING', 'DECELERATING', 'FLAT', 'UNKNOWN']);
const MANUAL_DIRECTIONS = new Set<ManualDirection>(['UP', 'FLAT', 'DOWN', 'MIXED', 'UNKNOWN']);
const MANUAL_RECORD_DIRECTIONS = new Set(['UP', 'FLAT', 'DOWN', 'UNKNOWN']);
const MANUAL_SOURCE_TYPES = new Set(['10-Q', '10-Q/A', '10-K', '10-K/A', '8-K', '8-K/A', 'DEF 14A']);
const MANUAL_VALUE_UNITS = new Set([
  'USD', 'USD mn', 'USD bn', 'count', 'units', 'percent', 'percentage_points', 'ratio', 'MW', 'GW',
]);
const P3_COMPANIES = {
  microsoft: { ticker: 'MSFT', cik: '0000789019', cashTag: 'PaymentsToAcquirePropertyPlantAndEquipment' },
  alphabet: { ticker: 'GOOGL', cik: '0001652044', cashTag: 'PaymentsToAcquirePropertyPlantAndEquipment' },
  amazon: { ticker: 'AMZN', cik: '0001018724', cashTag: 'PaymentsToAcquireProductiveAssets' },
  meta: { ticker: 'META', cik: '0001326801', cashTag: 'PaymentsToAcquirePropertyPlantAndEquipment' },
} as const;
const P3_SWITCH_DIRECTIONS = new Set<string>([...FUNDAMENTAL_DIRECTIONS, ...MANUAL_DIRECTIONS]);
const HEALTH_RANK: Readonly<Record<HealthStatus, number>> = {
  NOT_APPLICABLE: -1,
  OK: 0,
  NOT_RELEASED_YET: 1,
  STALE: 2,
  ERROR: 3,
};
const FRESHNESS_RANK: Readonly<Record<Freshness, number>> = {
  FRESH: 0,
  LATE: 1,
  STALE: 2,
  UNKNOWN: 3,
};

export const OVERVIEW_SERIES_IDS = TAPE_GROUPS.flatMap(({ ids }) => [...ids]);
export const LIQUIDITY_SERIES_IDS = [...new Set([
  ...OVERVIEW_SERIES_IDS,
  ...CONFIRMATION_SPREAD_IDS,
])];

export const DEFAULT_OVERLAY: Readonly<Record<string, boolean>> = {
  sofr: true,
  iorb: true,
  effr: true,
  obfr: false,
  tgcr: false,
  bgcr: false,
};

export const AVAILABILITY_LABELS: Readonly<Record<Availability, string>> = {
  ACTIVE_FREE: '免費自動',
  ACTIVE_PROXY: '免費代理',
  MANUAL_READY: '可人工匯入',
  UNAVAILABLE_FREE: '免費數據不足',
};

export const HEALTH_LABELS: Readonly<Record<HealthStatus, string>> = {
  OK: '正常',
  STALE: '沿用最後成功值',
  ERROR: '抓取錯誤',
  NOT_RELEASED_YET: '尚未發布',
  NOT_APPLICABLE: '不適用',
};

export const FRESHNESS_LABELS: Readonly<Record<Freshness, string>> = {
  FRESH: '新鮮',
  LATE: '延遲',
  STALE: '過期',
  UNKNOWN: '未知',
};

const AVAILABILITIES = new Set<Availability>(['ACTIVE_FREE', 'ACTIVE_PROXY', 'MANUAL_READY', 'UNAVAILABLE_FREE']);
const HEALTH_STATUSES = new Set<HealthStatus>(['OK', 'STALE', 'ERROR', 'NOT_RELEASED_YET', 'NOT_APPLICABLE']);
const FRESHNESS_VALUES = new Set<Freshness>(['FRESH', 'LATE', 'STALE', 'UNKNOWN']);
const PHASES = new Set<Phase>(['P0', 'P1', 'P2', 'P3']);
const LAYERS = new Set<Layer>(['liquidity_fuel', 'market_ignition', 'fundamental_exit']);
const ISO_DAY = /^\d{4}-\d{2}-\d{2}$/;
const ISO_TIMESTAMP = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/;
const DAY_MS = 86_400_000;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value);
}

function isNonnegativeInteger(value: unknown): value is number {
  return isFiniteNumber(value) && Number.isInteger(value) && value >= 0;
}

function isNullableNumber(value: unknown): value is number | null {
  return value === null || isFiniteNumber(value);
}

function isNullableNonnegativeNumber(value: unknown): value is number | null {
  return value === null || (isFiniteNumber(value) && value >= 0);
}

function isNullableString(value: unknown): value is string | null {
  return value === null || typeof value === 'string';
}

function isIsoTimestamp(value: unknown): value is string {
  return typeof value === 'string' && ISO_TIMESTAMP.test(value) && Number.isFinite(Date.parse(value));
}

function isNullableUtcTimestamp(value: unknown): value is string | null {
  return value === null || (isIsoTimestamp(value) && value.endsWith('Z'));
}

export function isIsoDay(value: unknown): value is string {
  if (typeof value !== 'string' || !ISO_DAY.test(value)) return false;
  const timestamp = Date.parse(`${value}T00:00:00Z`);
  return Number.isFinite(timestamp) && new Date(timestamp).toISOString().slice(0, 10) === value;
}

function isNullableTimestamp(value: unknown): value is string | null {
  return value === null || isIsoTimestamp(value);
}

function isNullableDay(value: unknown): value is string | null {
  return value === null || isIsoDay(value);
}

function isPoint(value: unknown): value is Point {
  return isRecord(value) && isIsoDay(value.date) && isNullableNumber(value.value);
}

function isFundamentalDirection(value: unknown): value is FundamentalDirection {
  return typeof value === 'string' && FUNDAMENTAL_DIRECTIONS.has(value as FundamentalDirection);
}

function fundamentalDirectionFor(value: number | null): FundamentalDirection {
  if (value === null) return 'UNKNOWN';
  if (value > 0) return 'ACCELERATING';
  if (value < 0) return 'DECELERATING';
  return 'FLAT';
}

function isFundamentalCompany(value: unknown): value is FundamentalCompanyDetail {
  const exactKeys = [
    'date', 'company_id', 'ticker', 'cik', 'fiscal_quarter', 'calendar_period_end',
    'cash_capex_usd_bn', 'qoq_percent_change', 'yoy_percent_change',
    'qoq_acceleration_pp', 'yoy_acceleration_pp', 'direction', 'tag', 'namespace',
    'unit', 'accession', 'form', 'filed_at', 'accepted_at', 'filing_url', 'frame',
    'context_start', 'context_end', 'quarterization_method', 'manual_review_required',
    'finance_lease_additions_usd_bn', 'finance_lease_tag', 'finance_lease_accession',
    'finance_lease_quarterization_method',
  ];
  if (!isRecord(value) || Object.keys(value).length !== exactKeys.length ||
    !exactKeys.every((key) => Object.hasOwn(value, key)) || !isIsoDay(value.date) ||
    typeof value.company_id !== 'string' || typeof value.ticker !== 'string' ||
    typeof value.cik !== 'string' || typeof value.fiscal_quarter !== 'string' ||
    !isIsoDay(value.calendar_period_end) || !isFiniteNumber(value.cash_capex_usd_bn) || value.cash_capex_usd_bn < 0 ||
    !isNullableNumber(value.qoq_percent_change) || !isNullableNumber(value.yoy_percent_change) ||
    !isNullableNumber(value.qoq_acceleration_pp) || !isNullableNumber(value.yoy_acceleration_pp) ||
    !isFundamentalDirection(value.direction) ||
    typeof value.tag !== 'string' || typeof value.namespace !== 'string' || typeof value.unit !== 'string' ||
    typeof value.accession !== 'string' || !/^\d{10}-\d{2}-\d{6}$/.test(value.accession) ||
    typeof value.form !== 'string' || !['10-Q', '10-Q/A', '10-K', '10-K/A'].includes(value.form) ||
    !isIsoDay(value.filed_at) || !isIsoTimestamp(value.accepted_at) || !value.accepted_at.endsWith('Z') ||
    typeof value.filing_url !== 'string' ||
    !isNullableString(value.frame) || !isIsoDay(value.context_start) || !isIsoDay(value.context_end) ||
    typeof value.quarterization_method !== 'string' || typeof value.manual_review_required !== 'boolean' ||
    !isNullableNonnegativeNumber(value.finance_lease_additions_usd_bn) || !isNullableString(value.finance_lease_tag) ||
    !isNullableString(value.finance_lease_accession) || !isNullableString(value.finance_lease_quarterization_method)) return false;
  const company = P3_COMPANIES[value.company_id as keyof typeof P3_COMPANIES];
  const fiscalQuarter = /^FY\d{4}Q([1-4])$/.exec(value.fiscal_quarter);
  const quarterizationByQuarter: Record<string, string> = {
    '1': 'Q1_YTD', '2': 'H1_MINUS_Q1', '3': '9M_MINUS_H1', '4': 'FY_MINUS_9M',
  };
  const quarter = fiscalQuarter?.[1];
  const expectedQuarterization = quarter ? quarterizationByQuarter[quarter] : undefined;
  const expectedForms = quarter === '4' ? ['10-K', '10-K/A'] : ['10-Q', '10-Q/A'];
  const acceptedDay = value.accepted_at.slice(0, 10);
  return company !== undefined && value.ticker === company.ticker && value.cik === company.cik &&
    value.tag === company.cashTag && value.namespace === 'us-gaap' && value.unit === 'USD' &&
    fiscalQuarter !== null && expectedQuarterization !== undefined &&
    /^https:\/\/www\.sec\.gov\/Archives\/edgar\/data\//.test(value.filing_url) &&
    value.filing_url.replaceAll('-', '').includes(
      `/Archives/edgar/data/${Number(value.cik)}/${value.accession.replaceAll('-', '')}/`,
    ) &&
    value.quarterization_method === expectedQuarterization && expectedForms.includes(value.form) &&
    value.direction === fundamentalDirectionFor(value.yoy_acceleration_pp) &&
    value.filed_at >= value.context_end && acceptedDay >= value.context_end &&
    Math.abs(elapsedDays(value.filed_at, acceptedDay)) <= 1 &&
    (value.finance_lease_accession === null || /^\d{10}-\d{2}-\d{6}$/.test(value.finance_lease_accession)) &&
    (value.finance_lease_additions_usd_bn === null
      ? value.finance_lease_tag === null && value.finance_lease_accession === null && value.finance_lease_quarterization_method === null
      : value.finance_lease_tag === 'RightOfUseAssetObtainedInExchangeForFinanceLeaseLiability' &&
        value.finance_lease_accession === value.accession && value.finance_lease_quarterization_method !== null &&
        value.finance_lease_quarterization_method === expectedQuarterization) &&
    value.context_start <= value.context_end && value.context_end === value.calendar_period_end &&
    value.date === value.calendar_period_end;
}

function isFundamentalDetail(value: unknown): value is FundamentalMetricDetail {
  const exactKeys = ['aggregate_direction', 'company_breadth', 'company_total', 'companies', 'caveats'];
  if (!isRecord(value) || Object.keys(value).length !== exactKeys.length ||
    !exactKeys.every((key) => Object.hasOwn(value, key)) || !isFundamentalDirection(value.aggregate_direction) ||
    !isNonnegativeInteger(value.company_breadth) || value.company_total !== 4 ||
    !Array.isArray(value.companies) || !value.companies.every(isFundamentalCompany) ||
    !Array.isArray(value.caveats) || !value.caveats.every((item) => typeof item === 'string' && item.length > 0)) return false;
  const companies = value.companies as FundamentalCompanyDetail[];
  if (companies.length === 0) {
    return value.aggregate_direction === 'UNKNOWN' && value.company_breadth === 0;
  }
  const knownDirections = companies.filter(({ direction }) => direction !== 'UNKNOWN');
  const expectedBreadth = value.aggregate_direction === 'UNKNOWN' ? 0
    : knownDirections.filter(({ direction }) => direction === value.aggregate_direction).length;
  return value.company_breadth <= value.company_total && companies.length === value.company_total &&
    value.company_breadth === expectedBreadth &&
    new Set(companies.map(({ company_id }) => company_id)).size === companies.length;
}

function isFundamentalSeriesPoint(value: unknown): value is FundamentalSeriesPoint {
  if (!isPoint(value) || !isRecord(value) || !isNullableNonnegativeNumber(value.aggregate_cash_capex_usd_bn)) return false;
  if (!isNullableNumber(value.qoq_percent_change) || !isNullableNumber(value.yoy_percent_change) ||
    !isNullableNumber(value.qoq_acceleration_pp) || !isNullableNumber(value.yoy_acceleration_pp) ||
    !isFundamentalDirection(value.aggregate_direction) ||
    !isNonnegativeInteger(value.company_breadth) || value.company_total !== 4 ||
    !isNullableNumber(value.company_breadth_ratio) || !isNonnegativeInteger(value.finance_lease_disclosure_breadth) ||
    !isNonnegativeInteger(value.manual_review_count) || !Array.isArray(value.companies) ||
    !value.companies.every(isFundamentalCompany)) return false;
  const companies = value.companies as FundamentalCompanyDetail[];
  const knownDirections = companies.filter(({ direction }) => direction !== 'UNKNOWN');
  const expectedDirection = fundamentalDirectionFor(value.yoy_acceleration_pp);
  const expectedBreadth = expectedDirection === 'UNKNOWN' ? 0
    : knownDirections.filter(({ direction }) => direction === expectedDirection).length;
  const expectedBreadthRatio = expectedDirection === 'UNKNOWN' || !knownDirections.length
    ? null : expectedBreadth / knownDirections.length;
  const aggregate = companies.reduce((sum, company) => sum + company.cash_capex_usd_bn, 0);
  return companies.length === 4 && new Set(companies.map(({ company_id }) => company_id)).size === 4 &&
    companies.every(({ date, calendar_period_end }) => date === value.date && calendar_period_end === value.date) &&
    value.aggregate_cash_capex_usd_bn !== null && Math.abs(value.aggregate_cash_capex_usd_bn - aggregate) <= 0.00001 &&
    value.aggregate_direction === expectedDirection && value.company_breadth === expectedBreadth &&
    (expectedBreadthRatio === null ? value.company_breadth_ratio === null
      : value.company_breadth_ratio !== null && Math.abs(value.company_breadth_ratio - expectedBreadthRatio) <= 0.000001) &&
    value.finance_lease_disclosure_breadth === companies
      .filter(({ finance_lease_additions_usd_bn }) => finance_lease_additions_usd_bn !== null).length &&
    value.manual_review_count === companies.filter(({ manual_review_required }) => manual_review_required).length;
}

function isManualSourceUrl(value: unknown, companyId: string, accession: string): boolean {
  if (typeof value !== 'string') return false;
  try {
    const url = new URL(value);
    const cik = P3_COMPANIES[companyId as keyof typeof P3_COMPANIES]?.cik;
    if (!cik || url.protocol !== 'https:' || url.hostname !== 'www.sec.gov' || url.port ||
      url.username || url.password || url.search || url.hash) return false;
    const accessionDigits = accession.replaceAll('-', '');
    const expectedPrefix = `/Archives/edgar/data/${Number(cik)}/${accessionDigits}/`;
    const expectedUrlPrefix = `https://www.sec.gov${expectedPrefix}`;
    return value.startsWith(expectedUrlPrefix) &&
      /^[A-Za-z0-9._-]+\.html?$/.test(value.slice(expectedUrlPrefix.length));
  } catch {
    return false;
  }
}

function elapsedDays(start: string, end: string): number {
  return (Date.parse(`${end}T00:00:00Z`) - Date.parse(`${start}T00:00:00Z`)) / DAY_MS;
}

function newYorkDay(timestamp: string): string {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: 'America/New_York', year: 'numeric', month: '2-digit', day: '2-digit',
  }).formatToParts(new Date(timestamp));
  const values = Object.fromEntries(parts.map(({ type, value }) => [type, value]));
  return `${values.year}-${values.month}-${values.day}`;
}

function isManualEvidenceRecord(value: unknown): value is ManualEvidenceRecord {
  const exactKeys = [
    'company_id', 'period_end', 'metric_id', 'direction', 'value', 'unit', 'yoy_pct',
    'comparable', 'source_type', 'source_url', 'filing_accession', 'filing_accepted_at',
    'as_of', 'reviewer', 'reviewed_at', 'paraphrase', 'review_note',
  ];
  return isRecord(value) && Object.keys(value).length === exactKeys.length &&
    exactKeys.every((key) => Object.hasOwn(value, key)) &&
    typeof value.company_id === 'string' && Object.hasOwn(P3_COMPANIES, value.company_id) &&
    isIsoDay(value.period_end) && (P3_MANUAL_IDS as readonly string[]).includes(String(value.metric_id)) &&
    typeof value.direction === 'string' && MANUAL_RECORD_DIRECTIONS.has(value.direction) &&
    isNullableNonnegativeNumber(value.value) && isNullableString(value.unit) && isNullableNumber(value.yoy_pct) &&
    typeof value.comparable === 'boolean' && typeof value.source_type === 'string' && MANUAL_SOURCE_TYPES.has(value.source_type) &&
    typeof value.filing_accession === 'string' && /^\d{10}-\d{2}-\d{6}$/.test(value.filing_accession) &&
    isIsoTimestamp(value.filing_accepted_at) && value.filing_accepted_at.endsWith('Z') && isIsoDay(value.as_of) &&
    typeof value.reviewer === 'string' && value.reviewer.length > 0 && value.reviewer.length <= 80 &&
    isIsoTimestamp(value.reviewed_at) && value.reviewed_at.endsWith('Z') &&
    typeof value.paraphrase === 'string' && value.paraphrase.length > 0 && value.paraphrase.length <= 280 &&
    typeof value.review_note === 'string' && value.review_note.length > 0 && value.review_note.length <= 500 &&
    value.period_end <= value.filing_accepted_at.slice(0, 10) && value.filing_accepted_at.slice(0, 10) <= value.as_of &&
    value.filing_accepted_at <= value.reviewed_at && value.as_of <= value.reviewed_at.slice(0, 10) &&
    isManualSourceUrl(value.source_url, value.company_id, value.filing_accession) &&
    ((value.value === null && value.unit === null) ||
      (value.value !== null && typeof value.unit === 'string' && MANUAL_VALUE_UNITS.has(value.unit))) &&
    (value.comparable || value.yoy_pct === null);
}

function manualAggregateDirection(records: readonly ManualEvidenceRecord[]): ManualDirection {
  const latestByCompany = new Map<string, ManualEvidenceRecord>();
  for (const record of records.filter(({ comparable }) => comparable)) {
    const current = latestByCompany.get(record.company_id);
    const key = `${record.as_of}\0${record.reviewed_at}\0${record.period_end}\0${record.filing_accepted_at}\0${record.filing_accession}`;
    const currentKey = current
      ? `${current.as_of}\0${current.reviewed_at}\0${current.period_end}\0${current.filing_accepted_at}\0${current.filing_accession}`
      : '';
    if (!current || key > currentKey) latestByCompany.set(record.company_id, record);
  }
  const directions = [...latestByCompany.values()].map(({ direction }) => direction);
  if (!directions.length) return 'UNKNOWN';
  if (directions.some((direction) => direction === 'UNKNOWN')) return 'UNKNOWN';
  return new Set(directions).size === 1 ? directions[0] : 'MIXED';
}

function commonP3Direction(directions: readonly string[]): string {
  if (!directions.length || directions.some((direction) => direction === 'UNKNOWN')) return 'UNKNOWN';
  return new Set(directions).size === 1 ? directions[0] : 'MIXED';
}

function isManualEvidenceDetail(value: unknown): value is ManualEvidenceDetail {
  const exactKeys = [
    'source_id', 'network_enabled', 'observation_date', 'direction', 'record_count',
    'company_count', 'comparable_count', 'latest_filing_accepted_at',
    'latest_reviewed_at', 'records',
  ];
  if (!isRecord(value) || Object.keys(value).length !== exactKeys.length ||
    !exactKeys.every((key) => Object.hasOwn(value, key)) ||
    value.source_id !== 'manual_public_filings' || value.network_enabled !== false ||
    !isIsoDay(value.observation_date) || !isIsoTimestamp(value.latest_filing_accepted_at) ||
    !value.latest_filing_accepted_at.endsWith('Z') || !isIsoTimestamp(value.latest_reviewed_at) ||
    !value.latest_reviewed_at.endsWith('Z') || !isNonnegativeInteger(value.record_count) ||
    !isNonnegativeInteger(value.company_count) || !isNonnegativeInteger(value.comparable_count) ||
    typeof value.direction !== 'string' || !MANUAL_DIRECTIONS.has(value.direction as ManualDirection) ||
    !Array.isArray(value.records) ||
    !value.records.every(isManualEvidenceRecord)) return false;
  const records = value.records as ManualEvidenceRecord[];
  const observationDate = value.observation_date as string;
  if (!records.length) return false;
  const latestAsOf = records.reduce((latest, record) => record.as_of > latest ? record.as_of : latest, records[0].as_of);
  const latestAccepted = records.reduce((latest, record) => record.filing_accepted_at > latest ? record.filing_accepted_at : latest, records[0].filing_accepted_at);
  const latestReviewed = records.reduce((latest, record) => record.reviewed_at > latest ? record.reviewed_at : latest, records[0].reviewed_at);
  return value.record_count === records.length &&
    value.record_count <= 4 && value.company_count === records.length &&
    value.company_count === new Set(records.map(({ company_id }) => company_id)).size &&
    value.comparable_count === records.filter(({ comparable }) => comparable).length &&
    records.every(({ as_of }) => as_of <= observationDate && elapsedDays(as_of, observationDate) <= 120) &&
    observationDate === latestAsOf && value.latest_filing_accepted_at === latestAccepted &&
    value.latest_reviewed_at === latestReviewed && value.direction === manualAggregateDirection(records);
}

function isManualEvidenceSeriesPoint(value: unknown): value is ManualEvidenceSeriesPoint {
  if (!isPoint(value) || !isRecord(value) || value.value !== null ||
    !isNonnegativeInteger(value.record_count) || !isNonnegativeInteger(value.company_count) ||
    !isNonnegativeInteger(value.comparable_count) || typeof value.direction !== 'string' ||
    !MANUAL_DIRECTIONS.has(value.direction as ManualDirection) || !Array.isArray(value.records) ||
    !value.records.every(isManualEvidenceRecord)) return false;
  const records = value.records as ManualEvidenceRecord[];
  return records.length > 0 && value.record_count === records.length && value.record_count <= 4 &&
    value.company_count === records.length &&
    value.company_count === new Set(records.map(({ company_id }) => company_id)).size &&
    value.comparable_count === records.filter(({ comparable }) => comparable).length &&
    records.every(({ as_of }) => as_of <= value.date && elapsedDays(as_of, value.date) <= 120) &&
    value.direction === manualAggregateDirection(records);
}

function isAvailability(value: unknown): value is Availability {
  return typeof value === 'string' && AVAILABILITIES.has(value as Availability);
}

function isHealthStatus(value: unknown): value is HealthStatus {
  return typeof value === 'string' && HEALTH_STATUSES.has(value as HealthStatus);
}

function isFreshness(value: unknown): value is Freshness {
  return typeof value === 'string' && FRESHNESS_VALUES.has(value as Freshness);
}

function isQuality(value: unknown): value is QualityInfo {
  return isRecord(value) && isHealthStatus(value.status) && isFreshness(value.freshness) &&
    isNullableUtcTimestamp(value.last_attempt_at) && isNullableTimestamp(value.last_success_at) &&
    isNullableString(value.failure_reason) &&
    (value.sample_size === null || isNonnegativeInteger(value.sample_size));
}

function isStatistics(value: unknown): value is Record<string, number | null> {
  return isRecord(value) && Object.values(value).every(isNullableNumber);
}

function isContext(value: unknown): value is MetricContext {
  if (!isRecord(value) || !Array.isArray(value.technical_flags) ||
    !value.technical_flags.every((flag) => typeof flag === 'string') ||
    typeof value.is_proxy !== 'boolean' || typeof value.confidence !== 'string' ||
    (value.direction !== undefined && typeof value.direction !== 'string')) return false;
  const nullableText = [
    'equity_observation_date', 'gdp_observation_date', 'common_quarter',
    'window_start_5d', 'window_end_5d', 'window_start_20d', 'window_end_20d',
    'dollar_status_5d', 'dollar_status_20d', 'ex_10b5_scope',
  ];
  return nullableText.every((key) => value[key] === undefined || isNullableString(value[key]));
}

function p1Direction(change: number | null | undefined): string {
  if (change === null || change === undefined) return 'UNKNOWN';
  if (change > 0) return 'MORE_NET_LONG';
  if (change < 0) return 'MORE_NET_SHORT';
  return 'FLAT';
}

const P2_MACRO_STATISTICS = [
  'equity_usd_bn',
  'gdp_usd_bn',
  'qoq_percent_change',
  'yoy_percent_change',
  'percentile_10y',
  'percentile_10y_sample_size',
] as const;

const P2_FORM4_STATISTICS = [
  'ratio_5d',
  'count_ratio_20d',
  'purchase_count_5d',
  'sale_count_5d',
  'purchase_count_20d',
  'sale_count_20d',
  'dollar_ratio_5d',
  'dollar_ratio_20d',
  'dollar_coverage_rate_5d',
  'dollar_coverage_rate_20d',
  'ex_explicit_false_count_ratio_5d',
  'ex_explicit_false_count_ratio_20d',
  'ex_explicit_false_coverage_5d',
  'ex_explicit_false_coverage_20d',
  'eligible_transaction_count_20d',
  'priced_transaction_count_20d',
  'unique_accessions_20d',
  'unique_issuers_20d',
  'filings_processed_20d',
  'form4_count_20d',
  'form4a_count_20d',
  'amendments_linked_20d',
  'amendments_review_count_20d',
  'parse_failures_20d',
  'tenb5_true_filings_20d',
  'tenb5_false_filings_20d',
  'tenb5_unknown_filings_20d',
] as const;

const P2_FORM4_COUNT_STATISTICS = [
  'purchase_count_5d', 'sale_count_5d', 'purchase_count_20d', 'sale_count_20d',
  'eligible_transaction_count_20d', 'priced_transaction_count_20d',
  'unique_accessions_20d', 'unique_issuers_20d', 'filings_processed_20d',
  'form4_count_20d', 'form4a_count_20d', 'amendments_linked_20d',
  'amendments_review_count_20d', 'parse_failures_20d', 'tenb5_true_filings_20d',
  'tenb5_false_filings_20d', 'tenb5_unknown_filings_20d',
] as const;

const P2_FORM4_COVERAGE_STATISTICS = [
  'dollar_coverage_rate_5d', 'dollar_coverage_rate_20d',
  'ex_explicit_false_coverage_5d', 'ex_explicit_false_coverage_20d',
] as const;

function hasStatistics(metric: Metric, keys: readonly string[]): boolean {
  return keys.every((key) => Object.hasOwn(metric.statistics, key));
}

function isP2MetricContract(metrics: Record<string, unknown>): boolean {
  if ([...P2_ACTIVE_IDS, ...P2_HELD_IDS].some((id) => !isMetric(metrics[id], id))) return false;
  if (['buffett_indicator_proxy', 'insider_buy_sell_proxy', 'insider_ratio_proxy']
    .some((legacyId) => Object.hasOwn(metrics, legacyId))) return false;

  const macro = metrics.nonfinancial_equities_gdp_proxy as Metric;
  if (macro.availability !== 'ACTIVE_PROXY' || macro.unit !== 'percent' ||
    !macro.frequency.toLowerCase().includes('quarter') ||
    !Object.hasOwn(macro.changes, 'one_quarter') || !hasStatistics(macro, P2_MACRO_STATISTICS) ||
    (macro.statistics.percentile_10y_sample_size !== null &&
      !isNonnegativeInteger(macro.statistics.percentile_10y_sample_size)) ||
    (macro.statistics.percentile_10y !== null &&
      (macro.statistics.percentile_10y < 0 || macro.statistics.percentile_10y > 100)) ||
    !Object.hasOwn(macro.context, 'equity_observation_date') ||
    !Object.hasOwn(macro.context, 'gdp_observation_date') ||
    !Object.hasOwn(macro.context, 'common_quarter') ||
    (macro.context.equity_observation_date !== null && !isIsoDay(macro.context.equity_observation_date)) ||
    (macro.context.gdp_observation_date !== null && !isIsoDay(macro.context.gdp_observation_date)) ||
    (macro.value !== null && (macro.context.equity_observation_date === null ||
      macro.context.gdp_observation_date === null || !macro.context.common_quarter))) return false;

  const form4 = metrics.sec_form4_nonderivative_ps_count_ratio_20d as Metric;
  if (form4.availability !== 'ACTIVE_PROXY' || form4.unit !== 'ratio' ||
    !form4.frequency.toLowerCase().includes('business') ||
    !hasStatistics(form4, P2_FORM4_STATISTICS) ||
    form4.value !== form4.statistics.count_ratio_20d ||
    P2_FORM4_COUNT_STATISTICS.some((key) => form4.statistics[key] !== null &&
      !isNonnegativeInteger(form4.statistics[key])) ||
    P2_FORM4_COVERAGE_STATISTICS.some((key) => form4.statistics[key] !== null &&
      ((form4.statistics[key] as number) < 0 || (form4.statistics[key] as number) > 1)) ||
    !['window_start_5d', 'window_end_5d', 'window_start_20d', 'window_end_20d',
      'dollar_status_5d', 'dollar_status_20d', 'ex_10b5_scope']
      .every((key) => Object.hasOwn(form4.context, key)) ||
    form4.context.ex_10b5_scope !== 'EXPLICIT_FALSE_ONLY' ||
    ['window_start_5d', 'window_end_5d', 'window_start_20d', 'window_end_20d']
      .some((key) => form4.context[key as keyof MetricContext] !== null &&
        !isIsoDay(form4.context[key as keyof MetricContext])) ||
    (form4.value !== null && (!form4.context.window_end_20d || !form4.context.window_start_20d))) return false;
  for (const window of ['5d', '20d'] as const) {
    const ratio = form4.statistics[`dollar_ratio_${window}`];
    const coverage = form4.statistics[`dollar_coverage_rate_${window}`];
    if (ratio !== null && (coverage === null || coverage < 0.8)) return false;
  }

  return P2_HELD_IDS.every((id) => {
    const metric = metrics[id] as Metric;
    return metric.availability === 'UNAVAILABLE_FREE' && metric.value === null &&
      metric.short_series.length === 0 && metric.quality.status === 'NOT_APPLICABLE' &&
      metric.quality.freshness === 'UNKNOWN' && metric.observation_date === null &&
      metric.released_at === null && metric.updated_at === null &&
      metric.expected_next_update === null && metric.quality.last_attempt_at === null &&
      metric.quality.last_success_at === null && metric.source.source_id === null &&
      metric.source.retrieved_at === null && Boolean(metric.quality.failure_reason ||
        metric.source.rights_note || metric.methodology.source_and_license_note);
  });
}

const P3_AUTOMATED_STATISTICS = [
  'aggregate_cash_capex_usd_bn',
  'qoq_percent_change',
  'yoy_percent_change',
  'qoq_acceleration_pp',
  'yoy_acceleration_pp',
  'company_breadth',
  'company_total',
  'company_breadth_ratio',
  'finance_lease_disclosure_breadth',
  'manual_review_count',
  'quarter_count',
] as const;

const P3_COUNT_STATISTICS = [
  'company_breadth', 'company_total', 'finance_lease_disclosure_breadth',
  'manual_review_count', 'quarter_count',
] as const;

const P3_SWITCH_FIELDS = [
  'mode', 'assessment', 'available_blocks', 'total_blocks', 'confidence',
  'summary', 'evidence_blocks',
] as const;

const P3_EVIDENCE_BLOCK_FIELDS = [
  'id', 'label', 'available', 'triggered', 'status', 'summary', 'direction', 'confidence',
] as const;

const P3_METRIC_BASE_FIELDS = [
  'metric_id', 'label', 'availability', 'value', 'unit', 'frequency',
  'observation_date', 'released_at', 'updated_at', 'expected_next_update',
  'changes', 'statistics', 'quality', 'context', 'source', 'methodology',
  'short_series', 'provenance', 'unavailability_reason',
] as const;

const P3_MANUAL_CHANGE_FIELDS = [
  'one_observation', 'five_observations', 'twenty_observations',
  'eight_weeks', 'twelve_weeks', 'one_quarter',
] as const;

function hasExactFields(value: unknown, fields: readonly string[]): value is Record<string, unknown> {
  return isRecord(value) && Object.keys(value).length === fields.length &&
    fields.every((field) => Object.hasOwn(value, field));
}

function hasExactP3Provenance(metric: Metric): boolean {
  if (!Array.isArray(metric.provenance) || metric.provenance.length !== 1 ||
    !isMetricSource(metric.provenance[0])) return false;
  const source = metric.source as unknown as Record<string, unknown>;
  const provenance = metric.provenance[0] as unknown as Record<string, unknown>;
  const sourceFields = Object.keys(source);
  return Object.keys(provenance).length === sourceFields.length &&
    sourceFields.every((field) => Object.hasOwn(provenance, field) && provenance[field] === source[field]);
}

function hasNullManualChanges(metric: Metric): boolean {
  return hasExactFields(metric.changes, P3_MANUAL_CHANGE_FIELDS) &&
    P3_MANUAL_CHANGE_FIELDS.every((field) => metric.changes[field] === null);
}

function isP3MetricContract(metrics: Record<string, unknown>, generatedAt: string): boolean {
  if (P3_METRIC_IDS.some((id) => !isMetric(metrics[id], id))) return false;
  if (['hyperscaler_capex', 'capex_acceleration', 'upstream_backlog', 'prepayments', 'take_or_pay']
    .some((legacyId) => Object.hasOwn(metrics, legacyId))) return false;

  const capex = metrics.hyperscaler_aggregate_cash_capex as Metric;
  const acceleration = metrics.hyperscaler_aggregate_cash_capex_yoy_acceleration_pp as Metric;
  if (![capex, acceleration].every((metric) =>
    hasExactFields(metric, [...P3_METRIC_BASE_FIELDS, 'details']) && hasExactP3Provenance(metric)) ||
    capex.availability !== 'ACTIVE_FREE' || acceleration.availability !== 'ACTIVE_FREE' ||
    capex.unit !== 'USD bn' || acceleration.unit !== 'percentage_points' ||
    capex.frequency !== 'quarterly' || acceleration.frequency !== 'quarterly' ||
    capex.expected_next_update !== null || acceleration.expected_next_update !== null ||
    capex.context.technical_flags.length !== 0 || acceleration.context.technical_flags.length !== 0) return false;

  for (const metric of [capex, acceleration]) {
    const detail = metric.details?.fundamental;
    const knownDirectionCount = detail?.companies.filter(({ direction }) => direction !== 'UNKNOWN').length ?? 0;
    const expectedBreadthRatio = detail && detail.aggregate_direction !== 'UNKNOWN' && knownDirectionCount
      ? detail.company_breadth / knownDirectionCount
      : null;
    if (Object.keys(metric.statistics).length !== P3_AUTOMATED_STATISTICS.length ||
      !hasStatistics(metric, P3_AUTOMATED_STATISTICS) || !metric.details ||
      Object.keys(metric.details).length !== 1 || !detail || !isFundamentalDetail(detail) ||
      detail.companies.some(({ date, calendar_period_end }) =>
        date !== metric.observation_date || calendar_period_end !== metric.observation_date) ||
      detail.companies.some(({ accepted_at }) => Date.parse(accepted_at) > Date.parse(generatedAt)) ||
      metric.source.source_id !== 'sec_edgar' || metric.context.direction !== detail.aggregate_direction ||
      P3_COUNT_STATISTICS.some((key) => metric.statistics[key] !== null &&
        !isNonnegativeInteger(metric.statistics[key])) ||
      (metric.statistics.company_breadth !== null && metric.statistics.company_breadth > 4) ||
      (metric.statistics.company_breadth_ratio !== null &&
        (metric.statistics.company_breadth_ratio < 0 || metric.statistics.company_breadth_ratio > 1))) return false;
    if (metric.value !== null) {
      if (metric.statistics.company_total !== 4 || detail.companies.length !== 4 ||
        detail.company_breadth !== metric.statistics.company_breadth ||
        detail.company_total !== metric.statistics.company_total ||
        (expectedBreadthRatio === null
          ? metric.statistics.company_breadth_ratio !== null
          : metric.statistics.company_breadth_ratio === null ||
            Math.abs(metric.statistics.company_breadth_ratio - expectedBreadthRatio) > 0.000001) ||
        metric.statistics.finance_lease_disclosure_breadth !== detail.companies
          .filter(({ finance_lease_additions_usd_bn }) => finance_lease_additions_usd_bn !== null).length ||
        metric.statistics.manual_review_count !== detail.companies
          .filter(({ manual_review_required }) => manual_review_required).length ||
        metric.quality.sample_size === null || metric.statistics.quarter_count === null ||
        metric.statistics.quarter_count < 12 || metric.short_series.length < 12) return false;
    } else if (metric.short_series.length !== 0 || detail.aggregate_direction !== 'UNKNOWN' ||
      detail.company_breadth !== 0 || detail.companies.length !== 0 ||
      metric.quality.status === 'OK' || metric.context.direction !== 'UNKNOWN' ||
      metric.statistics.quarter_count !== 0 || P3_AUTOMATED_STATISTICS
        .filter((key) => key !== 'quarter_count').some((key) => metric.statistics[key] !== null)) return false;
  }
  const capexDates = capex.short_series.map(({ date }) => date);
  const accelerationDates = acceleration.short_series.map(({ date }) => date);
  const capexLatest = capex.short_series.at(-1);
  const accelerationLatest = acceleration.short_series.at(-1);
  const atomicQualityFields: Array<keyof QualityInfo> = [
    'status', 'freshness', 'last_attempt_at', 'last_success_at', 'failure_reason',
  ];
  if (capex.value !== capex.statistics.aggregate_cash_capex_usd_bn ||
    acceleration.value !== acceleration.statistics.yoy_acceleration_pp ||
    P3_AUTOMATED_STATISTICS.some((key) => capex.statistics[key] !== acceleration.statistics[key]) ||
    JSON.stringify(capex.details) !== JSON.stringify(acceleration.details) ||
    capex.observation_date !== acceleration.observation_date ||
    capex.released_at !== acceleration.released_at || capex.updated_at !== acceleration.updated_at ||
    atomicQualityFields.some((key) => capex.quality[key] !== acceleration.quality[key]) ||
    capex.context.confidence !== acceleration.context.confidence ||
    capex.context.is_proxy !== false || acceleration.context.is_proxy !== false ||
    JSON.stringify(capexDates) !== JSON.stringify(accelerationDates) ||
    (capexLatest !== undefined && (capexLatest.date !== capex.observation_date || capexLatest.value !== capex.value)) ||
    (accelerationLatest !== undefined &&
      (accelerationLatest.date !== acceleration.observation_date || accelerationLatest.value !== acceleration.value))) return false;

  return P3_MANUAL_IDS.every((id) => {
    const metric = metrics[id] as Metric;
    if (metric.unit !== 'mixed' || metric.frequency !== 'quarterly' || metric.context.technical_flags.length !== 0 ||
      metric.value !== null || metric.source.source_id !== 'manual_public_filings' ||
      metric.expected_next_update !== null || !hasExactP3Provenance(metric) || !hasNullManualChanges(metric)) return false;
    const manual = metric.details?.manual_evidence;
    if (manual !== undefined && (!isManualEvidenceDetail(manual) ||
      manual.records.some((record) => record.metric_id !== id))) return false;
    if (metric.availability === 'MANUAL_READY') {
      return hasExactFields(metric, P3_METRIC_BASE_FIELDS) && metric.details === undefined &&
        metric.quality.status === 'NOT_APPLICABLE' &&
        metric.quality.freshness === 'UNKNOWN' && metric.observation_date === null &&
        metric.released_at === null && metric.updated_at === null && metric.expected_next_update === null &&
        metric.quality.last_attempt_at === null && metric.quality.last_success_at === null &&
        metric.source.retrieved_at === null && metric.context.direction === 'UNKNOWN' &&
        metric.context.confidence === 'UNKNOWN' && Object.keys(metric.statistics).length === 0 &&
        metric.short_series.length === 0 && manual === undefined;
    }
    const ageDays = manual === undefined ? null : elapsedDays(manual.observation_date, newYorkDay(generatedAt));
    const expectedQuality = ageDays !== null && ageDays > 120
      ? { status: 'STALE', freshness: 'STALE' }
      : { status: 'OK', freshness: 'FRESH' };
    const validQuality = ageDays !== null && ageDays >= 0 &&
      metric.quality.status === expectedQuality.status && metric.quality.freshness === expectedQuality.freshness;
    const manualStatisticKeys = ['record_count', 'company_count', 'comparable_count'];
    const manualDates = metric.short_series.map(({ date }) => date);
    return metric.availability === 'ACTIVE_FREE' &&
      hasExactFields(metric, [...P3_METRIC_BASE_FIELDS, 'details']) && validQuality &&
      metric.details !== undefined && metric.details !== null && Object.keys(metric.details).length === 1 &&
      manual !== undefined && manual.record_count > 0 && metric.observation_date === manual.observation_date &&
      metric.context.direction === manual.direction && metric.quality.sample_size === manual.record_count &&
      metric.context.confidence === (metric.quality.status === 'OK' ? 'MEDIUM' : 'UNKNOWN') &&
      metric.released_at === manual.latest_filing_accepted_at && metric.updated_at === manual.latest_reviewed_at &&
      metric.quality.last_attempt_at === manual.latest_reviewed_at &&
      metric.quality.last_success_at === manual.latest_reviewed_at && metric.source.retrieved_at === manual.latest_reviewed_at &&
      metric.expected_next_update === null && metric.short_series.length > 0 &&
      metric.short_series.every(({ value }) => value === null) && new Set(manualDates).size === manualDates.length &&
      manualDates.every((date, index) => index === 0 || manualDates[index - 1] < date) &&
      manualDates.at(-1) === metric.observation_date && Object.keys(metric.statistics).length === manualStatisticKeys.length &&
      manualStatisticKeys.every((key) => Object.hasOwn(metric.statistics, key)) &&
      metric.statistics.record_count === manual.record_count && metric.statistics.company_count === manual.company_count &&
      metric.statistics.comparable_count === manual.comparable_count;
  });
}

function maxNullableString(values: Array<string | null>): string | null {
  return values.reduce<string | null>((latest, current) =>
    current !== null && (latest === null || current > latest) ? current : latest, null);
}

function isMetricSource(value: unknown): value is MetricSource {
  return isRecord(value) && (value.source_id === undefined || isNullableString(value.source_id)) &&
    isNullableString(value.name) && isNullableString(value.url) &&
    isNullableString(value.tier) && isNullableTimestamp(value.retrieved_at) &&
    typeof value.rights_note === 'string';
}

function isMethodology(value: unknown): value is Methodology {
  if (!isRecord(value)) return false;
  const text = [
    'question', 'definition', 'why_it_matters', 'direction', 'calculation',
    'frequency_and_lag', 'common_misreads', 'technical_distortions', 'cannot_infer',
    'source_and_license_note', 'proxy_disclosure',
  ];
  return text.every((field) => typeof value[field] === 'string') &&
    Array.isArray(value.confirm_with) && value.confirm_with.every((item) => typeof item === 'string');
}

function isChanges(value: unknown): boolean {
  if (!isRecord(value) || !isNullableNumber(value.one_observation) || !isNullableNumber(value.five_observations)) return false;
  return ['twenty_observations', 'one_week', 'four_weeks', 'one_month', 'one_quarter', 'eight_weeks', 'twelve_weeks']
    .every((key) => value[key] === undefined || isNullableNumber(value[key]));
}

function isMetric(value: unknown, id?: string): value is Metric {
  return isRecord(value) && typeof value.metric_id === 'string' && (!id || value.metric_id === id) &&
    typeof value.label === 'string' && isAvailability(value.availability) &&
    isNullableNumber(value.value) && typeof value.unit === 'string' && typeof value.frequency === 'string' &&
    isNullableDay(value.observation_date) && isNullableTimestamp(value.released_at) &&
    isNullableTimestamp(value.updated_at) && isNullableDay(value.expected_next_update) &&
    isChanges(value.changes) && isStatistics(value.statistics) &&
    isQuality(value.quality) && isContext(value.context) &&
    isMetricSource(value.source) && isMethodology(value.methodology) &&
    Array.isArray(value.short_series) && value.short_series.every(isPoint) &&
    (value.details === undefined || value.details === null || isRecord(value.details));
}

function isEvidenceBlock(value: unknown): value is EvidenceBlock {
  return isRecord(value) && typeof value.id === 'string' && typeof value.label === 'string' &&
    typeof value.available === 'boolean' && (value.triggered === null || typeof value.triggered === 'boolean') &&
    typeof value.status === 'string' && typeof value.direction === 'string' &&
    typeof value.confidence === 'string' && typeof value.summary === 'string';
}

function isSwitch(value: unknown): value is SwitchState {
  return isRecord(value) && typeof value.mode === 'string' && isNullableString(value.assessment) &&
    isNonnegativeInteger(value.available_blocks) && isNonnegativeInteger(value.total_blocks) &&
    value.available_blocks <= value.total_blocks &&
    typeof value.confidence === 'string' && typeof value.summary === 'string' &&
    Array.isArray(value.evidence_blocks) && value.evidence_blocks.every(isEvidenceBlock);
}

function isCollectorSource(value: unknown): value is CollectorSource {
  return isRecord(value) && typeof value.collector_id === 'string' &&
    typeof value.name === 'string' && isNullableString(value.url) &&
    isNullableString(value.tier) && typeof value.rights_note === 'string' &&
    isHealthStatus(value.status) && isFreshness(value.freshness) &&
    isNullableDay(value.observation_date) && isNullableTimestamp(value.released_at) &&
    isNullableTimestamp(value.updated_at) && isNullableUtcTimestamp(value.last_attempt_at) &&
    isNullableTimestamp(value.last_success_at) &&
    isNullableDay(value.expected_next_update) && isNullableString(value.failure_reason);
}

function p2CollectorSourceMatches(
  source: CollectorSource | undefined,
  metric: Metric,
  collectorId: string,
  sourceId: string,
  generatedAt: string,
): boolean {
  if (!source) return false;
  const expectedUpdatedAt = metric.quality.last_attempt_at === generatedAt
    ? metric.quality.last_attempt_at
    : metric.updated_at;
  return source.collector_id === collectorId && metric.source.source_id === sourceId &&
    metric.source.retrieved_at === metric.quality.last_attempt_at &&
    source.name === metric.source.name && source.url === metric.source.url &&
    source.tier === metric.source.tier && source.rights_note === metric.source.rights_note &&
    source.status === metric.quality.status && source.freshness === metric.quality.freshness &&
    source.observation_date === metric.observation_date && source.released_at === metric.released_at &&
    source.updated_at === expectedUpdatedAt && source.last_success_at === metric.quality.last_success_at &&
    source.last_attempt_at === metric.quality.last_attempt_at &&
    source.expected_next_update === metric.expected_next_update &&
    source.failure_reason === metric.quality.failure_reason;
}

function isSourceHealth(value: unknown): value is SourceHealthCounts {
  return isRecord(value) && ['ok', 'stale', 'error', 'not_released_yet', 'not_applicable']
    .every((key) => isNonnegativeInteger(value[key]));
}

export function isSnapshot(value: unknown): value is Snapshot {
  if (!isRecord(value) || value.schema_version !== SCHEMA_VERSION ||
    !isIsoTimestamp(value.generated_at) || !isIsoTimestamp(value.pipeline_updated_at) ||
    !isNullableDay(value.market_date) || !isNullableString(value.overall_assessment) ||
    !isRecord(value.switches) || !isRecord(value.metrics) ||
    !isRecord(value.sources) || !isSourceHealth(value.source_health) ||
    !Array.isArray(value.technical_context) || !Array.isArray(value.alerts) || !isRecord(value.explanations)) return false;

  const switches = value.switches as Record<string, unknown>;
  const metrics = value.metrics as Record<string, unknown>;
  if (!(['liquidity_fuel', 'market_ignition', 'fundamental_exit'] as const)
    .every((id) => isSwitch(switches[id]))) return false;
  if (value.overall_assessment !== (switches.liquidity_fuel as SwitchState).assessment) return false;
  const marketIgnition = switches.market_ignition as SwitchState;
  if (marketIgnition.mode !== 'EVIDENCE_ONLY' || marketIgnition.assessment !== null ||
    marketIgnition.total_blocks !== P1_EVIDENCE_BLOCK_IDS.length ||
    marketIgnition.available_blocks !== marketIgnition.evidence_blocks.filter(({ available }) => available).length ||
    marketIgnition.evidence_blocks.length !== P1_EVIDENCE_BLOCK_IDS.length ||
    !P1_EVIDENCE_BLOCK_IDS.every((id, index) => marketIgnition.evidence_blocks[index]?.id === id) ||
    marketIgnition.evidence_blocks.some((block) => block.triggered !== null ||
      !P1_DIRECTIONS.has(block.direction) || !EVIDENCE_CONFIDENCE.has(block.confidence) ||
      (block.available === (block.direction === 'UNKNOWN')))) return false;
  const fundamentalExit = switches.fundamental_exit as SwitchState;
  if (!hasExactFields(fundamentalExit, P3_SWITCH_FIELDS) ||
    fundamentalExit.evidence_blocks.some((block) => !hasExactFields(block, P3_EVIDENCE_BLOCK_FIELDS)) ||
    fundamentalExit.mode !== 'EVIDENCE_ONLY' || fundamentalExit.assessment !== null ||
    fundamentalExit.total_blocks !== P3_EVIDENCE_BLOCK_IDS.length ||
    fundamentalExit.available_blocks !== fundamentalExit.evidence_blocks.filter(({ available }) => available).length ||
    fundamentalExit.evidence_blocks.length !== P3_EVIDENCE_BLOCK_IDS.length ||
    !P3_EVIDENCE_BLOCK_IDS.every((id, index) => fundamentalExit.evidence_blocks[index]?.id === id) ||
    fundamentalExit.evidence_blocks.some((block) => block.triggered !== null ||
      !EVIDENCE_CONFIDENCE.has(block.confidence) || !P3_SWITCH_DIRECTIONS.has(block.direction) ||
      (!block.available && block.direction !== 'UNKNOWN'))) return false;
  if (!Object.entries(metrics).every(([id, metric]) => isMetric(metric, id))) return false;
  if (![...OVERVIEW_SERIES_IDS, ...CONFIRMATION_SPREAD_IDS, ...P1_CFTC_CONFIG.map(({ id }) => id), ...P1_RIGHTS_GATED_IDS, ...P2_SERIES_IDS, ...P3_METRIC_IDS]
    .every((id) => isMetric(metrics[id], id))) return false;
  if (!isP2MetricContract(metrics)) return false;
  if (!isP3MetricContract(metrics, value.generated_at as string)) return false;
  const p3Capex = metrics[P3_AUTOMATED_IDS[0]] as Metric;
  const p3Acceleration = metrics[P3_AUTOMATED_IDS[1]] as Metric;
  const p3Fundamental = p3Capex.details?.fundamental;
  const p3AutomatedAvailable = Boolean(p3Fundamental) && [p3Capex, p3Acceleration].every((metric) =>
    metric.quality.status === 'OK' && metric.quality.freshness === 'FRESH' && metric.value !== null &&
    metric.statistics.quarter_count !== null && metric.statistics.quarter_count >= 12);
  const manualBlockState = (ids: readonly (typeof P3_MANUAL_IDS)[number][]) => {
    const active = ids.map((id) => metrics[id] as Metric)
      .filter(({ availability }) => availability === 'ACTIVE_FREE');
    if (!active.length) return { available: false, direction: 'UNKNOWN', status: 'MANUAL_READY' };
    if (!active.every(({ quality }) => quality.status === 'OK' && quality.freshness === 'FRESH')) {
      return { available: false, direction: 'UNKNOWN', status: 'STALE' };
    }
    const direction = commonP3Direction(active.map((metric) => metric.details!.manual_evidence!.direction));
    return { available: true, direction, status: direction };
  };
  const orders = manualBlockState(['ai_upstream_orders_backlog']);
  const commitments = manualBlockState([
    'customer_prepayments_contract_commitments', 'take_or_pay_commitments',
  ]);
  const p3ExpectedBlocks = [
    {
      available: p3AutomatedAvailable,
      direction: p3AutomatedAvailable ? p3Fundamental!.aggregate_direction : 'UNKNOWN',
      status: p3AutomatedAvailable ? p3Fundamental!.aggregate_direction : 'UNAVAILABLE',
    },
    orders,
    commitments,
    {
      available: p3AutomatedAvailable,
      direction: p3AutomatedAvailable ? commonP3Direction(p3Fundamental!.companies.map(({ direction }) => direction)) : 'UNKNOWN',
      status: p3AutomatedAvailable
        ? commonP3Direction(p3Fundamental!.companies.map(({ direction }) => direction)) : 'UNAVAILABLE',
    },
  ];
  if (fundamentalExit.evidence_blocks.some((block, index) =>
    block.available !== p3ExpectedBlocks[index].available || block.direction !== p3ExpectedBlocks[index].direction ||
    block.status !== p3ExpectedBlocks[index].status ||
    block.confidence !== (block.available ? 'MEDIUM' : 'UNKNOWN'))) return false;
  const expectedP3Coverage = p3ExpectedBlocks.filter(({ available }) => available).length;
  const expectedP3Confidence = expectedP3Coverage === 0 ? 'UNKNOWN' : expectedP3Coverage <= 2 ? 'LOW' : 'MEDIUM';
  if (fundamentalExit.available_blocks !== expectedP3Coverage ||
    fundamentalExit.confidence !== expectedP3Confidence) return false;
  if (P1_CFTC_CONFIG.some(({ id, availability }) => {
    const metric = metrics[id] as Metric;
    const requiredStatistics = [
      'net_position', 'net_percent_open_interest', 'change_8_weeks', 'change_12_weeks',
      'z_score_3_year', 'z_score_3_year_sample_size', 'open_interest', 'sample_size',
    ];
    return metric.availability !== availability || metric.unit !== 'percent_open_interest' ||
      !metric.frequency.toLowerCase().includes('week') ||
      !Object.hasOwn(metric.changes, 'eight_weeks') || !Object.hasOwn(metric.changes, 'twelve_weeks') ||
      requiredStatistics.some((name) => !Object.hasOwn(metric.statistics, name)) ||
      metric.statistics.sample_size !== metric.quality.sample_size ||
      metric.changes.eight_weeks !== metric.statistics.change_8_weeks ||
      metric.changes.twelve_weeks !== metric.statistics.change_12_weeks ||
      metric.context.direction !== p1Direction(metric.statistics.change_8_weeks);
  })) return false;
  if (P1_RIGHTS_GATED_IDS.some((id) => {
    const metric = metrics[id] as Metric;
    return metric.availability !== 'UNAVAILABLE_FREE' || metric.value !== null ||
      metric.short_series.length !== 0 || metric.quality.status !== 'NOT_APPLICABLE' ||
      metric.quality.freshness !== 'UNKNOWN';
  })) return false;
  const positioningBlock = marketIgnition.evidence_blocks[1];
  const cftcMetrics = P1_CFTC_CONFIG.map(({ id }) => metrics[id] as Metric);
  const cftcAlignedDate = cftcMetrics[0].observation_date;
  const cftcAvailable = cftcAlignedDate !== null && cftcMetrics.every((metric) =>
    metric.quality.status === 'OK' && metric.quality.freshness === 'FRESH' &&
    metric.value !== null && metric.observation_date === cftcAlignedDate &&
    metric.changes.eight_weeks !== null && metric.changes.eight_weeks !== undefined &&
    metric.changes.twelve_weeks !== null && metric.changes.twelve_weeks !== undefined &&
    metric.statistics.change_8_weeks !== null && metric.statistics.change_8_weeks !== undefined &&
    metric.statistics.change_12_weeks !== null && metric.statistics.change_12_weeks !== undefined &&
    metric.statistics.z_score_3_year !== null && metric.statistics.z_score_3_year !== undefined &&
    isNonnegativeInteger(metric.statistics.z_score_3_year_sample_size) &&
    metric.statistics.z_score_3_year_sample_size >= 156);
  const componentDirections = cftcMetrics.map((metric) => p1Direction(metric.statistics.change_8_weeks));
  const positioningDirection = cftcAvailable
    ? new Set(componentDirections).size === 1 ? componentDirections[0] : 'MIXED'
    : 'UNKNOWN';
  const positioningConfidence = cftcAvailable ? 'LOW' : 'UNKNOWN';
  if (positioningBlock.available !== cftcAvailable ||
    positioningBlock.direction !== positioningDirection ||
    positioningBlock.status !== (cftcAvailable ? positioningDirection : 'UNAVAILABLE_FREE') ||
    positioningBlock.confidence !== positioningConfidence ||
    marketIgnition.confidence !== positioningConfidence ||
    marketIgnition.evidence_blocks.some((block, index) => index !== 1 &&
      (block.available || block.status !== 'UNAVAILABLE_FREE' ||
        block.direction !== 'UNKNOWN' || block.confidence !== 'UNKNOWN'))) return false;
  const rawSources = value.sources as Record<string, unknown>;
  const sourceIds = Object.keys(rawSources);
  if (sourceIds.length !== COLLECTOR_SOURCE_IDS.length ||
    !COLLECTOR_SOURCE_IDS.every((id) => Object.hasOwn(rawSources, id)) ||
    !Object.entries(rawSources).every(([id, source]) => isCollectorSource(source) && source.collector_id === id)) return false;
  const sources = rawSources as Record<string, CollectorSource>;
  const cftcSource = sources.cftc_tff_futures_only;
  if (!cftcSource) return false;
  if (!p2CollectorSourceMatches(
    sources.fred_nonfinancial_equities_gdp,
    metrics.nonfinancial_equities_gdp_proxy as Metric,
    'fred_nonfinancial_equities_gdp',
    'fred_government',
    value.generated_at,
  ) || !p2CollectorSourceMatches(
    sources.sec_form4_daily_index,
    metrics.sec_form4_nonderivative_ps_count_ratio_20d as Metric,
    'sec_form4_daily_index',
    'sec_edgar',
    value.generated_at,
  ) || !p2CollectorSourceMatches(
    sources.sec_companyfacts_capex,
    metrics.hyperscaler_aggregate_cash_capex as Metric,
    'sec_companyfacts_capex',
    'sec_edgar',
    value.generated_at,
  )) return false;
  const expectedHealth = cftcMetrics.map(({ quality }) => quality.status)
    .reduce((worst, current) => HEALTH_RANK[current] > HEALTH_RANK[worst] ? current : worst);
  const expectedFreshness = cftcMetrics.map(({ quality }) => quality.freshness)
    .reduce((worst, current) => FRESHNESS_RANK[current] > FRESHNESS_RANK[worst] ? current : worst);
  if (cftcSource.status !== expectedHealth || cftcSource.freshness !== expectedFreshness ||
    cftcSource.observation_date !== maxNullableString(cftcMetrics.map(({ observation_date }) => observation_date)) ||
    cftcSource.released_at !== maxNullableString(cftcMetrics.map(({ released_at }) => released_at)) ||
    cftcSource.expected_next_update !== maxNullableString(cftcMetrics.map(({ expected_next_update }) => expected_next_update))) return false;
  const sourceHealth = value.source_health as SourceHealthCounts;
  const collectorStatusKeys: Record<HealthStatus, keyof SourceHealthCounts> = {
    OK: 'ok', STALE: 'stale', ERROR: 'error',
    NOT_RELEASED_YET: 'not_released_yet', NOT_APPLICABLE: 'not_applicable',
  };
  if ((Object.entries(collectorStatusKeys) as Array<[HealthStatus, keyof SourceHealthCounts]>).some(([status, key]) =>
    sourceHealth[key] !== Object.values(sources).filter((source) => source.status === status).length)) return false;
  if (!value.technical_context.every((item) => isRecord(item) && isIsoDay(item.date) &&
    Array.isArray(item.flags) && item.flags.every((flag) => typeof flag === 'string') && typeof item.note === 'string')) return false;
  if (!value.alerts.every((item) => isRecord(item) && typeof item.level === 'string' &&
    typeof item.title === 'string' && typeof item.detail === 'string')) return false;
  if (typeof value.explanations.headline !== 'string' || !Array.isArray(value.explanations.bullets) ||
    !value.explanations.bullets.every((item) => isRecord(item) &&
      ['metric_id', 'observation', 'meaning', 'alternative', 'confirmation', 'judgment', 'confidence']
        .every((key) => typeof item[key] === 'string'))) return false;
  const availabilityCounts: Array<[keyof Pick<Snapshot, 'active_free_count' | 'active_proxy_count' | 'manual_ready_count' | 'unavailable_free_count'>, Availability]> = [
    ['active_free_count', 'ACTIVE_FREE'], ['active_proxy_count', 'ACTIVE_PROXY'],
    ['manual_ready_count', 'MANUAL_READY'], ['unavailable_free_count', 'UNAVAILABLE_FREE'],
  ];
  if (availabilityCounts.some(([key, availability]) => !isNonnegativeInteger(value[key]) ||
    value[key] !== Object.values(metrics).filter((metric) => isMetric(metric) && metric.availability === availability).length)) return false;
  return isNonnegativeInteger(value.stale_count) && value.stale_count === Object.values(metrics)
    .filter((metric) => isMetric(metric) && metric.quality.status === 'STALE').length;
}

function isCatalogMetric(value: unknown): value is CatalogMetric {
  return isRecord(value) && typeof value.metric_id === 'string' && typeof value.label === 'string' &&
    typeof value.unit === 'string' && typeof value.frequency === 'string' &&
    typeof value.layer === 'string' && LAYERS.has(value.layer as Layer) &&
    typeof value.phase === 'string' && PHASES.has(value.phase as Phase) &&
    typeof value.role === 'string' && isAvailability(value.availability) &&
    typeof value.series_path === 'string' && value.series_path.startsWith('data/series/') &&
    !value.series_path.includes('..');
}

function isSeriesFile(value: unknown, id: string): value is SeriesFile {
  const valid = isRecord(value) && value.schema_version === SCHEMA_VERSION && value.metric_id === id &&
    typeof value.label === 'string' && typeof value.unit === 'string' && typeof value.frequency === 'string' &&
    isAvailability(value.availability) && isQuality(value.quality) &&
    isNullableDay(value.observation_date) && isNullableTimestamp(value.released_at) &&
    isNullableTimestamp(value.updated_at) && isMetricSource(value.source) &&
    Array.isArray(value.observations) && value.observations.every(isPoint);
  if (!valid) return false;
  const series = value as unknown as SeriesFile;
  if ((P3_AUTOMATED_IDS as readonly string[]).includes(id)) {
    const observations = series.observations as unknown[];
    if (series.availability !== 'ACTIVE_FREE' || series.source.source_id !== 'sec_edgar' ||
      !series.frequency.toLowerCase().includes('quarter') ||
      series.unit !== (id === P3_AUTOMATED_IDS[0] ? 'USD bn' : 'percentage_points')) return false;
    if (observations.length === 0) return series.quality.status !== 'OK' && series.observation_date === null;
    if (observations.length < 12 || !observations.every(isFundamentalSeriesPoint)) return false;
    const points = observations as FundamentalSeriesPoint[];
    if (new Set(points.map(({ date }) => date)).size !== points.length ||
      points.some(({ date }, index) => index > 0 && points[index - 1].date >= date) ||
      points.at(-1)?.date !== series.observation_date) return false;
    return points.every((point) => point.value === (id === P3_AUTOMATED_IDS[0]
      ? point.aggregate_cash_capex_usd_bn : point.yoy_acceleration_pp));
  }
  if ((P3_MANUAL_IDS as readonly string[]).includes(id)) {
    const observations = series.observations as unknown[];
    if (series.unit !== 'mixed' || !series.frequency.toLowerCase().includes('quarter') ||
      series.source.source_id !== 'manual_public_filings') return false;
    if (series.availability === 'MANUAL_READY') {
      return observations.length === 0 && series.quality.status === 'NOT_APPLICABLE' &&
        series.quality.freshness === 'UNKNOWN' && series.observation_date === null;
    }
    if (series.availability !== 'ACTIVE_FREE' || !observations.length ||
      !((series.quality.status === 'OK' && series.quality.freshness === 'FRESH') ||
        (series.quality.status === 'STALE' && series.quality.freshness === 'STALE')) ||
      !observations.every(isManualEvidenceSeriesPoint)) return false;
    const points = observations as ManualEvidenceSeriesPoint[];
    return new Set(points.map(({ date }) => date)).size === points.length &&
      points.every((point, index) => (index === 0 || points[index - 1].date < point.date) &&
        point.records.every((record) => record.metric_id === id)) &&
      points.at(-1)?.date === series.observation_date;
  }
  return true;
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function dataUrl(base: string, path: string): string {
  return `${base.endsWith('/') ? base : `${base}/`}${path}`;
}

async function fetchJson(url: string, fetcher: typeof fetch): Promise<unknown> {
  const response = await fetcher(url);
  if (!response.ok) throw new Error(`${response.status} ${response.statusText || 'request failed'}`);
  return response.json();
}

export function parseRoute(hash: string): RouteId {
  const candidate = hash.replace(/^#\/?/, '').replace(/\/$/, '');
  return ROUTES.some(({ id }) => id === candidate) ? candidate as RouteId : 'overview';
}

export function routeMetricIds(route: RouteId, catalog: readonly CatalogMetric[], snapshot: Snapshot): string[] {
  if (route === 'provenance') return [];
  const dynamic = route === 'market-ignition'
    ? [
        ...P1_CFTC_CONFIG.map(({ id }) => id),
        ...P1_RIGHTS_GATED_IDS,
        ...P2_SERIES_IDS,
        ...catalog.filter(({ layer }) => layer === 'market_ignition').map(({ metric_id }) => metric_id),
      ]
    : route === 'fundamental-exit'
      ? [
          ...P3_METRIC_IDS,
          ...catalog.filter(({ layer }) => layer === 'fundamental_exit').map(({ metric_id }) => metric_id),
        ]
      : route === 'liquidity-fuel'
        ? [...LIQUIDITY_SERIES_IDS, ...catalog.filter(({ layer }) => layer === 'liquidity_fuel').map(({ metric_id }) => metric_id)]
        : OVERVIEW_SERIES_IDS;
  return [...new Set(dynamic)].filter((id) => id in snapshot.metrics);
}

export function snapshotSeriesFallback(snapshot: Snapshot, id: string): SeriesFile {
  const metric = snapshot.metrics[id];
  if (!metric) throw new Error(`Missing snapshot metric: ${id}`);
  return {
    schema_version: SCHEMA_VERSION,
    metric_id: id,
    label: metric.label,
    unit: metric.unit,
    frequency: metric.frequency,
    availability: metric.availability,
    quality: { ...metric.quality },
    observation_date: metric.observation_date,
    released_at: metric.released_at,
    updated_at: metric.updated_at,
    source: { ...metric.source },
    observations: metric.short_series.map((point) => ({ ...point })),
  };
}

export async function loadDashboardCore(base: string, fetcher: typeof fetch = fetch): Promise<DashboardCore> {
  const snapshotPromise = fetchJson(dataUrl(base, 'data/snapshot.json'), fetcher).then((value) => {
    if (!isSnapshot(value)) throw new Error('Invalid v2 snapshot payload');
    return value;
  });
  const catalogPromise = fetchJson(dataUrl(base, 'data/manifest.json'), fetcher)
    .then((value): { catalog: CatalogMetric[]; catalogError: null } => {
      if (!isRecord(value) || value.schema_version !== SCHEMA_VERSION || !isIsoTimestamp(value.generated_at) ||
        !Array.isArray(value.metrics) || !value.metrics.every(isCatalogMetric)) throw new Error('Invalid v2 manifest payload');
      return { catalog: value.metrics, catalogError: null };
    })
    .catch((error): { catalog: CatalogMetric[]; catalogError: string } => ({ catalog: [], catalogError: errorMessage(error) }));
  const [snapshot, { catalog, catalogError }] = await Promise.all([snapshotPromise, catalogPromise]);
  return { snapshot, catalog, catalogError };
}

export async function loadRouteSeries(
  base: string,
  route: RouteId,
  snapshot: Snapshot,
  catalog: readonly CatalogMetric[],
  fetcher: typeof fetch = fetch,
): Promise<RouteSeriesResult> {
  const catalogById = new Map(catalog.map((metric) => [metric.metric_id, metric]));
  const ids = routeMetricIds(route, catalog, snapshot);
  const results = await Promise.all(ids.map(async (id): Promise<[string, SeriesFile, string | null]> => {
    const path = catalogById.get(id)?.series_path ?? `data/series/${id}.json`;
    try {
      const value = await fetchJson(dataUrl(base, path), fetcher);
      if (!isSeriesFile(value, id)) throw new Error(`Invalid v2 series payload: ${id}`);
      return [id, value, null];
    } catch (error) {
      return [id, snapshotSeriesFallback(snapshot, id), errorMessage(error)];
    }
  }));
  const series: SeriesMap = {};
  const errors: Record<string, string> = {};
  for (const [id, file, error] of results) {
    series[id] = file;
    if (error) errors[id] = error;
  }
  return { series, errors };
}

function fractionDigitsFor(unit: string, value?: number | null): number {
  if (unit === 'percent' || unit === 'percent_open_interest') return 2;
  if (unit === 'bp') return 1;
  if (unit === 'USD bn') {
    if (value === 0 || value == null) return 0;
    if (Math.abs(value) < 1) return 3;
    if (Math.abs(value) < 100) return 1;
    return 0;
  }
  return 2;
}

function suffixFor(unit: string): string {
  if (unit === 'percent') return '%';
  if (unit === 'percent_open_interest') return '% OI';
  if (unit === 'bp') return ' bp';
  if (unit === 'USD bn') return 'B';
  return '';
}

export function formatValue(value: number | null | undefined, unit = '', fractionDigits = fractionDigitsFor(unit, value)): string {
  if (value == null || !Number.isFinite(value)) return '—';
  const safeValue = Object.is(value, -0) ? 0 : value;
  return `${new Intl.NumberFormat('en-US', {
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
  }).format(safeValue)}${suffixFor(unit)}`;
}

export function formatSignedDelta(value: number | null | undefined, unit = '', fractionDigits = fractionDigitsFor(unit, value)): string {
  if (value == null || !Number.isFinite(value)) return '—';
  return `${value > 0 ? '+' : ''}${formatValue(value, unit, fractionDigits)}`;
}

export function formatUpdateTimestamp(iso: string | null | undefined): string {
  if (!iso) return '—';
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return '—';
  return parsed.toISOString().slice(5, 16).replace('T', ' ');
}

export function changePresentation(metric: Metric): ChangePresentation {
  const frequency = metric.frequency.toLowerCase();
  if (frequency.includes('quarter')) return { label: '1Q', value: metric.changes.one_quarter ?? metric.changes.one_observation };
  if (frequency.includes('month')) return { label: '1M', value: metric.changes.one_month ?? metric.changes.one_observation };
  if (frequency.includes('week')) return { label: '1W', value: metric.changes.one_week ?? metric.changes.one_observation };
  return { label: '1 OBS', value: metric.changes.one_observation };
}

export function getGlobalLatestDate(series: SeriesMap): string | null {
  let latest: string | null = null;
  for (const file of Object.values(series)) {
    for (const point of file.observations) if (isIsoDay(point.date) && (latest == null || point.date > latest)) latest = point.date;
  }
  return latest;
}

export function windowPoints(points: readonly Point[], range: RangeKey, globalLatestDate: string | null): Point[] {
  if (range === 'MAX' || !isIsoDay(globalLatestDate)) return [...points];
  const end = Date.parse(`${globalLatestDate}T00:00:00Z`);
  const cutoff = end - RANGE_DAYS[range] * DAY_MS;
  return points.filter((point) => isIsoDay(point.date) && Date.parse(`${point.date}T00:00:00Z`) >= cutoff &&
    Date.parse(`${point.date}T00:00:00Z`) <= end);
}

export function buildOverlayUnion(series: SeriesMap, ids: readonly string[]): OverlayUnion {
  const dates = [...new Set(ids.flatMap((id) => (series[id]?.observations ?? [])
    .filter((point) => isIsoDay(point.date)).map((point) => point.date)))].sort();
  const values: Record<string, Array<number | null>> = {};
  for (const id of ids) {
    const byDate = new Map((series[id]?.observations ?? []).filter((point) => isIsoDay(point.date))
      .map((point) => [point.date, point.value]));
    values[id] = dates.map((date) => byDate.get(date) ?? null);
  }
  return { dates, values };
}
