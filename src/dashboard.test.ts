import { describe, expect, it, vi } from 'vitest';
import {
  CONFIRMATION_SPREAD_IDS,
  OVERVIEW_SERIES_IDS,
  RANGE_DAYS,
  SCHEMA_VERSION,
  SWITCH_CONFIG,
  TAPE_GROUPS,
  buildOverlayUnion,
  changePresentation,
  formatSignedDelta,
  formatValue,
  getGlobalLatestDate,
  isSnapshot,
  loadDashboardCore,
  loadRouteSeries,
  parseRoute,
  routeMetricIds,
  snapshotSeriesFallback,
  windowPoints,
  type SeriesMap,
} from './dashboard';
import { jsonResponse, makeCatalog, makeMetric, makeSeriesFile, makeSnapshot } from './test-fixtures';
import type { Snapshot } from './types';

describe('v2 contract and configuration', () => {
  it('hard-cuts to schema 2.0.0 and requires the locked assessment field', () => {
    const valid = makeSnapshot();
    expect(isSnapshot(valid)).toBe(true);
    expect(isSnapshot({ ...valid, schema_version: '1.0.0' })).toBe(false);
    const withoutAssessment = { ...valid } as Record<string, unknown>;
    delete withoutAssessment.overall_assessment;
    expect(isSnapshot(withoutAssessment)).toBe(false);
    expect(isSnapshot({ ...valid, source_health: { ok: 1, stale: 0, error: 0 } })).toBe(false);

    const withoutStatistics = structuredClone(valid) as unknown as Record<string, unknown>;
    delete (withoutStatistics.metrics as Record<string, Record<string, unknown>>).sofr.statistics;
    expect(isSnapshot(withoutStatistics)).toBe(false);

    const withoutAttempt = structuredClone(valid) as Snapshot;
    delete (withoutAttempt.metrics.sofr.quality as Partial<Snapshot['metrics'][string]['quality']>).last_attempt_at;
    expect(isSnapshot(withoutAttempt)).toBe(false);

    const sourceWithoutAttempt = structuredClone(valid) as Snapshot;
    delete (sourceWithoutAttempt.sources.nyfed_rates as Partial<Snapshot['sources'][string]>).last_attempt_at;
    expect(isSnapshot(sourceWithoutAttempt)).toBe(false);

    const nonUtcAttempt = structuredClone(valid);
    nonUtcAttempt.metrics.sofr.quality.last_attempt_at = '2026-08-12T10:32:49-07:00';
    expect(isSnapshot(nonUtcAttempt)).toBe(false);

    const invalidStatistic = structuredClone(valid) as unknown as Record<string, unknown>;
    ((invalidStatistic.metrics as Record<string, Record<string, unknown>>).sofr.statistics as Record<string, unknown>).trend = 'up';
    expect(isSnapshot(invalidStatistic)).toBe(false);
  });

  it('keeps switch and tape order explicit and includes ON RRP and SRF', () => {
    expect(SWITCH_CONFIG.map(({ id }) => id)).toEqual(['liquidity_fuel', 'market_ignition', 'fundamental_exit']);
    const tape = TAPE_GROUPS.flatMap(({ ids }) => ids);
    expect(tape).toEqual(OVERVIEW_SERIES_IDS);
    expect(tape).toContain('on_rrp_accepted');
    expect(tape).toContain('srf_accepted');
    expect(CONFIRMATION_SPREAD_IDS).toHaveLength(5);
  });

  it('parses canonical hashes and falls back safely', () => {
    expect(parseRoute('#/overview')).toBe('overview');
    expect(parseRoute('#/liquidity-fuel')).toBe('liquidity-fuel');
    expect(parseRoute('#/market-ignition/')).toBe('market-ignition');
    expect(parseRoute('#/unknown')).toBe('overview');
  });

  it('selects route series from v2 manifest instead of loading everything', () => {
    const snapshot = makeSnapshot();
    const catalog = makeCatalog();
    expect(routeMetricIds('overview', catalog, snapshot)).toEqual(OVERVIEW_SERIES_IDS);
    expect(routeMetricIds('market-ignition', catalog, snapshot)).toEqual(['vix_vix3m_proxy', 'finra_margin_debt']);
    expect(routeMetricIds('fundamental-exit', catalog, snapshot)).toEqual(['hyperscaler_capex']);
  });
});

