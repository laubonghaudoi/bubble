export type Availability =
  | 'ACTIVE_FREE'
  | 'ACTIVE_PROXY'
  | 'MANUAL_READY'
  | 'UNAVAILABLE_FREE';

export type HealthStatus =
  | 'OK'
  | 'STALE'
  | 'ERROR'
  | 'NOT_RELEASED_YET'
  | 'NOT_APPLICABLE';

export type Freshness = 'FRESH' | 'LATE' | 'STALE' | 'UNKNOWN';
export type Phase = 'P0' | 'P1' | 'P2' | 'P3';
export type Layer = 'liquidity_fuel' | 'market_ignition' | 'fundamental_exit';

export interface Point {
  date: string;
  value: number | null;
}

export interface SrfPoint extends Point {
  accepted_amount_usd_bn: number;
  alert_eligible_accepted_amount_usd_bn: number;
  exercise_accepted_amount_usd_bn: number;
  has_technical_exercise: boolean;
  technical_exercise: boolean;
  classification_complete: true;
}

export type FundamentalDirection =
  | 'ACCELERATING'
  | 'DECELERATING'
  | 'FLAT'
  | 'UNKNOWN';

export interface FundamentalCompanyDetail {
  date: string;
  company_id: string;
  ticker: string;
  cik: string;
  fiscal_quarter: string;
  calendar_period_end: string;
  cash_capex_usd_bn: number;
  qoq_percent_change: number | null;
  yoy_percent_change: number | null;
  qoq_acceleration_pp: number | null;
  yoy_acceleration_pp: number | null;
  direction: FundamentalDirection;
  tag: string;
  namespace: string;
  unit: string;
  accession: string;
  form: string;
  filed_at: string;
  accepted_at: string;
  filing_url: string;
  frame: string | null;
  context_start: string;
  context_end: string;
  quarterization_method: string;
  manual_review_required: boolean;
  finance_lease_additions_usd_bn: number | null;
  finance_lease_tag: string | null;
  finance_lease_accession: string | null;
  finance_lease_quarterization_method: string | null;
}

export interface FundamentalMetricDetail {
  aggregate_direction: FundamentalDirection;
  company_breadth: number;
  company_total: 4;
  companies: FundamentalCompanyDetail[];
  caveats: string[];
}

export interface FundamentalSeriesPoint extends Point {
  aggregate_cash_capex_usd_bn: number | null;
  qoq_percent_change: number | null;
  yoy_percent_change: number | null;
  qoq_acceleration_pp: number | null;
  yoy_acceleration_pp: number | null;
  aggregate_direction: FundamentalDirection;
  company_breadth: number;
  company_total: number;
  company_breadth_ratio: number | null;
  finance_lease_disclosure_breadth: number;
  manual_review_count: number;
  companies: FundamentalCompanyDetail[];
}

export type ManualDirection = 'UP' | 'FLAT' | 'DOWN' | 'MIXED' | 'UNKNOWN';

export interface ManualEvidenceRecord {
  company_id: string;
  period_end: string;
  metric_id: string;
  direction: Exclude<ManualDirection, 'MIXED'>;
  value: number | null;
  unit: string | null;
  yoy_pct: number | null;
  comparable: boolean;
  source_type: string;
  source_url: string;
  filing_accession: string;
  filing_accepted_at: string;
  as_of: string;
  reviewer: string;
  reviewed_at: string;
  paraphrase: string;
  review_note: string;
}

export interface ManualEvidenceDetail {
  source_id: 'manual_public_filings';
  network_enabled: false;
  observation_date: string;
  direction: ManualDirection;
  record_count: number;
  company_count: number;
  comparable_count: number;
  latest_filing_accepted_at: string;
  latest_reviewed_at: string;
  records: ManualEvidenceRecord[];
}

export interface ManualEvidenceSeriesPoint extends Point {
  record_count: number;
  company_count: number;
  comparable_count: number;
  direction: ManualDirection;
  records: ManualEvidenceRecord[];
}

export interface MetricDetails {
  [key: string]: unknown;
  fundamental?: FundamentalMetricDetail;
  manual_evidence?: ManualEvidenceDetail;
}

