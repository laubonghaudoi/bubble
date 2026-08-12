import { describe, expect, it, vi } from 'vitest';
import type { Metric, Snapshot } from './types';
import {
  MAIN_TABS,
  SERIES_IDS,
  SWITCH_CONFIG,
  TAPE_GROUPS,
  buildOverlayUnion,
  formatMonthDay,
  formatSignedDelta,
  formatUpdateTimestamp,
  formatValue,
  getGlobalLatestDate,
  loadDashboardData,
  snapshotSeriesFallback,
  windowPoints,
  type SeriesFile,
  type SeriesMap,
} from './dashboard';

function metric(id: string, shortValue = 1): Metric {
  return {
    label: id.toUpperCase(),
    value: shortValue,
    unit: id === 'sofr_iorb_spread' ? 'bp' : 'percent',
    as_of: '2026-08-10',
    quality: 'official',
    status: 'ok',
    short_series: [{ date: '2026-08-10', value: shortValue }],
  };
}

function snapshot(): Snapshot {
  return {
    schema_version: '1.0.0',
    generated_at: '2026-08-12T05:54:00.550421Z',
    market_date: '2026-08-10',
    overall_status: 'neutral',
    switches: {
      liquidity_fuel: { status: 'neutral', score: 0, confidence: 'high', summary: 'ok' },
      market_ignition: { status: 'unavailable', score: 0, confidence: 'low', summary: 'missing' },
      fundamental_exit: { status: 'unavailable', score: 0, confidence: 'low', summary: 'missing' },
    },
    metrics: Object.fromEntries(SERIES_IDS.map((id, index) => [id, metric(id, index + 1)])),
    technical_context: [],
    alerts: [],
    explanations: { headline: 'headline', bullets: [] },
    source_health: { ok: 1, stale: 0, error: 0, missing: 0 },
    sources: {
      source: {
        name: 'Source',
        url: 'https://example.com',
        status: 'ok',
        as_of: '2026-08-10',
        retrieved_at: '2026-08-12T05:54:00.550421Z',
        frequency: 'daily',
        quality: 'official',
      },
    },
  };
}

function seriesFile(id: string, observations: SeriesFile['observations']): SeriesFile {
  return {
    metric_id: id,
    label: id.toUpperCase(),
    unit: 'percent',
    frequency: 'daily',
    quality: 'official',
    status: 'ok',
    as_of: observations.at(-1)?.date ?? null,
    observations,
  };
}

