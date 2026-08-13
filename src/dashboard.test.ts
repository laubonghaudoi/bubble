import { describe, expect, it, vi } from 'vitest';
import {
  COLLECTOR_SOURCE_IDS,
  CONFIRMATION_SPREAD_IDS,
  OVERVIEW_SERIES_IDS,
  P1_CFTC_CONFIG,
  P1_RIGHTS_GATED_IDS,
  P2_ACTIVE_IDS,
  P2_HELD_IDS,
  P2_SERIES_IDS,
  P3_AUTOMATED_IDS,
  P3_EVIDENCE_BLOCK_IDS,
  P3_MANUAL_IDS,
  P3_METRIC_IDS,
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
import { jsonResponse, makeCatalog, makeManualEvidenceRecord, makeMetric, makeSeriesFile, makeSnapshot, makeSnapshotWithReviewedManualEvidence } from './test-fixtures';
import type { FundamentalCompanyDetail, Metric, Snapshot } from './types';

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

    expect(Object.keys(valid.sources).sort()).toEqual([...COLLECTOR_SOURCE_IDS].sort());
    const extraCollector = structuredClone(valid);
    extraCollector.sources.unreviewed_collector = {
      ...extraCollector.sources.nyfed_rates,
      collector_id: 'unreviewed_collector',
    };
    extraCollector.source_health.ok += 1;
    expect(isSnapshot(extraCollector)).toBe(false);

    const missingCollector = structuredClone(valid);
    delete missingCollector.sources.treasury_auctions;
    missingCollector.source_health.ok -= 1;
    expect(isSnapshot(missingCollector)).toBe(false);

    const mismatchedCollectorIdentity = structuredClone(valid);
    mismatchedCollectorIdentity.sources.fred_iorb.collector_id = 'fred_h41';
    expect(isSnapshot(mismatchedCollectorIdentity)).toBe(false);

    const invalidStatistic = structuredClone(valid) as unknown as Record<string, unknown>;
    ((invalidStatistic.metrics as Record<string, Record<string, unknown>>).sofr.statistics as Record<string, unknown>).trend = 'up';
    expect(isSnapshot(invalidStatistic)).toBe(false);

    const existingNonP3Details = structuredClone(valid);
    existingNonP3Details.metrics.on_rrp_accepted.details = {
      submitted_usd_bn: 0,
      counterparties: 12,
    };
    expect(isSnapshot(existingNonP3Details)).toBe(true);
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
    expect(parseRoute('#/provenance')).toBe('provenance');
    expect(parseRoute('#/provenance/')).toBe('provenance');
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
    expect(routeMetricIds('fundamental-exit', catalog, snapshot)).toEqual(P3_METRIC_IDS);
    expect(routeMetricIds('provenance', catalog, snapshot)).toEqual([]);
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

  it('strictly validates canonical P3 evidence-only metrics, details, and 12-quarter history', () => {
    const valid = makeSnapshot();
    expect(P3_AUTOMATED_IDS).toEqual([
      'hyperscaler_aggregate_cash_capex',
      'hyperscaler_aggregate_cash_capex_yoy_acceleration_pp',
    ]);
    expect(P3_MANUAL_IDS).toEqual([
      'ai_upstream_orders_backlog',
      'customer_prepayments_contract_commitments',
      'take_or_pay_commitments',
    ]);
    expect(valid.switches.fundamental_exit).toMatchObject({
      mode: 'EVIDENCE_ONLY', assessment: null, available_blocks: 2, total_blocks: 4, confidence: 'LOW',
    });
    expect(valid.switches.fundamental_exit.evidence_blocks.map(({ id }) => id)).toEqual(P3_EVIDENCE_BLOCK_IDS);
    expect(valid.overall_assessment).toBe(valid.switches.liquidity_fuel.assessment);
    expect(valid.switches.market_ignition.assessment).toBeNull();
    expect(isSnapshot(valid)).toBe(true);

    const severity = structuredClone(valid);
    severity.switches.fundamental_exit.assessment = 'WATCH';
    expect(isSnapshot(severity)).toBe(false);

    const triggered = structuredClone(valid);
    triggered.switches.fundamental_exit.evidence_blocks[0].triggered = true;
    expect(isSnapshot(triggered)).toBe(false);

    const severityStatus = structuredClone(valid);
    severityStatus.switches.fundamental_exit.evidence_blocks[0].status = 'WATCH';
    expect(isSnapshot(severityStatus)).toBe(false);

    const extraSwitchField = structuredClone(valid);
    (extraSwitchField.switches.fundamental_exit as unknown as Record<string, unknown>).severity = 'WATCH';
    expect(isSnapshot(extraSwitchField)).toBe(false);

    const extraBlockField = structuredClone(valid);
    (extraBlockField.switches.fundamental_exit.evidence_blocks[0] as unknown as Record<string, unknown>).severity = null;
    expect(isSnapshot(extraBlockField)).toBe(false);

    const missingBlockField = structuredClone(valid);
    delete (missingBlockField.switches.fundamental_exit.evidence_blocks[0] as unknown as Record<string, unknown>).summary;
    expect(isSnapshot(missingBlockField)).toBe(false);

    const missingCanonicalMetric = structuredClone(valid);
    delete missingCanonicalMetric.metrics.hyperscaler_aggregate_cash_capex;
    expect(isSnapshot(missingCanonicalMetric)).toBe(false);

    const legacyAlias = structuredClone(valid);
    legacyAlias.metrics.hyperscaler_capex = structuredClone(valid.metrics.hyperscaler_aggregate_cash_capex);
    legacyAlias.metrics.hyperscaler_capex.metric_id = 'hyperscaler_capex';
    expect(isSnapshot(legacyAlias)).toBe(false);

    const missingStatistic = structuredClone(valid);
    delete missingStatistic.metrics.hyperscaler_aggregate_cash_capex.statistics.qoq_acceleration_pp;
    expect(isSnapshot(missingStatistic)).toBe(false);

    const extraStatistic = structuredClone(valid);
    extraStatistic.metrics.hyperscaler_aggregate_cash_capex.statistics.unreviewed_extra = 1;
    expect(isSnapshot(extraStatistic)).toBe(false);

    const extraAutomatedMetricField = structuredClone(valid);
    (extraAutomatedMetricField.metrics.hyperscaler_aggregate_cash_capex as unknown as Record<string, unknown>)
      .assessment = null;
    expect(isSnapshot(extraAutomatedMetricField)).toBe(false);

    const missingAutomatedProvenance = structuredClone(valid);
    delete (missingAutomatedProvenance.metrics.hyperscaler_aggregate_cash_capex as unknown as Record<string, unknown>)
      .provenance;
    expect(isSnapshot(missingAutomatedProvenance)).toBe(false);

    const extraAutomatedProvenance = structuredClone(valid);
    extraAutomatedProvenance.metrics.hyperscaler_aggregate_cash_capex.provenance!.push({
      ...extraAutomatedProvenance.metrics.hyperscaler_aggregate_cash_capex.source,
    });
    expect(isSnapshot(extraAutomatedProvenance)).toBe(false);

    const mismatchedAutomatedProvenance = structuredClone(valid);
    mismatchedAutomatedProvenance.metrics.hyperscaler_aggregate_cash_capex.provenance![0].retrieved_at = null;
    expect(isSnapshot(mismatchedAutomatedProvenance)).toBe(false);

    const capexValueMismatch = structuredClone(valid);
    capexValueMismatch.metrics.hyperscaler_aggregate_cash_capex.value = 0;
    expect(isSnapshot(capexValueMismatch)).toBe(false);

    const accelerationValueMismatch = structuredClone(valid);
    accelerationValueMismatch.metrics.hyperscaler_aggregate_cash_capex_yoy_acceleration_pp.value = 0;
    expect(isSnapshot(accelerationValueMismatch)).toBe(false);

    const tooShort = structuredClone(valid);
    for (const id of P3_AUTOMATED_IDS) {
      tooShort.metrics[id].short_series = tooShort.metrics[id].short_series.slice(-11);
    }
    expect(isSnapshot(tooShort)).toBe(false);

    const malformedMapping = structuredClone(valid) as unknown as Record<string, unknown>;
    const malformedMetrics = malformedMapping.metrics as Record<string, Metric>;
    delete (malformedMetrics.hyperscaler_aggregate_cash_capex.details!.fundamental!.companies[0] as unknown as Record<string, unknown>).accession;
    expect(isSnapshot(malformedMapping)).toBe(false);

    const mutateMicrosoft = (snapshot: Snapshot, mutation: (company: FundamentalCompanyDetail) => void) => {
      for (const id of P3_AUTOMATED_IDS) {
        const company = snapshot.metrics[id].details!.fundamental!.companies
          .find(({ company_id }) => company_id === 'microsoft')!;
        mutation(company);
      }
    };
    const wrongQuarterization = structuredClone(valid);
    mutateMicrosoft(wrongQuarterization, (company) => { company.quarterization_method = 'Q1_YTD'; });
    expect(isSnapshot(wrongQuarterization)).toBe(false);

    const wrongFiscalForm = structuredClone(valid);
    mutateMicrosoft(wrongFiscalForm, (company) => { company.form = '10-Q'; });
    expect(isSnapshot(wrongFiscalForm)).toBe(false);

    const wrongFinanceQuarterization = structuredClone(valid);
    mutateMicrosoft(wrongFinanceQuarterization, (company) => { company.finance_lease_quarterization_method = 'H1_MINUS_Q1'; });
    expect(isSnapshot(wrongFinanceQuarterization)).toBe(false);

    const extraCompanyField = structuredClone(valid);
    mutateMicrosoft(extraCompanyField, (company) => {
      (company as unknown as Record<string, unknown>).schema_drift = true;
    });
    expect(isSnapshot(extraCompanyField)).toBe(false);

    const missingCompanyDate = structuredClone(valid);
    mutateMicrosoft(missingCompanyDate, (company) => {
      delete (company as unknown as Record<string, unknown>).date;
    });
    expect(isSnapshot(missingCompanyDate)).toBe(false);

    const mismatchedCompanyDate = structuredClone(valid);
    mutateMicrosoft(mismatchedCompanyDate, (company) => { company.date = '2026-03-31'; });
    expect(isSnapshot(mismatchedCompanyDate)).toBe(false);

    const mismatchedFinanceAccession = structuredClone(valid);
    mutateMicrosoft(mismatchedFinanceAccession, (company) => {
      company.finance_lease_accession = '0001193125-26-999999';
    });
    expect(isSnapshot(mismatchedFinanceAccession)).toBe(false);

    const partialNullFinanceLease = structuredClone(valid);
    for (const id of P3_AUTOMATED_IDS) {
      const alphabet = partialNullFinanceLease.metrics[id].details!.fundamental!.companies
        .find(({ company_id }) => company_id === 'alphabet')!;
      alphabet.finance_lease_tag = 'RightOfUseAssetObtainedInExchangeForFinanceLeaseLiability';
    }
    expect(isSnapshot(partialNullFinanceLease)).toBe(false);

    const filedNextUtcDay = structuredClone(valid);
    mutateMicrosoft(filedNextUtcDay, (company) => { company.filed_at = '2026-07-31'; });
    expect(isSnapshot(filedNextUtcDay)).toBe(true);

    const filingAcceptanceGap = structuredClone(valid);
    mutateMicrosoft(filingAcceptanceGap, (company) => { company.filed_at = '2026-08-01'; });
    expect(isSnapshot(filingAcceptanceGap)).toBe(false);

    const filedBeforeContextEnd = structuredClone(valid);
    mutateMicrosoft(filedBeforeContextEnd, (company) => { company.filed_at = '2026-06-29'; });
    expect(isSnapshot(filedBeforeContextEnd)).toBe(false);

    const acceptedBeforeContextEnd = structuredClone(valid);
    mutateMicrosoft(acceptedBeforeContextEnd, (company) => {
      company.filed_at = '2026-06-30';
      company.accepted_at = '2026-06-29T23:59:59Z';
    });
    expect(isSnapshot(acceptedBeforeContextEnd)).toBe(false);

    const futureAcceptance = structuredClone(valid);
    mutateMicrosoft(futureAcceptance, (company) => {
      company.filed_at = '2027-01-01';
      company.accepted_at = '2027-01-01T00:00:00Z';
    });
    expect(isSnapshot(futureAcceptance)).toBe(false);

    const breadthMismatch = structuredClone(valid);
    breadthMismatch.metrics.hyperscaler_aggregate_cash_capex.details!.fundamental!.company_breadth = 2;
    expect(isSnapshot(breadthMismatch)).toBe(false);

    const automatedAgentAccession = structuredClone(valid);
    for (const id of P3_AUTOMATED_IDS) {
      const microsoft = automatedAgentAccession.metrics[id].details!.fundamental!.companies
        .find(({ company_id }) => company_id === 'microsoft')!;
      microsoft.accession = '0001193125-26-323660';
      microsoft.finance_lease_accession = '0001193125-26-323660';
      microsoft.filing_url = 'https://www.sec.gov/Archives/edgar/data/789019/000119312526323660/msft-20260630.htm';
    }
    expect(isSnapshot(automatedAgentAccession)).toBe(true);
    expect(valid.metrics.hyperscaler_aggregate_cash_capex.quality.sample_size).toBe(12);
    expect(valid.metrics.hyperscaler_aggregate_cash_capex_yoy_acceleration_pp.quality.sample_size).toBe(7);

    const atomicStateMutations: Array<[string, (metric: Metric) => void]> = [
      ['status', (metric) => { metric.quality.status = 'STALE'; }],
      ['freshness', (metric) => { metric.quality.freshness = 'STALE'; }],
      ['last attempt', (metric) => { metric.quality.last_attempt_at = '2026-08-11T17:32:49Z'; }],
      ['last success', (metric) => { metric.quality.last_success_at = '2026-08-11T17:32:49Z'; }],
      ['failure reason', (metric) => { metric.quality.failure_reason = 'one endpoint failed'; }],
      ['context confidence', (metric) => { metric.context.confidence = 'LOW'; }],
    ];
    for (const [field, mutate] of atomicStateMutations) {
      const nonAtomic = structuredClone(valid);
      mutate(nonAtomic.metrics.hyperscaler_aggregate_cash_capex_yoy_acceleration_pp);
      expect(isSnapshot(nonAtomic), field).toBe(false);
    }

    const reviewedZero = makeSnapshotWithReviewedManualEvidence();
    expect(reviewedZero.metrics.ai_upstream_orders_backlog.value).toBeNull();
    expect(reviewedZero.metrics.ai_upstream_orders_backlog.details!.manual_evidence!.records[0].value).toBe(0);
    expect(reviewedZero.switches.fundamental_exit).toMatchObject({ available_blocks: 3, confidence: 'MEDIUM', assessment: null });
    expect(isSnapshot(reviewedZero)).toBe(true);

    const extraActiveManualMetricField = structuredClone(reviewedZero);
    (extraActiveManualMetricField.metrics.ai_upstream_orders_backlog as unknown as Record<string, unknown>)
      .severity = 'WATCH';
    expect(isSnapshot(extraActiveManualMetricField)).toBe(false);

    const manualAgentAccession = makeSnapshotWithReviewedManualEvidence('ai_upstream_orders_backlog', {
      filing_accession: '0001193125-26-323660',
      source_url: 'https://www.sec.gov/Archives/edgar/data/789019/000119312526323660/msft-20260630.htm',
    });
    expect(isSnapshot(manualAgentAccession)).toBe(true);

    const noUnitForTrueZero = structuredClone(reviewedZero);
    noUnitForTrueZero.metrics.ai_upstream_orders_backlog.details!.manual_evidence!.records[0].unit = null;
    expect(isSnapshot(noUnitForTrueZero)).toBe(false);

    const manualRecordMutations: Array<[string, (record: ReturnType<typeof makeManualEvidenceRecord>) => void]> = [
      ['source type', (record) => { record.source_type = 'PRESS RELEASE'; }],
      ['unit', (record) => { record.unit = 'USD thousands'; }],
      ['negative value', (record) => { record.value = -1; }],
      ['wrong issuer URL', (record) => {
        record.source_url = 'https://www.sec.gov/Archives/edgar/data/1652044/000078901926123456/msft-20260630.htm';
      }],
      ['issuer-host URL', (record) => {
        record.source_url = 'https://www.microsoft.com/Archives/edgar/data/789019/000078901926123456/msft-20260630.htm';
      }],
      ['SEC subdomain URL', (record) => {
        record.source_url = 'https://data.sec.gov/Archives/edgar/data/789019/000078901926123456/msft-20260630.htm';
      }],
      ['explicit port URL', (record) => {
        record.source_url = 'https://www.sec.gov:443/Archives/edgar/data/789019/000078901926123456/msft-20260630.htm';
      }],
      ['query URL', (record) => { record.source_url += '?output=1'; }],
      ['fragment URL', (record) => { record.source_url += '#evidence'; }],
      ['non-HTML URL', (record) => {
        record.source_url = 'https://www.sec.gov/Archives/edgar/data/789019/000078901926123456/msft-20260630.txt';
      }],
      ['nested filing URL', (record) => {
        record.source_url = 'https://www.sec.gov/Archives/edgar/data/789019/000078901926123456/nested/msft-20260630.htm';
      }],
    ];
    for (const [field, mutate] of manualRecordMutations) {
      const invalidManual = structuredClone(reviewedZero);
      mutate(invalidManual.metrics.ai_upstream_orders_backlog.details!.manual_evidence!.records[0]);
      expect(isSnapshot(invalidManual), field).toBe(false);
    }

    const directionMismatch = structuredClone(reviewedZero);
    directionMismatch.switches.fundamental_exit.evidence_blocks[1].direction = 'UP';
    expect(isSnapshot(directionMismatch)).toBe(false);

    const networkEnabledManual = structuredClone(reviewedZero);
    networkEnabledManual.metrics.ai_upstream_orders_backlog.details!.manual_evidence!.network_enabled = true as false;
    expect(isSnapshot(networkEnabledManual)).toBe(false);

    const manualReadyClaimsUpdate = structuredClone(valid);
    manualReadyClaimsUpdate.metrics.ai_upstream_orders_backlog.updated_at = '2026-08-12T12:00:00Z';
    expect(isSnapshot(manualReadyClaimsUpdate)).toBe(false);

    expect(valid.metrics.ai_upstream_orders_backlog.details).toBeUndefined();
    expect(valid.metrics.ai_upstream_orders_backlog.provenance).toEqual([
      valid.metrics.ai_upstream_orders_backlog.source,
    ]);
    expect(valid.metrics.ai_upstream_orders_backlog.changes).toEqual({
      one_observation: null,
      five_observations: null,
      twenty_observations: null,
      eight_weeks: null,
      twelve_weeks: null,
      one_quarter: null,
    });
    const manualReadyWithNullDetails = structuredClone(valid);
    manualReadyWithNullDetails.metrics.ai_upstream_orders_backlog.details = null;
    expect(isSnapshot(manualReadyWithNullDetails)).toBe(false);
    const extraManualReadyMetricField = structuredClone(valid);
    (extraManualReadyMetricField.metrics.ai_upstream_orders_backlog as unknown as Record<string, unknown>)
      .unknown = true;
    expect(isSnapshot(extraManualReadyMetricField)).toBe(false);
    const missingManualChange = structuredClone(valid);
    delete missingManualChange.metrics.ai_upstream_orders_backlog.changes.twenty_observations;
    expect(isSnapshot(missingManualChange)).toBe(false);
    const nonNullManualChange = structuredClone(valid);
    nonNullManualChange.metrics.ai_upstream_orders_backlog.changes.eight_weeks = 0;
    expect(isSnapshot(nonNullManualChange)).toBe(false);
    const extraManualChange = structuredClone(valid);
    (extraManualChange.metrics.ai_upstream_orders_backlog.changes as unknown as Record<string, unknown>)
      .one_year = null;
    expect(isSnapshot(extraManualChange)).toBe(false);
    const activeManualWithNullDetails = structuredClone(reviewedZero);
    activeManualWithNullDetails.metrics.ai_upstream_orders_backlog.details = null;
    expect(isSnapshot(activeManualWithNullDetails)).toBe(false);

    const staleManual = makeSnapshotWithReviewedManualEvidence('ai_upstream_orders_backlog', {
      period_end: '2026-03-31',
      filing_accepted_at: '2026-04-12T20:15:00Z',
      as_of: '2026-04-13',
      reviewed_at: '2026-04-14T12:00:00Z',
    });
    expect(isSnapshot(staleManual)).toBe(false);
    staleManual.metrics.ai_upstream_orders_backlog.quality.status = 'STALE';
    staleManual.metrics.ai_upstream_orders_backlog.quality.freshness = 'STALE';
    staleManual.metrics.ai_upstream_orders_backlog.context.confidence = 'UNKNOWN';
    staleManual.stale_count += 1;
    staleManual.switches.fundamental_exit.evidence_blocks[1] = {
      ...staleManual.switches.fundamental_exit.evidence_blocks[1],
      available: false,
      status: 'STALE',
      direction: 'UNKNOWN',
      confidence: 'UNKNOWN',
    };
    staleManual.switches.fundamental_exit.available_blocks = 2;
    staleManual.switches.fundamental_exit.confidence = 'LOW';
    expect(isSnapshot(staleManual)).toBe(true);

    const exactBoundary = makeSnapshotWithReviewedManualEvidence('ai_upstream_orders_backlog', {
      period_end: '2026-03-31',
      filing_accepted_at: '2026-04-13T20:15:00Z',
      as_of: '2026-04-14',
      reviewed_at: '2026-04-15T12:00:00Z',
    });
    exactBoundary.generated_at = '2026-08-13T03:59:59Z';
    expect(isSnapshot(exactBoundary), '120 days at New York 23:59 remains fresh').toBe(true);
    const afterNewYorkMidnight = structuredClone(exactBoundary);
    afterNewYorkMidnight.generated_at = '2026-08-13T04:00:00Z';
    expect(isSnapshot(afterNewYorkMidnight), '121 days after New York midnight must be stale').toBe(false);
    afterNewYorkMidnight.metrics.ai_upstream_orders_backlog.quality.status = 'STALE';
    afterNewYorkMidnight.metrics.ai_upstream_orders_backlog.quality.freshness = 'STALE';
    afterNewYorkMidnight.metrics.ai_upstream_orders_backlog.context.confidence = 'UNKNOWN';
    afterNewYorkMidnight.stale_count += 1;
    afterNewYorkMidnight.switches.fundamental_exit.evidence_blocks[1] = {
      ...afterNewYorkMidnight.switches.fundamental_exit.evidence_blocks[1],
      available: false, status: 'STALE', direction: 'UNKNOWN', confidence: 'UNKNOWN',
    };
    afterNewYorkMidnight.switches.fundamental_exit.available_blocks = 2;
    afterNewYorkMidnight.switches.fundamental_exit.confidence = 'LOW';
    expect(isSnapshot(afterNewYorkMidnight)).toBe(true);

    const partialCommitments = makeSnapshotWithReviewedManualEvidence('customer_prepayments_contract_commitments');
    const staleTakeOrPay = makeSnapshotWithReviewedManualEvidence('take_or_pay_commitments', {
      period_end: '2026-03-31',
      filing_accepted_at: '2026-04-12T20:15:00Z',
      as_of: '2026-04-13',
      reviewed_at: '2026-04-14T12:00:00Z',
    });
    partialCommitments.metrics.take_or_pay_commitments = staleTakeOrPay.metrics.take_or_pay_commitments;
    partialCommitments.metrics.take_or_pay_commitments.quality.status = 'STALE';
    partialCommitments.metrics.take_or_pay_commitments.quality.freshness = 'STALE';
    partialCommitments.metrics.take_or_pay_commitments.context.confidence = 'UNKNOWN';
    partialCommitments.active_free_count += 1;
    partialCommitments.manual_ready_count -= 1;
    partialCommitments.stale_count += 1;
    partialCommitments.switches.fundamental_exit.evidence_blocks[2] = {
      ...partialCommitments.switches.fundamental_exit.evidence_blocks[2],
      available: false, status: 'STALE', direction: 'UNKNOWN', confidence: 'UNKNOWN',
    };
    partialCommitments.switches.fundamental_exit.available_blocks = 2;
    partialCommitments.switches.fundamental_exit.confidence = 'LOW';
    expect(isSnapshot(partialCommitments)).toBe(true);

    const partialCommitmentsClaimAvailable = structuredClone(partialCommitments);
    partialCommitmentsClaimAvailable.switches.fundamental_exit.evidence_blocks[2] = {
      ...partialCommitmentsClaimAvailable.switches.fundamental_exit.evidence_blocks[2],
      available: true, status: 'DOWN', direction: 'DOWN', confidence: 'MEDIUM',
    };
    partialCommitmentsClaimAvailable.switches.fundamental_exit.available_blocks = 3;
    partialCommitmentsClaimAvailable.switches.fundamental_exit.confidence = 'MEDIUM';
    expect(isSnapshot(partialCommitmentsClaimAvailable)).toBe(false);
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
  it('loads the five canonical P3 series and validates enriched CapEx history independently', async () => {
    const snapshot = makeSnapshot();
    const catalog = makeCatalog();
    const requested: string[] = [];
    const fetcher = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input); requested.push(url);
      const id = /\/data\/series\/([^/]+)\.json$/.exec(url)?.[1] ?? '';
      const file = makeSeriesFile(snapshot.metrics[id]);
      if (id === 'hyperscaler_aggregate_cash_capex_yoy_acceleration_pp') {
        file.observations = file.observations.slice(-11);
      }
      return jsonResponse(file);
    }) as unknown as typeof fetch;
    const result = await loadRouteSeries('/bubble/', 'fundamental-exit', snapshot, catalog, fetcher);
    expect(requested).toEqual(P3_METRIC_IDS.map((id) => `/bubble/data/series/${id}.json`));
    expect(result.errors).toHaveProperty('hyperscaler_aggregate_cash_capex_yoy_acceleration_pp');
    expect(result.series.hyperscaler_aggregate_cash_capex.observations).toHaveLength(12);
    expect(result.series.hyperscaler_aggregate_cash_capex_yoy_acceleration_pp.observations)
      .toEqual(snapshot.metrics.hyperscaler_aggregate_cash_capex_yoy_acceleration_pp.short_series);
    expect(result.errors).not.toHaveProperty('ai_upstream_orders_backlog');
  });

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