export interface MetricChanges {
  one_observation: number | null;
  five_observations: number | null;
  twenty_observations?: number | null;
  one_week?: number | null;
  four_weeks?: number | null;
  one_month?: number | null;
  one_quarter?: number | null;
  eight_weeks?: number | null;
  twelve_weeks?: number | null;
}

export interface QualityInfo {
  status: HealthStatus;
  freshness: Freshness;
  last_attempt_at: string | null;
  last_success_at: string | null;
  failure_reason: string | null;
  sample_size: number | null;
}

export interface MetricContext {
  technical_flags: string[];
  is_proxy: boolean;
  confidence: string;
  direction?: string;
  equity_observation_date?: string | null;
  gdp_observation_date?: string | null;
  common_quarter?: string | null;
  window_start_5d?: string | null;
  window_end_5d?: string | null;
  window_start_20d?: string | null;
  window_end_20d?: string | null;
  dollar_status_5d?: string | null;
  dollar_status_20d?: string | null;
  ex_10b5_scope?: string | null;
}

export interface MetricSource {
  source_id?: string | null;
  name: string | null;
  url: string | null;
  tier: string | null;
  retrieved_at: string | null;
  rights_note: string;
}

export interface Methodology {
  question: string;
  definition: string;
  why_it_matters: string;
  direction: string;
  calculation: string;
  frequency_and_lag: string;
  common_misreads: string;
  technical_distortions: string;
  confirm_with: string[];
  cannot_infer: string;
  source_and_license_note: string;
  proxy_disclosure: string;
}

export interface Metric {
  metric_id: string;
  label: string;
  availability: Availability;
  value: number | null;
  unit: string;
  frequency: string;
  observation_date: string | null;
  released_at: string | null;
  updated_at: string | null;
  expected_next_update: string | null;
  changes: MetricChanges;
  statistics: Record<string, number | null>;
  quality: QualityInfo;
  context: MetricContext;
  source: MetricSource;
  methodology: Methodology;
  short_series: Point[];
  provenance?: MetricSource[];
  unavailability_reason?: string | null;
  details?: MetricDetails | null;
}

export interface EvidenceBlock {
  id: string;
  label: string;
  available: boolean;
  triggered: boolean | null;
  status: string;
  direction: string;
  confidence: string;
  summary: string;
}

export interface SwitchState {
  mode: string;
  assessment: string | null;
  available_blocks: number;
  total_blocks: number;
  confidence: string;
  evidence_blocks: EvidenceBlock[];
  summary: string;
}

export interface TechnicalContext {
  date: string;
  flags: string[];
  note: string;
}

export interface ExplanationBullet {
  metric_id: string;
  observation: string;
  meaning: string;
  alternative: string;
  confirmation: string;
  judgment: string;
  confidence: string;
}

export interface CollectorSource {
  collector_id?: string;
  name: string;
  url: string | null;
  tier: string | null;
  rights_note: string;
  status: HealthStatus;
  freshness: Freshness;
  observation_date: string | null;
  released_at: string | null;
  updated_at: string | null;
  last_attempt_at: string | null;
  last_success_at: string | null;
  expected_next_update: string | null;
  failure_reason: string | null;
}

export interface SourceHealthCounts {
  ok: number;
  stale: number;
  error: number;
  not_released_yet: number;
  not_applicable: number;
}

export type VideoP0Status =
  | 'GREEN'
  | 'YELLOW'
  | 'RED'
  | 'EXTREME_CONTEXT_REQUIRED'
  | 'EXTREME_CONFIRMED'
  | 'UNAVAILABLE';

export type VideoP0DataStatus =
  | 'CURRENT'
  | 'LAST_GOOD'
  | 'PARTIAL'
  | 'UNAVAILABLE';

export type DecisionConfidence = 'HIGH' | 'MEDIUM' | 'LOW' | 'UNKNOWN';
export type FormulaSourceKind =
  | 'VIDEO_SOURCE_RULE'
  | 'DASHBOARD_OPERATIONALIZATION'
  | 'MANUAL_CONTEXT';
export type FormulaNotationKind = FormulaSourceKind | 'MATHEMATICAL_NOTATION';
export type FormulaEvaluationState =
  | 'CURRENT'
  | 'LAST_GOOD'
  | 'STALE'
  | 'MISSING'
  | 'DISABLED'
  | 'REVIEW_REQUIRED';

