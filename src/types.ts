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

export interface MetricChanges {
  one_observation: number | null;
  five_observations: number | null;
  twenty_observations?: number | null;
  one_week?: number | null;
  four_weeks?: number | null;
  one_month?: number | null;
  one_quarter?: number | null;
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
}

export interface EvidenceBlock {
  id: string;
  label: string;
  available: boolean;
  triggered: boolean | null;
  status: string;
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

export interface Snapshot {
  schema_version: '2.0.0';
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
