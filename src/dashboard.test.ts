import { describe, expect, it, vi } from 'vitest';
import {
  CONFIRMATION_SPREAD_IDS,
  OVERVIEW_SERIES_IDS,
  P1_CFTC_CONFIG,
  P1_RIGHTS_GATED_IDS,
  P2_ACTIVE_IDS,
  P2_HELD_IDS,
  P2_SERIES_IDS,
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

    const withoutEvidenceDirection = structuredClone(valid);
    delete (withoutEvidenceDirection.switches.market_ignition.evidence_blocks[0] as Partial<typeof withoutEvidenceDirection.switches.market_ignition.evidence_blocks[number]>).direction;
    expect(isSnapshot(withoutEvidenceDirection)).toBe(false);

    const withoutEvidenceConfidence = structuredClone(valid);
    delete (withoutEvidenceConfidence.switches.market_ignition.evidence_blocks[0] as Partial<typeof withoutEvidenceConfidence.switches.market_ignition.evidence_blocks[number]>).confidence;
    expect(isSnapshot(withoutEvidenceConfidence)).toBe(false);

    const p1WithAssessment = structuredClone(valid);
    p1WithAssessment.switches.market_ignition.assessment = 'WATCH';
    expect(isSnapshot(p1WithAssessment)).toBe(false);

    const p1WithSeverityMode = structuredClone(valid);
    p1WithSeverityMode.switches.market_ignition.mode = 'WATCH';
    expect(isSnapshot(p1WithSeverityMode)).toBe(false);

    const p1WithTriggeredSeverity = structuredClone(valid);
    p1WithTriggeredSeverity.switches.market_ignition.evidence_blocks[1].triggered = true;
    expect(isSnapshot(p1WithTriggeredSeverity)).toBe(false);

    const unavailableP1WithDirection = structuredClone(valid);
    unavailableP1WithDirection.switches.market_ignition.evidence_blocks[0].direction = 'MORE_NET_LONG';
    expect(isSnapshot(unavailableP1WithDirection)).toBe(false);

    const cftcWithoutEightWeekChange = structuredClone(valid);
    delete cftcWithoutEightWeekChange.metrics.cftc_e_mini_sp500_asset_manager_net_pct_oi.changes.eight_weeks;
    expect(isSnapshot(cftcWithoutEightWeekChange)).toBe(false);

    const cftcWithoutNetPosition = structuredClone(valid);
    delete cftcWithoutNetPosition.metrics.cftc_e_mini_sp500_asset_manager_net_pct_oi.statistics.net_position;
    expect(isSnapshot(cftcWithoutNetPosition)).toBe(false);

    const cftcWrongAvailability = structuredClone(valid);
    cftcWrongAvailability.metrics.cftc_e_mini_sp500_asset_manager_net_pct_oi.availability = 'ACTIVE_PROXY';
    cftcWrongAvailability.active_free_count -= 1;
    cftcWrongAvailability.active_proxy_count += 1;
    expect(isSnapshot(cftcWrongAvailability)).toBe(false);

    const heldWithValue = structuredClone(valid);
    heldWithValue.metrics.vix_vix3m_term_structure_proxy.value = 99;
    heldWithValue.metrics.vix_vix3m_term_structure_proxy.short_series = [{ date: '2026-08-11', value: 99 }];
    expect(isSnapshot(heldWithValue)).toBe(false);

    const stalePositioningStillAvailable = structuredClone(valid);
    for (const { id } of P1_CFTC_CONFIG) {
      stalePositioningStillAvailable.metrics[id].quality.status = 'STALE';
      stalePositioningStillAvailable.metrics[id].quality.freshness = 'STALE';
    }
    stalePositioningStillAvailable.stale_count += P1_CFTC_CONFIG.length;
    expect(isSnapshot(stalePositioningStillAvailable)).toBe(false);

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

  it('only exposes CFTC positioning when every weekly input is complete, fresh, and aligned', () => {
    expect(P1_CFTC_CONFIG.map(({ availability }) => availability)).toEqual([
      'ACTIVE_FREE', 'ACTIVE_PROXY', 'ACTIVE_FREE', 'ACTIVE_PROXY',
    ]);
    for (const { id } of P1_CFTC_CONFIG) {
      const lateInput = structuredClone(makeSnapshot());
      lateInput.metrics[id].quality.freshness = 'LATE';
      expect(isSnapshot(lateInput), `${id} must be FRESH`).toBe(false);
    }
    for (const { id, availability } of P1_CFTC_CONFIG) {
      const wrongAvailability = structuredClone(makeSnapshot());
      const replacement = availability === 'ACTIVE_FREE' ? 'ACTIVE_PROXY' : 'ACTIVE_FREE';
      wrongAvailability.metrics[id].availability = replacement;
      wrongAvailability[availability === 'ACTIVE_FREE' ? 'active_free_count' : 'active_proxy_count'] -= 1;
      wrongAvailability[replacement === 'ACTIVE_FREE' ? 'active_free_count' : 'active_proxy_count'] += 1;
      expect(isSnapshot(wrongAvailability), `${id} availability`).toBe(false);
    }

    const adversarialMutations: Array<[string, (snapshot: Snapshot) => void]> = [
      ['health', (snapshot) => { snapshot.metrics[P1_CFTC_CONFIG[0].id].quality.status = 'ERROR'; }],
      ['aligned observation date', (snapshot) => { snapshot.metrics[P1_CFTC_CONFIG[1].id].observation_date = '2026-08-10'; }],
      ['non-null 8W change', (snapshot) => { snapshot.metrics[P1_CFTC_CONFIG[2].id].changes.eight_weeks = null; }],
      ['non-null 12W change', (snapshot) => { snapshot.metrics[P1_CFTC_CONFIG[3].id].changes.twelve_weeks = null; }],
      ['non-null 8W statistic', (snapshot) => { snapshot.metrics[P1_CFTC_CONFIG[0].id].statistics.change_8_weeks = null; }],
      ['non-null 12W statistic', (snapshot) => { snapshot.metrics[P1_CFTC_CONFIG[1].id].statistics.change_12_weeks = null; }],
      ['non-null z-score', (snapshot) => { snapshot.metrics[P1_CFTC_CONFIG[2].id].statistics.z_score_3_year = null; }],
      ['156-observation z-score sample', (snapshot) => { snapshot.metrics[P1_CFTC_CONFIG[3].id].statistics.z_score_3_year_sample_size = 155; }],
      ['aligned non-null date', (snapshot) => { snapshot.metrics[P1_CFTC_CONFIG[0].id].observation_date = null; }],
      ['percent-open-interest unit', (snapshot) => { snapshot.metrics[P1_CFTC_CONFIG[1].id].unit = 'percent'; }],
    ];
    for (const [requirement, mutate] of adversarialMutations) {
      const claimedAvailable = structuredClone(makeSnapshot());
      mutate(claimedAvailable);
      expect(isSnapshot(claimedAvailable), requirement).toBe(false);
    }

    const correctlyUnavailable = structuredClone(makeSnapshot());
    correctlyUnavailable.metrics[P1_CFTC_CONFIG[0].id].changes.eight_weeks = null;
    correctlyUnavailable.metrics[P1_CFTC_CONFIG[0].id].statistics.change_8_weeks = null;
    correctlyUnavailable.metrics[P1_CFTC_CONFIG[0].id].context.direction = 'UNKNOWN';
    correctlyUnavailable.switches.market_ignition.available_blocks = 0;
    correctlyUnavailable.switches.market_ignition.confidence = 'UNKNOWN';
    correctlyUnavailable.switches.market_ignition.evidence_blocks[1] = {
      ...correctlyUnavailable.switches.market_ignition.evidence_blocks[1],
      available: false,
      status: 'UNAVAILABLE_FREE',
      direction: 'UNKNOWN',
      confidence: 'UNKNOWN',
    };
    expect(isSnapshot(correctlyUnavailable)).toBe(true);
  });

  it('reconciles CFTC metric, evidence-block, switch, and aggregate-source state', () => {
    const metricId = P1_CFTC_CONFIG[0].id;
    const wrongMetricDirection = structuredClone(makeSnapshot());
    wrongMetricDirection.metrics[metricId].context.direction = 'MORE_NET_SHORT';
    expect(isSnapshot(wrongMetricDirection)).toBe(false);

    const mismatchedEightWeekArtifacts = structuredClone(makeSnapshot());
    mismatchedEightWeekArtifacts.metrics[metricId].changes.eight_weeks = 9.99;
    expect(isSnapshot(mismatchedEightWeekArtifacts)).toBe(false);

    const mismatchedSampleSize = structuredClone(makeSnapshot());
    mismatchedSampleSize.metrics[metricId].quality.sample_size = 155;
    expect(isSnapshot(mismatchedSampleSize)).toBe(false);

    const positioningMutations: Array<[string, (snapshot: Snapshot) => void]> = [
      ['direction', (snapshot) => { snapshot.switches.market_ignition.evidence_blocks[1].direction = 'MORE_NET_LONG'; }],
      ['status', (snapshot) => { snapshot.switches.market_ignition.evidence_blocks[1].status = 'AVAILABLE'; }],
      ['confidence', (snapshot) => { snapshot.switches.market_ignition.evidence_blocks[1].confidence = 'HIGH'; }],
      ['switch confidence', (snapshot) => { snapshot.switches.market_ignition.confidence = 'HIGH'; }],
    ];
    for (const [field, mutate] of positioningMutations) {
      const inconsistent = structuredClone(makeSnapshot());
      mutate(inconsistent);
      expect(isSnapshot(inconsistent), field).toBe(false);
    }

    const sourceMutations: Array<[string, (snapshot: Snapshot) => void]> = [
      ['status', (snapshot) => {
        snapshot.sources.cftc_tff_futures_only.status = 'ERROR';
        snapshot.source_health.ok -= 1;
        snapshot.source_health.error += 1;
      }],
      ['freshness', (snapshot) => { snapshot.sources.cftc_tff_futures_only.freshness = 'LATE'; }],
      ['observation date', (snapshot) => { snapshot.sources.cftc_tff_futures_only.observation_date = '2026-08-10'; }],
      ['release', (snapshot) => { snapshot.sources.cftc_tff_futures_only.released_at = '2026-08-11T12:00:00Z'; }],
      ['expected next update', (snapshot) => { snapshot.sources.cftc_tff_futures_only.expected_next_update = '2026-08-14'; }],
    ];
    for (const [field, mutate] of sourceMutations) {
      const inconsistent = structuredClone(makeSnapshot());
      mutate(inconsistent);
      expect(isSnapshot(inconsistent), `CFTC source ${field}`).toBe(false);
    }

    const missingCftcSource = structuredClone(makeSnapshot());
    delete missingCftcSource.sources.cftc_tff_futures_only;
    missingCftcSource.source_health.ok -= 1;
    expect(isSnapshot(missingCftcSource)).toBe(false);

    const synchronizedDegraded = structuredClone(makeSnapshot());
    synchronizedDegraded.metrics[metricId].quality.status = 'STALE';
    synchronizedDegraded.metrics[metricId].quality.freshness = 'STALE';
    synchronizedDegraded.stale_count += 1;
    synchronizedDegraded.switches.market_ignition.available_blocks = 0;
    synchronizedDegraded.switches.market_ignition.confidence = 'UNKNOWN';
    synchronizedDegraded.switches.market_ignition.evidence_blocks[1] = {
      ...synchronizedDegraded.switches.market_ignition.evidence_blocks[1],
      available: false,
      status: 'UNAVAILABLE_FREE',
      direction: 'UNKNOWN',
      confidence: 'UNKNOWN',
    };
    synchronizedDegraded.sources.cftc_tff_futures_only.status = 'STALE';
    synchronizedDegraded.sources.cftc_tff_futures_only.freshness = 'STALE';
    synchronizedDegraded.source_health.ok -= 1;
    synchronizedDegraded.source_health.stale += 1;
    expect(isSnapshot(synchronizedDegraded)).toBe(true);
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
    expect(routeMetricIds('market-ignition', catalog, snapshot)).toEqual([
      ...P1_CFTC_CONFIG.map(({ id }) => id),
      ...P1_RIGHTS_GATED_IDS,
      ...P2_SERIES_IDS,
    ]);
    expect(routeMetricIds('fundamental-exit', catalog, snapshot)).toEqual(['hyperscaler_capex']);
    expect(routeMetricIds('market-ignition', [], snapshot)).toEqual([
      ...P1_CFTC_CONFIG.map(({ id }) => id),
      ...P1_RIGHTS_GATED_IDS,
      ...P2_SERIES_IDS,
    ]);
  });

  it('strictly validates the two-active/six-held P2 context contract without changing P1 severity', () => {
    const valid = makeSnapshot();
    expect(P2_ACTIVE_IDS).toHaveLength(2);
    expect(P2_HELD_IDS).toHaveLength(6);
    expect(valid.switches.market_ignition.assessment).toBeNull();
    expect(valid.overall_assessment).toBe(valid.switches.liquidity_fuel.assessment);
    expect(isSnapshot(valid)).toBe(true);

    const p2CannotRewriteOverall = structuredClone(valid);
    p2CannotRewriteOverall.overall_assessment = 'STRESS';
    expect(isSnapshot(p2CannotRewriteOverall)).toBe(false);

    const missingActive = structuredClone(valid);
    delete missingActive.metrics.nonfinancial_equities_gdp_proxy;
    expect(isSnapshot(missingActive)).toBe(false);

    const legacyAlias = structuredClone(valid);
    legacyAlias.metrics.buffett_indicator_proxy = structuredClone(valid.metrics.nonfinancial_equities_gdp_proxy);
    legacyAlias.metrics.buffett_indicator_proxy.metric_id = 'buffett_indicator_proxy';
    expect(isSnapshot(legacyAlias)).toBe(false);

    const missingMacroCore = structuredClone(valid);
    delete missingMacroCore.metrics.nonfinancial_equities_gdp_proxy.statistics.percentile_10y_sample_size;
    expect(isSnapshot(missingMacroCore)).toBe(false);

    const missingMacroComponentDate = structuredClone(valid);
    delete missingMacroComponentDate.metrics.nonfinancial_equities_gdp_proxy.context.gdp_observation_date;
    expect(isSnapshot(missingMacroComponentDate)).toBe(false);

    const valueMismatch = structuredClone(valid);
    valueMismatch.metrics.sec_form4_nonderivative_ps_count_ratio_20d.value = 9;
    expect(isSnapshot(valueMismatch)).toBe(false);

    const missingAuditStat = structuredClone(valid);
    delete missingAuditStat.metrics.sec_form4_nonderivative_ps_count_ratio_20d.statistics.amendments_review_count_20d;
    expect(isSnapshot(missingAuditStat)).toBe(false);

    const invalidCoverage = structuredClone(valid);
    invalidCoverage.metrics.sec_form4_nonderivative_ps_count_ratio_20d.statistics.dollar_coverage_rate_20d = 1.01;
    expect(isSnapshot(invalidCoverage)).toBe(false);

    const lowCoverageDollarPublication = structuredClone(valid);
    lowCoverageDollarPublication.metrics.sec_form4_nonderivative_ps_count_ratio_20d.statistics.dollar_ratio_5d = 0.01;
    expect(isSnapshot(lowCoverageDollarPublication)).toBe(false);

    const wrongSensitivity = structuredClone(valid);
    wrongSensitivity.metrics.sec_form4_nonderivative_ps_count_ratio_20d.context.ex_10b5_scope = 'ALL_UNKNOWN_EXCLUDED';
    expect(isSnapshot(wrongSensitivity)).toBe(false);

    const heldPublishesValue = structuredClone(valid);
    heldPublishesValue.metrics[P2_HELD_IDS[0]].value = 0;
    expect(isSnapshot(heldPublishesValue)).toBe(false);

    const heldClaimsAttempt = structuredClone(valid);
    heldClaimsAttempt.metrics[P2_HELD_IDS[0]].quality.last_attempt_at = '2026-08-12T12:00:00Z';
    expect(isSnapshot(heldClaimsAttempt)).toBe(false);

    const heldClaimsSource = structuredClone(valid);
    heldClaimsSource.metrics[P2_HELD_IDS[0]].source.source_id = 'permission_hold';
    expect(isSnapshot(heldClaimsSource)).toBe(false);

    const missingMacroSource = structuredClone(valid);
    delete missingMacroSource.sources.fred_nonfinancial_equities_gdp;
    missingMacroSource.source_health.ok -= 1;
    expect(isSnapshot(missingMacroSource)).toBe(false);

    const mismatchedSecSource = structuredClone(valid);
    mismatchedSecSource.sources.sec_form4_daily_index.observation_date = '2026-08-10';
    expect(isSnapshot(mismatchedSecSource)).toBe(false);
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
    expect(formatValue(12.345, 'percent_open_interest')).toBe('12.35% OI');
    expect(formatSignedDelta(-1.25, 'percent_open_interest')).toBe('-1.25% OI');
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
    expect(requested).toEqual([
      ...P1_CFTC_CONFIG.map(({ id }) => `/bubble/data/series/${id}.json`),
      ...P1_RIGHTS_GATED_IDS.map((id) => `/bubble/data/series/${id}.json`),
      ...P2_SERIES_IDS.map((id) => `/bubble/data/series/${id}.json`),
    ]);
    expect(result.errors).toHaveProperty('finra_margin_debt');
    expect(result.series.finra_margin_debt.observations).toEqual(snapshot.metrics.finra_margin_debt.short_series);
    expect(snapshotSeriesFallback(snapshot, 'sofr').schema_version).toBe(SCHEMA_VERSION);
  });

  it('uses canonical P1 and P2 paths when the manifest is unavailable', async () => {
    const snapshot = makeSnapshot();
    const requested: string[] = [];
    const fetcher = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input); requested.push(url);
      const id = /\/data\/series\/([^/]+)\.json$/.exec(url)?.[1] ?? '';
      return jsonResponse(makeSeriesFile(snapshot.metrics[id]));
    }) as unknown as typeof fetch;
    const result = await loadRouteSeries('/bubble/', 'market-ignition', snapshot, [], fetcher);
    expect(requested).toEqual([
      ...P1_CFTC_CONFIG.map(({ id }) => `/bubble/data/series/${id}.json`),
      ...P1_RIGHTS_GATED_IDS.map((id) => `/bubble/data/series/${id}.json`),
      ...P2_SERIES_IDS.map((id) => `/bubble/data/series/${id}.json`),
    ]);
    expect(getGlobalLatestDate(result.series)).toBe('2026-08-11');
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
