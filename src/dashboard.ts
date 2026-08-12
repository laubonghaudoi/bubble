import type {
  Availability,
  CatalogMetric,
  CollectorSource,
  EvidenceBlock,
  Freshness,
  HealthStatus,
  Layer,
  Methodology,
  Metric,
  MetricContext,
  MetricSource,
  Phase,
  Point,
  QualityInfo,
  Snapshot,
  SourceHealthCounts,
  SwitchState,
} from './types';

export type RouteId = 'overview' | 'liquidity-fuel' | 'market-ignition' | 'fundamental-exit';
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
  return isRecord(value) && Array.isArray(value.technical_flags) &&
    value.technical_flags.every((flag) => typeof flag === 'string') &&
    typeof value.is_proxy === 'boolean' && typeof value.confidence === 'string';
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
  return ['twenty_observations', 'one_week', 'four_weeks', 'one_month', 'one_quarter']
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
    Array.isArray(value.short_series) && value.short_series.every(isPoint);
}

function isEvidenceBlock(value: unknown): value is EvidenceBlock {
  return isRecord(value) && typeof value.id === 'string' && typeof value.label === 'string' &&
    typeof value.available === 'boolean' && (value.triggered === null || typeof value.triggered === 'boolean') &&
    typeof value.status === 'string' && typeof value.summary === 'string';
}

function isSwitch(value: unknown): value is SwitchState {
  return isRecord(value) && typeof value.mode === 'string' && isNullableString(value.assessment) &&
    isNonnegativeInteger(value.available_blocks) && isNonnegativeInteger(value.total_blocks) &&
    value.available_blocks <= value.total_blocks &&
    typeof value.confidence === 'string' && typeof value.summary === 'string' &&
    Array.isArray(value.evidence_blocks) && value.evidence_blocks.every(isEvidenceBlock);
}

function isCollectorSource(value: unknown): value is CollectorSource {
  return isRecord(value) && typeof value.name === 'string' && isNullableString(value.url) &&
    isNullableString(value.tier) && typeof value.rights_note === 'string' &&
    isHealthStatus(value.status) && isFreshness(value.freshness) &&
    isNullableDay(value.observation_date) && isNullableTimestamp(value.released_at) &&
    isNullableTimestamp(value.updated_at) && isNullableUtcTimestamp(value.last_attempt_at) &&
    isNullableTimestamp(value.last_success_at) &&
    isNullableDay(value.expected_next_update) && isNullableString(value.failure_reason);
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
  if (!Object.entries(metrics).every(([id, metric]) => isMetric(metric, id))) return false;
  if (![...OVERVIEW_SERIES_IDS, ...CONFIRMATION_SPREAD_IDS].every((id) => isMetric(metrics[id], id))) return false;
  if (!Object.values(value.sources).every(isCollectorSource)) return false;
  const sources = value.sources as Record<string, CollectorSource>;
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
  return isRecord(value) && value.schema_version === SCHEMA_VERSION && value.metric_id === id &&
    typeof value.label === 'string' && typeof value.unit === 'string' && typeof value.frequency === 'string' &&
    isAvailability(value.availability) && isQuality(value.quality) &&
    isNullableDay(value.observation_date) && isNullableTimestamp(value.released_at) &&
    isNullableTimestamp(value.updated_at) && isMetricSource(value.source) &&
    Array.isArray(value.observations) && value.observations.every(isPoint);
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
  const dynamic = route === 'market-ignition'
    ? catalog.filter(({ layer }) => layer === 'market_ignition').map(({ metric_id }) => metric_id)
    : route === 'fundamental-exit'
      ? catalog.filter(({ layer }) => layer === 'fundamental_exit').map(({ metric_id }) => metric_id)
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
  if (unit === 'percent') return 2;
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
