import type { CatalogMetric, Point, Snapshot, Status } from './types';

export type RangeKey = '1M' | '3M' | '1Y' | 'MAX';

export interface SeriesFile {
  schema_version?: string;
  metric_id: string;
  label: string;
  unit: string;
  frequency: string;
  quality: string;
  status: Status;
  as_of: string | null;
  retrieved_at?: string | null;
  observations: Point[];
}

export type SeriesMap = Record<string, SeriesFile>;

export interface DashboardData {
  snapshot: Snapshot;
  catalog: CatalogMetric[];
  series: SeriesMap;
  catalogError: string | null;
  seriesErrors: Record<string, string>;
}

export interface OverlayUnion {
  dates: string[];
  values: Record<string, Array<number | null>>;
}

export const THRESHOLD_BP = 3;

export const RANGE_DAYS: Record<RangeKey, number> = {
  '1M': 31,
  '3M': 93,
  '1Y': 366,
  MAX: 100_000,
};

export const SWITCH_CONFIG = [
  { id: 'liquidity_fuel', num: '01', kicker: 'LIQUIDITY FUEL', title: '流動性燃料' },
  { id: 'market_ignition', num: '02', kicker: 'MARKET IGNITION', title: '市場引信' },
  { id: 'fundamental_exit', num: '03', kicker: 'FUNDAMENTAL EXIT', title: '基本面逃生門' },
] as const;

export const TAPE_GROUPS = [
  {
    label: 'DAILY · 隔夜價格與流量',
    ids: ['sofr_iorb_spread', 'sofr', 'iorb', 'effr', 'obfr', 'tgcr', 'bgcr', 'tga_daily'],
  },
  {
    label: 'WEEKLY · Fed 資產負債表',
    ids: ['reserve_balances', 'fed_total_assets', 'tga_weekly_h41'],
  },
] as const;

export const TICKERS: Readonly<Record<string, string>> = {
  sofr_iorb_spread: 'SOFR−IORB',
  sofr: 'SOFR',
  iorb: 'IORB',
  effr: 'EFFR',
  obfr: 'OBFR',
  tgcr: 'TGCR',
  bgcr: 'BGCR',
  tga_daily: 'TGA · DAILY',
  reserve_balances: 'RESERVES',
  fed_total_assets: 'WALCL',
  tga_weekly_h41: 'TGA · H.4.1',
};

export const MAIN_TABS = [
  { id: 'sofr_iorb_spread', label: 'SOFR−IORB' },
  { id: 'sofr', label: 'SOFR' },
  { id: 'iorb', label: 'IORB' },
  { id: 'effr', label: 'EFFR' },
  { id: 'tga_daily', label: 'TGA' },
  { id: 'reserve_balances', label: 'RESERVES' },
  { id: 'fed_total_assets', label: 'WALCL' },
] as const;

export const SERIES_IDS = [
  'sofr',
  'iorb',
  'effr',
  'obfr',
  'tgcr',
  'bgcr',
  'sofr_iorb_spread',
  'tga_daily',
  'tga_weekly_h41',
  'reserve_balances',
  'fed_total_assets',
] as const;

export const DEFAULT_OVERLAY: Readonly<Record<string, boolean>> = {
  sofr: true,
  iorb: true,
  effr: true,
  obfr: false,
  tgcr: false,
  bgcr: false,
};

export const STATUS_LABELS: Readonly<Record<Status, string>> = {
  ok: '正常',
  stale: '過期',
  missing: '未接通',
  error: '抓取錯誤',
  not_released: '尚未發布',
  manual_update_due: '待人工更新',
  paid_data_unavailable: '需供應商',
};

const FALLBACK_FREQUENCIES: Readonly<Record<string, string>> = {
  sofr: 'business_daily',
  iorb: 'weekly / policy',
  effr: 'business_daily',
  obfr: 'business_daily',
  tgcr: 'business_daily',
  bgcr: 'business_daily',
  sofr_iorb_spread: 'business_daily',
  tga_daily: 'business_daily',
  tga_weekly_h41: 'weekly / policy',
  reserve_balances: 'weekly / policy',
  fed_total_assets: 'weekly / policy',
};