export interface FormulaBasis {
  kind: FormulaSourceKind;
  label: string;
  source_segment_id: string | null;
  note: string;
}

export interface FormulaClause {
  clause_id: string;
  order: number;
  label: string;
  metric_id: string | null;
  operator: '>' | '>=' | '<' | '<=' | '=';
  threshold: number | string | boolean | null;
  threshold_unit: string | null;
  current_value: number | string | boolean | null;
  current_unit: string | null;
  met: boolean | null;
  observation_date: string | null;
  released_at: string | null;
  quality_status: HealthStatus;
  freshness: Freshness;
  evaluation_state: FormulaEvaluationState;
  basis: FormulaBasis[];
  note: string;
}

export interface FormulaEvaluation {
  expression: string;
  display_tex: string;
  plain_language: string;
  triggered: boolean | null;
  clauses: FormulaClause[];
}

export interface FormulaRoute {
  route_id: string;
  label: string;
  expression: string;
  triggered: boolean | null;
  clauses: FormulaClause[];
}

export interface FormulaNotationItem {
  key: string;
  symbol_tex: string;
  label: string;
  definition: string;
  unit: string | null;
  source_kind: FormulaNotationKind;
  note: string;
}

export interface VideoSourceSegment {
  segment_id: string;
  label: string;
  start_seconds: number;
  end_seconds: number;
  timestamp_url: string;
}

export interface VideoP0Thresholds {
  yellow: {
    spread_positive_bp: number;
    positive_streak_observations: number;
    reserve_usd_bn: number;
    reserve_change_4w_usd_bn: number;
    tga_operational_floor_usd_bn: number;
  };
  red: {
    spread_bp: number;
    reserve_usd_bn: number;
    srf_positive_days_required: number;
    srf_window_completed_days: number;
  };
  extreme: {
    reserve_usd_bn: number;
    decline_percentile: string;
  };
  tga_source_target_usd_bn: number;
}

export interface VideoP0CrisisContext {
  status: 'UNKNOWN' | 'MAJOR_CRISIS_PRESENT' | 'NO_MAJOR_CRISIS';
  as_of: string | null;
  reviewed_at: string | null;
  reviewer: string | null;
  note: string | null;
}

export interface VideoP0Model {
  model_id: 'henren778_p0_liquidity';
  label: string;
  enabled: boolean;
  status: VideoP0Status;
  data_status: VideoP0DataStatus;
  confidence: DecisionConfidence;
  availability_reason: string | null;
  evaluated_at: string;
  source: {
    title: string;
    display_title: string;
    author: string;
    url: string;
    segments: VideoSourceSegment[];
  };
  thresholds: VideoP0Thresholds;
  operationalizations: Record<string, string | number | boolean>;
  crisis_context: VideoP0CrisisContext;
  notation: FormulaNotationItem[];
  formulas: {
    yellow: FormulaEvaluation;
    red: FormulaEvaluation & { routes: FormulaRoute[] };
    extreme: FormulaEvaluation & {
      candidate: boolean | null;
      context_required: boolean;
    };
  };
  technical_flags: string[];
  notes: string[];
}

export interface Snapshot {
  schema_version: '2.2.0';
  generated_at: string;
  pipeline_updated_at: string;
  market_date: string | null;
  overall_assessment: string | null;
  switches: Record<Layer, SwitchState>;
  metrics: Record<string, Metric>;
  technical_context: TechnicalContext[];
  alerts: Array<{ level: string; title: string; detail: string }>;
  explanations: { headline: string; bullets: ExplanationBullet[] };
  source_health: SourceHealthCounts;
  decision_models: {
    p0_video_liquidity: VideoP0Model;
  };
  sources: Record<string, CollectorSource>;
  active_free_count: number;
  active_proxy_count: number;
  manual_ready_count: number;
  unavailable_free_count: number;
  stale_count: number;
}

export interface CatalogMetric {
  metric_id: string;
  label: string;
  unit: string;
  frequency: string;
  layer: Layer;
  phase: Phase;
  role: string;
  availability: Availability;
  series_path: string;
}