describe('formatting and range behavior', () => {
  it('never conflates zero with missing', () => {
    expect(formatValue(0, 'bp')).toBe('0.0 bp');
    expect(formatSignedDelta(0, 'bp')).toBe('0.0 bp');
    expect(formatValue(null, 'bp')).toBe('—');
    expect(formatValue(0.725, 'USD bn')).toBe('0.725B');
    expect(formatValue(12.738, 'USD bn')).toBe('12.7B');
    expect(formatValue(966.851, 'USD bn')).toBe('967B');
    expect(formatValue(0, 'USD bn')).toBe('0B');
    expect(formatSignedDelta(-0.001, 'USD bn')).toBe('-0.001B');
  });

  it('uses frequency-aware change labels', () => {
    expect(changePresentation(makeMetric('daily')).label).toBe('1 OBS');
    expect(changePresentation(makeMetric('weekly', { frequency: 'weekly', changes: { one_observation: 1, five_observations: 5, one_week: 7 } }))).toEqual({ label: '1W', value: 7 });
    expect(changePresentation(makeMetric('monthly', { frequency: 'monthly', changes: { one_observation: 1, five_observations: 5, one_month: 30 } }))).toEqual({ label: '1M', value: 30 });
    expect(changePresentation(makeMetric('quarterly', { frequency: 'quarterly', changes: { one_observation: 1, five_observations: 5, one_quarter: 90 } }))).toEqual({ label: '1Q', value: 90 });
  });

  it('supports 8W and 12W windows against one global anchor', () => {
    expect(RANGE_DAYS['8W']).toBe(56);
    expect(RANGE_DAYS['12W']).toBe(84);
    const snapshot = makeSnapshot();
    const latest = makeSeriesFile(snapshot.metrics.sofr);
    latest.observations = [{ date: '2026-08-12', value: 1 }];
    const older = makeSeriesFile(snapshot.metrics.iorb);
    older.observations = [{ date: '2026-06-16', value: 1 }, { date: '2026-06-18', value: 2 }, { date: '2026-07-01', value: 3 }];
    const map: SeriesMap = { latest, older };
    expect(getGlobalLatestDate(map)).toBe('2026-08-12');
    expect(windowPoints(older.observations, '8W', '2026-08-12').map(({ date }) => date)).toEqual(['2026-06-18', '2026-07-01']);
    expect(windowPoints(older.observations, '12W', '2026-08-12')).toHaveLength(3);
  });

  it('date-unions overlays with nulls for absent observations', () => {
    const snapshot = makeSnapshot();
    const a = makeSeriesFile(snapshot.metrics.sofr);
    const b = makeSeriesFile(snapshot.metrics.iorb);
    a.observations = [{ date: '2026-08-03', value: 3 }, { date: '2026-08-01', value: 0 }];
    b.observations = [{ date: '2026-08-02', value: 2 }];
    expect(buildOverlayUnion({ a, b }, ['a', 'b'])).toEqual({
      dates: ['2026-08-01', '2026-08-02', '2026-08-03'],
      values: { a: [0, null, 3], b: [null, 2, null] },
    });
  });
});

describe('route-lazy loading', () => {
  it('loads only route series and falls back independently to short_series', async () => {
    const snapshot = makeSnapshot();
    const catalog = makeCatalog();
    const requested: string[] = [];
    const fetcher = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input); requested.push(url);
      const id = /\/data\/series\/([^/]+)\.json$/.exec(url)?.[1] ?? '';
      if (id === 'finra_margin_debt') return jsonResponse({}, 503);
      return jsonResponse(makeSeriesFile(snapshot.metrics[id]));
    }) as unknown as typeof fetch;
    const result = await loadRouteSeries('/bubble/', 'market-ignition', snapshot, catalog, fetcher);
    expect(requested).toEqual(['/bubble/data/series/vix_vix3m_proxy.json', '/bubble/data/series/finra_margin_debt.json']);
    expect(result.errors).toHaveProperty('finra_margin_debt');
    expect(result.series.finra_margin_debt.observations).toEqual(snapshot.metrics.finra_margin_debt.short_series);
    expect(snapshotSeriesFallback(snapshot, 'sofr').schema_version).toBe(SCHEMA_VERSION);
  });

  it('loads v2 core in parallel, keeps manifest failure nonfatal, and rejects v1 snapshot', async () => {
    const snapshot = makeSnapshot();
    const catalog = makeCatalog();
    const ok = vi.fn(async (input: RequestInfo | URL) => String(input).endsWith('snapshot.json')
      ? jsonResponse(snapshot)
      : jsonResponse({ schema_version: SCHEMA_VERSION, generated_at: snapshot.generated_at, metrics: catalog })) as unknown as typeof fetch;
    const loaded = await loadDashboardCore('/', ok);
    expect(loaded.snapshot.schema_version).toBe(SCHEMA_VERSION);
    expect(loaded.catalog).toEqual(catalog);
    expect(loaded.catalogError).toBeNull();

    const noManifest = vi.fn(async (input: RequestInfo | URL) => String(input).endsWith('snapshot.json') ? jsonResponse(snapshot) : jsonResponse({}, 500)) as unknown as typeof fetch;
    await expect(loadDashboardCore('/', noManifest)).resolves.toMatchObject({ catalog: [], catalogError: expect.stringContaining('500') });

    const v1 = vi.fn(async (input: RequestInfo | URL) => String(input).endsWith('snapshot.json')
      ? jsonResponse({ ...snapshot, schema_version: '1.0.0' })
      : jsonResponse({ schema_version: SCHEMA_VERSION, generated_at: snapshot.generated_at, metrics: catalog })) as unknown as typeof fetch;
    await expect(loadDashboardCore('/', v1)).rejects.toThrow('Invalid v2 snapshot payload');
  });
});