const DAY_MS = 86_400_000;
const ISO_DAY = /^\d{4}-\d{2}-\d{2}$/;

function isIsoDay(value: unknown): value is string {
  if (typeof value !== 'string' || !ISO_DAY.test(value)) return false;
  const timestamp = Date.parse(`${value}T00:00:00Z`);
  return Number.isFinite(timestamp) && new Date(timestamp).toISOString().slice(0, 10) === value;
}

function fractionDigitsFor(unit: string): number {
  if (unit === 'percent') return 2;
  if (unit === 'bp') return 1;
  if (unit === 'USD bn') return 0;
  return 2;
}

function suffixFor(unit: string): string {
  if (unit === 'percent') return '%';
  if (unit === 'bp') return ' bp';
  if (unit === 'USD bn') return 'B';
  return '';
}

export function formatValue(
  value: number | null | undefined,
  unit = '',
  fractionDigits = fractionDigitsFor(unit),
): string {
  if (value == null || !Number.isFinite(value)) return '—';
  const safeValue = Object.is(value, -0) ? 0 : value;
  const formatted = new Intl.NumberFormat('en-US', {
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
  }).format(safeValue);
  return `${formatted}${suffixFor(unit)}`;
}

export function formatSignedDelta(
  value: number | null | undefined,
  unit = '',
  fractionDigits = fractionDigitsFor(unit),
): string {
  if (value == null || !Number.isFinite(value)) return '—';
  return `${value > 0 ? '+' : ''}${formatValue(value, unit, fractionDigits)}`;
}

export function formatMonthDay(date: string | null | undefined): string {
  if (!date) return '—';
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(date);
  return match ? `${match[2]}/${match[3]}` : '—';
}

export function formatUpdateTimestamp(iso: string | null | undefined): string {
  if (!iso) return '—';
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return '—';
  return parsed.toISOString().slice(5, 16).replace('T', ' ');
}

export function getGlobalLatestDate(series: SeriesMap): string | null {
  let latest: string | null = null;
  for (const file of Object.values(series)) {
    for (const point of file.observations) {
      if (isIsoDay(point.date) && (latest == null || point.date > latest)) latest = point.date;
    }
  }
  return latest;
}

export function windowPoints(
  points: readonly Point[],
  range: RangeKey,
  globalLatestDate: string | null,
): Point[] {
  if (range === 'MAX' || !isIsoDay(globalLatestDate)) return [...points];
  const end = Date.parse(`${globalLatestDate}T00:00:00Z`);
  const cutoff = end - RANGE_DAYS[range] * DAY_MS;
  return points.filter((point) => {
    if (!isIsoDay(point.date)) return false;
    const time = Date.parse(`${point.date}T00:00:00Z`);
    return time >= cutoff && time <= end;
  });
}

export function buildOverlayUnion(series: SeriesMap, ids: readonly string[]): OverlayUnion {
  const dates = [
    ...new Set(
      ids.flatMap((id) =>
        (series[id]?.observations ?? []).filter((point) => isIsoDay(point.date)).map((point) => point.date),
      ),
    ),
  ].sort();

  const values: Record<string, Array<number | null>> = {};
  for (const id of ids) {
    const byDate = new Map<string, number | null>();
    for (const point of series[id]?.observations ?? []) {
      if (isIsoDay(point.date)) byDate.set(point.date, point.value);
    }
    values[id] = dates.map((date) => (byDate.has(date) ? (byDate.get(date) ?? null) : null));
  }
  return { dates, values };
}