function jsonResponse(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('dashboard configuration', () => {
  it('keeps semantic switch, tape, tab, and series order explicit', () => {
    expect(SWITCH_CONFIG.map(({ id }) => id)).toEqual([
      'liquidity_fuel',
      'market_ignition',
      'fundamental_exit',
    ]);
    expect(TAPE_GROUPS.flatMap(({ ids }) => ids)).toEqual([
      'sofr_iorb_spread',
      'sofr',
      'iorb',
      'effr',
      'obfr',
      'tgcr',
      'bgcr',
      'tga_daily',
      'reserve_balances',
      'fed_total_assets',
      'tga_weekly_h41',
    ]);
    expect(MAIN_TABS[0]).toEqual({ id: 'sofr_iorb_spread', label: 'SOFR−IORB' });
    expect(new Set(SERIES_IDS).size).toBe(11);
  });
});

describe('dashboard formatting', () => {
  it('never conflates zero and missing values', () => {
    expect(formatValue(0, 'bp')).toBe('0.0 bp');
    expect(formatSignedDelta(0, 'bp')).toBe('0.0 bp');
    expect(formatValue(null, 'bp')).toBe('—');
    expect(formatValue(undefined, 'percent')).toBe('—');
  });

  it('uses fixed unit precision, signed deltas, and compact dates', () => {
    expect(formatValue(3.636, 'percent')).toBe('3.64%');
    expect(formatValue(-2, 'bp')).toBe('-2.0 bp');
    expect(formatValue(1234.4, 'USD bn')).toBe('1,234B');
    expect(formatSignedDelta(1.25, 'percent')).toBe('+1.25%');
    expect(formatSignedDelta(-3.5, 'bp')).toBe('-3.5 bp');
    expect(formatMonthDay('2026-08-10')).toBe('08/10');
    expect(formatUpdateTimestamp('2026-08-12T05:54:00.550421Z')).toBe('08-12 05:54');
    expect(formatUpdateTimestamp('not-a-date')).toBe('—');
  });
});

describe('dashboard series helpers', () => {
  it('windows every series against one global latest date', () => {
    const map: SeriesMap = {
      latest: seriesFile('latest', [{ date: '2026-08-12', value: 1 }]),
      older: seriesFile('older', [
        { date: '2026-07-11', value: 1 },
        { date: '2026-07-12', value: 2 },
        { date: '2026-08-01', value: 3 },
      ]),
    };
    const latest = getGlobalLatestDate(map);
    expect(latest).toBe('2026-08-12');
    expect(windowPoints(map.older.observations, '1M', latest).map(({ date }) => date)).toEqual([
      '2026-07-12',
      '2026-08-01',
    ]);
    expect(windowPoints([{ date: '2026-06-01', value: 9 }], '1M', latest)).toEqual([]);
  });

  it('ignores impossible calendar dates when anchoring and windowing ranges', () => {
    const map: SeriesMap = {
      valid: seriesFile('valid', [{ date: '2026-08-12', value: 1 }]),
      invalid: seriesFile('invalid', [{ date: '9999-99-99', value: 2 }]),
    };
    expect(getGlobalLatestDate(map)).toBe('2026-08-12');
    expect(windowPoints([
      { date: '9999-99-99', value: 2 },
      { date: '2026-08-10', value: 3 },
    ], '1M', '2026-08-12')).toEqual([{ date: '2026-08-10', value: 3 }]);
  });

  it('builds a sorted date union with null-aligned values', () => {
    const map: SeriesMap = {
      a: seriesFile('a', [
        { date: '2026-08-03', value: 3 },
        { date: '2026-08-01', value: 0 },
      ]),
      b: seriesFile('b', [
        { date: '2026-08-02', value: 2 },
        { date: '2026-08-03', value: 4 },
      ]),
    };
    expect(buildOverlayUnion(map, ['a', 'b'])).toEqual({
      dates: ['2026-08-01', '2026-08-02', '2026-08-03'],
      values: {
        a: [0, null, 3],
        b: [null, 2, 4],
      },
    });
  });

  it('copies snapshot short series for a safe independent fallback', () => {
    const source = snapshot();
    const fallback = snapshotSeriesFallback(source, 'sofr');
    expect(fallback.observations).toEqual(source.metrics.sofr.short_series);
    expect(fallback.observations).not.toBe(source.metrics.sofr.short_series);
    expect(snapshotSeriesFallback(source, 'unknown')).toMatchObject({
      metric_id: 'unknown',
      status: 'missing',
      observations: [],
    });
  });
});

describe('loadDashboardData', () => {
  it('falls back each failed series independently', async () => {
    const source = snapshot();
    const fetcher = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith('/data/snapshot.json')) return jsonResponse(source);
      if (url.endsWith('/data/manifest.json')) return jsonResponse({ metrics: [] });
      if (url.endsWith('/data/series/iorb.json')) return jsonResponse({ error: 'nope' }, 503);
      if (url.endsWith('/data/series/effr.json')) throw new Error('offline');
      const id = /\/data\/series\/([^/]+)\.json$/.exec(url)?.[1] ?? '';
      return jsonResponse(seriesFile(id, [{ date: '2026-08-11', value: 99 }]));
    }) as unknown as typeof fetch;

    const data = await loadDashboardData('/bubble/', fetcher);

    expect(data.series.sofr.observations).toEqual([{ date: '2026-08-11', value: 99 }]);
    expect(data.series.iorb.observations).toEqual(source.metrics.iorb.short_series);
    expect(data.series.effr.observations).toEqual(source.metrics.effr.short_series);
    expect(Object.keys(data.series)).toEqual([...SERIES_IDS]);
    expect(Object.keys(data.seriesErrors)).toEqual(['iorb', 'effr']);
    expect(fetcher).toHaveBeenCalledWith('/bubble/data/snapshot.json');
  });

  it('keeps manifest failure nonfatal while snapshot failure stays fatal', async () => {
    const source = snapshot();
    const manifestFailure = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith('/data/snapshot.json')) return jsonResponse(source);
      if (url.endsWith('/data/manifest.json')) return jsonResponse({}, 500);
      const id = /\/data\/series\/([^/]+)\.json$/.exec(url)?.[1] ?? '';
      return jsonResponse(seriesFile(id, []));
    }) as unknown as typeof fetch;
    const data = await loadDashboardData('./', manifestFailure);
    expect(data.catalog).toEqual([]);
    expect(data.catalogError).toContain('500');

    const snapshotFailure = vi.fn(async () => jsonResponse({}, 500)) as unknown as typeof fetch;
    await expect(loadDashboardData('/', snapshotFailure)).rejects.toThrow('500');
  });

  it('rejects malformed nested snapshots and degrades malformed manifest entries safely', async () => {
    const malformedSnapshot = { ...snapshot(), metrics: {} };
    const snapshotFetcher = vi.fn(async () => jsonResponse(malformedSnapshot)) as unknown as typeof fetch;
    await expect(loadDashboardData('/', snapshotFetcher)).rejects.toThrow('Invalid snapshot payload');

    const source = snapshot();
    const manifestFetcher = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith('/data/snapshot.json')) return jsonResponse(source);
      if (url.endsWith('/data/manifest.json')) return jsonResponse({ metrics: [null] });
      const id = /\/data\/series\/([^/]+)\.json$/.exec(url)?.[1] ?? '';
      return jsonResponse(seriesFile(id, []));
    }) as unknown as typeof fetch;
    const data = await loadDashboardData('/', manifestFetcher);
    expect(data.catalog).toEqual([]);
    expect(data.catalogError).toContain('Invalid manifest payload');
  });
});