export function snapshotSeriesFallback(snapshot: Snapshot, id: string): SeriesFile {
  const metric = snapshot.metrics[id];
  return {
    schema_version: snapshot.schema_version,
    metric_id: id,
    label: metric?.label ?? id,
    unit: metric?.unit ?? '',
    frequency: FALLBACK_FREQUENCIES[id] ?? '',
    quality: metric?.quality ?? 'proxy',
    status: metric?.status ?? 'missing',
    as_of: metric?.as_of ?? null,
    retrieved_at: snapshot.generated_at,
    observations: (metric?.short_series ?? []).map((point) => ({ ...point })),
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isStatus(value: unknown): value is Status {
  return typeof value === 'string' && Object.prototype.hasOwnProperty.call(STATUS_LABELS, value);
}

function isPoint(value: unknown): value is Point {
  return (
    isRecord(value) &&
    isIsoDay(value.date) &&
    (value.value === null || (typeof value.value === 'number' && Number.isFinite(value.value)))
  );
}

function isNullableString(value: unknown): value is string | null {
  return value === null || typeof value === 'string';
}

function isNullableNumber(value: unknown): value is number | null | undefined {
  return value == null || (typeof value === 'number' && Number.isFinite(value));
}

function isMetric(value: unknown): boolean {
  return (
    isRecord(value) &&
    typeof value.label === 'string' &&
    (value.value === null || (typeof value.value === 'number' && Number.isFinite(value.value))) &&
    typeof value.unit === 'string' &&
    isNullableString(value.as_of) &&
    typeof value.quality === 'string' &&
    isStatus(value.status) &&
    isNullableNumber(value.previous) &&
    isNullableNumber(value.delta_1d) &&
    isNullableNumber(value.change_5d) &&
    (value.trend_5d === undefined || typeof value.trend_5d === 'string') &&
    (value.short_series === undefined || (Array.isArray(value.short_series) && value.short_series.every(isPoint))) &&
    (value.flags === undefined || (Array.isArray(value.flags) && value.flags.every((item) => typeof item === 'string'))) &&
    (value.source_ids === undefined || (Array.isArray(value.source_ids) && value.source_ids.every((item) => typeof item === 'string')))
  );
}

function isSource(value: unknown): boolean {
  return (
    isRecord(value) &&
    typeof value.name === 'string' &&
    typeof value.url === 'string' &&
    isStatus(value.status) &&
    isNullableString(value.as_of) &&
    isNullableString(value.retrieved_at) &&
    typeof value.frequency === 'string' &&
    typeof value.quality === 'string' &&
    (value.error === undefined || isNullableString(value.error))
  );
}

function isSnapshot(value: unknown): value is Snapshot {
  if (
    !isRecord(value) ||
    typeof value.schema_version !== 'string' ||
    typeof value.generated_at !== 'string' ||
    !Number.isFinite(Date.parse(value.generated_at)) ||
    !(value.market_date === null || isIsoDay(value.market_date)) ||
    typeof value.overall_status !== 'string' ||
    !isRecord(value.metrics) ||
    !isRecord(value.sources) ||
    !isRecord(value.switches) ||
    !isRecord(value.source_health) ||
    !isRecord(value.explanations) ||
    !Array.isArray(value.technical_context) ||
    !Array.isArray(value.alerts)
  ) return false;

  const metrics = value.metrics as Record<string, unknown>;
  const sources = value.sources as Record<string, unknown>;
  const switches = value.switches as Record<string, unknown>;
  const sourceHealth = value.source_health as Record<string, unknown>;
  const explanations = value.explanations as Record<string, unknown>;

  if (!SERIES_IDS.every((id) => isMetric(metrics[id])) || !Object.values(metrics).every(isMetric)) return false;
  if (!Object.values(sources).every(isSource)) return false;
  if (!SWITCH_CONFIG.every(({ id }) => {
    const item = switches[id];
    return isRecord(item) && typeof item.status === 'string' && typeof item.score === 'number' &&
      Number.isFinite(item.score) && typeof item.confidence === 'string' && typeof item.summary === 'string';
  })) return false;
  if (!['ok', 'stale', 'error', 'missing'].every((key) => typeof sourceHealth[key] === 'number' && Number.isFinite(sourceHealth[key]))) return false;
  if (typeof explanations.headline !== 'string' || !Array.isArray(explanations.bullets) || !explanations.bullets.every((bullet) =>
    isRecord(bullet) && typeof bullet.observation === 'string' && typeof bullet.meaning === 'string' &&
    typeof bullet.caveat === 'string' && typeof bullet.confidence === 'string')) return false;
  if (!value.technical_context.every((item) => isRecord(item) && isIsoDay(item.date) && Array.isArray(item.flags) &&
    item.flags.every((flag) => typeof flag === 'string') && typeof item.note === 'string')) return false;
  if (!value.alerts.every((item) => isRecord(item) && typeof item.level === 'string' &&
    typeof item.title === 'string' && typeof item.detail === 'string')) return false;
  return true;
}

const CATALOG_STRING_FIELDS: ReadonlyArray<keyof CatalogMetric> = [
  'id', 'label', 'unit', 'frequency', 'layer', 'role', 'quality', 'availability',
  'question_answered', 'why_track', 'interpretation_up', 'interpretation_down',
  'false_positives', 'confirm_with', 'cannot_conclude', 'methodology', 'source_url', 'series_path',
];

function isCatalogMetric(value: unknown): value is CatalogMetric {
  return isRecord(value) && CATALOG_STRING_FIELDS.every((field) => typeof value[field] === 'string');
}

function isSeriesFile(value: unknown, id: string): value is SeriesFile {
  return (
    isRecord(value) &&
    value.metric_id === id &&
    typeof value.label === 'string' &&
    typeof value.unit === 'string' &&
    typeof value.frequency === 'string' &&
    typeof value.quality === 'string' &&
    isStatus(value.status) &&
    (value.as_of === null || typeof value.as_of === 'string') &&
    Array.isArray(value.observations) &&
    value.observations.every(isPoint)
  );
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

export async function loadDashboardData(base: string, fetcher: typeof fetch = fetch): Promise<DashboardData> {
  const rawSnapshot = await fetchJson(dataUrl(base, 'data/snapshot.json'), fetcher);
  if (!isSnapshot(rawSnapshot)) throw new Error('Invalid snapshot payload');
  const snapshot = rawSnapshot;

  const catalogRequest = fetchJson(dataUrl(base, 'data/manifest.json'), fetcher)
    .then((rawManifest): { catalog: CatalogMetric[]; catalogError: null } => {
      if (!isRecord(rawManifest) || !Array.isArray(rawManifest.metrics) || !rawManifest.metrics.every(isCatalogMetric)) {
        throw new Error('Invalid manifest payload');
      }
      return { catalog: rawManifest.metrics, catalogError: null };
    })
    .catch((error): { catalog: CatalogMetric[]; catalogError: string } => ({
      catalog: [],
      catalogError: errorMessage(error),
    }));

  const seriesRequest = Promise.all(
    SERIES_IDS.map(async (id): Promise<[string, SeriesFile, string | null]> => {
      try {
        const rawSeries = await fetchJson(dataUrl(base, `data/series/${id}.json`), fetcher);
        if (!isSeriesFile(rawSeries, id)) throw new Error(`Invalid series payload: ${id}`);
        return [id, rawSeries, null];
      } catch (error) {
        return [id, snapshotSeriesFallback(snapshot, id), errorMessage(error)];
      }
    }),
  );
  const [{ catalog, catalogError }, results] = await Promise.all([catalogRequest, seriesRequest]);

  const series: SeriesMap = {};
  const seriesErrors: Record<string, string> = {};
  for (const [id, file, error] of results) {
    series[id] = file;
    if (error) seriesErrors[id] = error;
  }

  return { snapshot, catalog, series, catalogError, seriesErrors };
}
