import {
  type CSSProperties,
  type KeyboardEvent as ReactKeyboardEvent,
  type MutableRefObject,
  type MouseEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
} from 'react';
import type {
  Availability,
  CatalogMetric,
  CollectorSource,
  HealthStatus,
  Metric,
  Snapshot,
  SwitchState,
} from '../types';
import {
  AVAILABILITY_LABELS,
  CONFIRMATION_SPREAD_IDS,
  FRESHNESS_LABELS,
  HEALTH_LABELS,
  LIQUIDITY_MAIN_TABS,
  OVERVIEW_MAIN_TABS,
  P1_CFTC_CONFIG,
  P1_RIGHTS_GATED_IDS,
  P2_ACTIVE_IDS,
  P2_HELD_IDS,
  ROUTES,
  SWITCH_CONFIG,
  TAPE_GROUPS,
  THRESHOLD_BP,
  TICKERS,
  changePresentation,
  formatSignedDelta,
  formatUpdateTimestamp,
  formatValue,
  getGlobalLatestDate,
  type RangeKey,
  type RouteId,
  type SeriesMap,
  windowPoints,
} from '../dashboard';
import { MainMetricChart, OVERLAY_CONFIG, RateOverlayChart, Sparkline } from './Charts';

const TAPE_IDS = TAPE_GROUPS.flatMap(({ ids }) => [...ids]);
const BALANCE_IDS = ['fed_total_assets', 'reserve_balances', 'tga_daily', 'tga_weekly_h41'] as const;
const BALANCE_COLORS = ['var(--balance-1)', 'var(--balance-2)', 'var(--balance-3)', 'var(--balance-4)'];
const RANGES: RangeKey[] = ['1M', '8W', '12W', '3M', '1Y', 'MAX'];
const UNIT_LABEL: Record<string, string> = {
  bp: 'BASIS POINTS',
  percent: 'PERCENT',
  percent_open_interest: 'NET % OPEN INTEREST',
  'USD bn': 'USD BILLIONS',
};
const RESERVE_REFERENCE_LINES = [
  { value: 2900, label: '參考區 2.9T' },
  { value: 2800, label: '參考區 2.8T' },
  { value: 2500, label: '參考區 2.5T' },
] as const;
const LAST_GOOD_NOTE = '最後成功值，並非今日新值';

type StatusTone = 'positive' | 'neutral' | 'warning' | 'negative' | 'unavailable';

function statusTone(status: string | null | undefined): StatusTone {
  const value = status?.toUpperCase() ?? '';
  if (['OK', 'NORMAL', 'AMPLE', 'ACTIVE', 'FRESH', 'ACTIVE_FREE', 'ACTIVE_PROXY', 'RISING'].includes(value)) return 'positive';
  if (['NEUTRAL', 'UNKNOWN', 'NOT_APPLICABLE', 'FLAT'].includes(value)) return 'neutral';
  if (['WATCH', 'ELEVATED', 'PARTIAL', 'STALE', 'LATE', 'NOT_RELEASED_YET', 'MANUAL_READY', 'MIXED'].includes(value)) return 'warning';
  if (['TIGHTENING', 'WARNING', 'STRESS', 'ERROR', 'FALLING'].includes(value)) return 'negative';
  return 'unavailable';
}

function statusStyle(status: string | null | undefined): CSSProperties {
  const tone = statusTone(status);
  return { '--status-color': `var(--${tone})`, '--status-fg': `var(--${tone}-fg)` } as CSSProperties;
}

function deltaClass(value: number | null | undefined) {
  if (value == null) return 'is-missing';
  if (value === 0) return 'is-zero';
  return value > 0 ? 'is-positive' : 'is-negative';
}

function displayTimestamp(value: string | null | undefined) {
  if (!value) return '—';
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toISOString().replace('.000Z', 'Z');
}

function healthText(status: HealthStatus) {
  return HEALTH_LABELS[status] ?? status;
}

function evidenceDirectionLabel(direction: string) {
  return direction.replaceAll('_', '-');
}

function evidenceCardStyle(available: boolean, status: string, evidenceOnly: boolean): CSSProperties {
  if (!evidenceOnly) return statusStyle(status);
  return available
    ? { '--status-color': 'var(--action)', '--status-fg': 'var(--action)' } as CSSProperties
    : statusStyle('UNAVAILABLE');
}

function Badge({ status, label }: { status: string; label?: string }) {
  return <span className={`badge badge-${status.toLowerCase()}`} data-status={status} style={statusStyle(status)}>{label ?? status}</span>;
}

function valueState(metric: Metric | undefined): 'current' | 'last-good' | 'missing' {
  if (metric?.value == null) return 'missing';
  return metric.quality.status === 'OK' ? 'current' : 'last-good';
}

function isLastGood(metric: Metric | undefined) {
  return valueState(metric) === 'last-good';
}

function LastGoodTag({ status }: { status: HealthStatus }) {
  return <small className="last-good-tag" data-health={status} title={LAST_GOOD_NOTE} aria-label={LAST_GOOD_NOTE}>LAST-GOOD</small>;
}

function RouteNav({ route }: { route: RouteId }) {
  return (
    <nav className="route-nav" aria-label="Dashboard 頁面">
      {ROUTES.map((item) => (
        <a className={`route-link${item.id === route ? ' is-active' : ''}`} href={item.href} aria-current={item.id === route ? 'page' : undefined} key={item.id}>
          {item.label}
        </a>
      ))}
    </nav>
  );
}

function StatusBar({ snapshot, route, onOpenSources }: { snapshot: Snapshot; route: RouteId; onOpenSources: () => void }) {
  const health = snapshot.source_health;
  const total = health.ok + health.stale + health.error + health.not_released_yet + health.not_applicable;
  const p0Assessment = snapshot.overall_assessment ?? snapshot.switches.liquidity_fuel.assessment ?? snapshot.switches.liquidity_fuel.mode;
  const healthTone = health.error > 0 ? 'var(--negative)' : health.stale > 0 || health.not_released_yet > 0 ? 'var(--warning)' : 'var(--positive)';
  return (
    <>
      <header className="status-bar">
        <div className="brand"><span className="brand-mark">USD·LIQ</span><span className="brand-divider" aria-hidden="true" /><h1 className="brand-title">美元流動性監測</h1></div>
        <div className="status-cluster">
          <span className="status-item">MKT <strong>{snapshot.market_date ?? '—'}</strong></span>
          <span className="status-item">UPD <strong>{formatUpdateTimestamp(snapshot.pipeline_updated_at)}</strong></span>
          <button className="status-item source-status" onClick={onOpenSources} type="button" aria-label="查看來源與健康狀態">
            SRC <strong>{health.ok}/{total}</strong><span className="health-dot" style={{ '--health-color': healthTone } as CSSProperties} aria-hidden="true" />
          </button>
          <span className="overall-pill" style={statusStyle(p0Assessment)}>{String(p0Assessment).toUpperCase()}</span>
        </div>
      </header>
      <RouteNav route={route} />
    </>
  );
}

function onSwitchKeyDown(event: ReactKeyboardEvent<HTMLAnchorElement>, index: number, refs: MutableRefObject<Array<HTMLAnchorElement | null>>) {
  const keys = ['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', 'Home', 'End'];
  if (!keys.includes(event.key)) return;
  event.preventDefault();
  const last = SWITCH_CONFIG.length - 1;
  const next = event.key === 'Home' ? 0 : event.key === 'End' ? last
    : event.key === 'ArrowLeft' || event.key === 'ArrowUp' ? (index + last) % SWITCH_CONFIG.length
      : (index + 1) % SWITCH_CONFIG.length;
  refs.current[next]?.focus();
}

function SwitchStrip({ snapshot, route }: { snapshot: Snapshot; route: RouteId }) {
  const refs = useRef<Array<HTMLAnchorElement | null>>([]);
  return (
    <section className="switch-strip" aria-label="三個監測開關">
      {SWITCH_CONFIG.map((config, index) => {
        const value = snapshot.switches[config.id];
        const assessment = value.assessment ?? value.mode;
        const available = Math.max(0, Math.min(value.total_blocks, value.available_blocks));
        const total = Math.max(1, value.total_blocks);
        return (
          <a
            className={`switch-card switch-card-link${route === config.route ? ' is-current' : ''}`}
            href={`#/${config.route}`}
            key={config.id}
            style={statusStyle(assessment)}
            aria-label={`${config.title}，${assessment ?? '未能評估'}，${available}/${total} evidence blocks`}
            aria-current={route === config.route ? 'page' : undefined}
            ref={(node) => { refs.current[index] = node; }}
            onKeyDown={(event) => onSwitchKeyDown(event, index, refs)}
          >
            <div className="switch-head"><span className="switch-number">{config.num}</span><span className="switch-kicker">{config.kicker}</span><strong className="switch-status">{assessment ?? 'UNAVAILABLE'}</strong></div>
            <div className="switch-title-row">
              <h2>{config.title}</h2>
              <div className="meter" aria-hidden="true">{Array.from({ length: total }, (_, segment) => <span className={`meter-segment${segment < available ? ' is-filled' : ''}`} key={segment} />)}</div>
              <b className="switch-score">{available}/{total}</b>
            </div>
            <p className="switch-summary">{value.summary}</p>
            <div className="switch-confidence">CONFIDENCE {value.confidence.toUpperCase()}</div>
          </a>
        );
      })}
    </section>
  );
}

function LiveTape({ snapshot, series, selected, onSelect }: { snapshot: Snapshot; series: SeriesMap; selected: string; onSelect: (id: string) => void }) {
  const activeCount = TAPE_IDS.filter((id) => ['ACTIVE_FREE', 'ACTIVE_PROXY'].includes(snapshot.metrics[id]?.availability)).length;
  return (
    <section className="panel tape-panel" aria-labelledby="live-tape-title">
      <div className="panel-header" id="live-tape-title"><span>LIVE TAPE</span><span>{activeCount} ACTIVE</span></div>
      <div className="tape-head" aria-hidden="true"><span>METRIC</span><span>TREND</span><span>LAST</span><span>CHANGE</span></div>
      <div className="tape-scroll">
        {TAPE_GROUPS.map((group) => (
          <div className="tape-group" key={group.label}>
            <h3 className="tape-group-title">{group.label}</h3>
            {group.ids.map((id) => {
              const metric = snapshot.metrics[id];
              if (!metric) return null;
              const change = changePresentation(metric);
              const lastGood = isLastGood(metric);
              return (
                <button className={`tape-row${selected === id ? ' is-selected' : ''}${lastGood ? ' is-last-good' : ''}`} data-value-state={valueState(metric)} type="button" key={id} onClick={() => onSelect(id)} aria-pressed={selected === id} title={`${metric.label} · as-of ${metric.observation_date ?? '—'}${lastGood ? ` · ${LAST_GOOD_NOTE}` : ''}`}>
                  <span className="tape-label">{TICKERS[id] ?? metric.label}{metric.context.is_proxy ? <small className="proxy-mark">PROXY</small> : null}</span>
                  <Sparkline points={series[id]?.observations ?? metric.short_series} selected={selected === id} label={metric.label} lastGood={lastGood} />
                  <span className="tape-value-state"><strong className="tape-value">{formatValue(metric.value, metric.unit)}</strong>{lastGood ? <LastGoodTag status={metric.quality.status} /> : null}</span>
                  <span className={`tape-delta ${deltaClass(change.value)}`}><b>{formatSignedDelta(change.value, metric.unit)}</b><small>{change.label}</small></span>
                </button>
              );
            })}
          </div>
        ))}
      </div>
    </section>
  );
}

interface ChartPanelProps {
  snapshot: Snapshot;
  series: SeriesMap;
  main: string;
  range: RangeKey;
  overlay: Record<string, boolean>;
  tabs: ReadonlyArray<{ id: string; label: string }>;
  onMain: (id: string) => void;
  onRange: (range: RangeKey) => void;
  onOverlay: (id: string) => void;
}

function ChartPanel({ snapshot, series, main, range, overlay, tabs, onMain, onRange, onOverlay }: ChartPanelProps) {
  const fallbackId = tabs[0]?.id ?? 'sofr_iorb_spread_bp';
  const metric = snapshot.metrics[main] ?? snapshot.metrics[fallbackId];
  const metricId = metric.metric_id;
  const globalLatest = getGlobalLatestDate(series);
  const points = windowPoints(series[metricId]?.observations ?? metric.short_series, range, globalLatest);
  const overlaySeries = useMemo(() => Object.fromEntries(OVERLAY_CONFIG.filter(({ id }) => overlay[id]).map(({ id }) => [id, windowPoints(series[id]?.observations ?? snapshot.metrics[id]?.short_series ?? [], range, globalLatest)])), [globalLatest, overlay, range, series, snapshot.metrics]);
  const overlayLastGoodIds = useMemo(() => OVERLAY_CONFIG.flatMap(({ id }) => isLastGood(snapshot.metrics[id]) ? [id] : []), [snapshot.metrics]);
  const change = changePresentation(metric);
  const lastGood = isLastGood(metric);
  const referenceLines = metricId === 'reserve_balances' ? RESERVE_REFERENCE_LINES : [];
  return (
    <section className="panel chart-panel" aria-label="主要流動性圖表">
      <div className="chart-toolbar">
        <div className="tab-group" aria-label="主要指標">{tabs.map(({ id, label }) => <button className={`tab-button${metricId === id ? ' is-active' : ''}`} aria-label={`${label} 主圖指標`} aria-pressed={metricId === id} type="button" key={id} onClick={() => onMain(id)}>{label}</button>)}</div>
        <div className="range-cluster"><span className="range-caption">REGIME WINDOW</span><div className="range-group" aria-label="Regime window；唔係預測期限">{RANGES.map((item) => <button className={`tab-button${range === item ? ' is-active' : ''}`} aria-pressed={range === item} type="button" key={item} onClick={() => onRange(item)}>{item}</button>)}</div></div>
      </div>
      <div className={`readout${lastGood ? ' is-last-good' : ''}`} data-value-state={valueState(metric)}>
        <div className="readout-primary"><div className="readout-label">{metric.label} · {UNIT_LABEL[metric.unit] ?? metric.unit.toUpperCase()}</div><div className="readout-value-state"><div className="readout-value">{formatValue(metric.value, metric.unit)}</div>{lastGood ? <LastGoodTag status={metric.quality.status} /> : null}</div></div>
        <span className={`readout-delta ${deltaClass(change.value)}`}>{formatSignedDelta(change.value, metric.unit)} {change.label}</span>
        <div className="readout-meta"><span>{points[0]?.date ?? '—'} → {points.at(-1)?.date ?? '—'} · {points.length} pts</span><span>HOVER 睇每日數值</span></div>
      </div>
      <div className="main-chart"><MainMetricChart metricId={metricId} label={metric.label} unit={metric.unit} points={points} thresholdBp={THRESHOLD_BP} referenceLines={referenceLines} lastGood={lastGood} /></div>
      {metricId === 'reserve_balances' ? <p className="chart-reference-note">2.9T／2.8T／2.5T 只係存量參考區，會隨銀行體系規模、監管同 reserve demand 改變，唔係固定壓力門檻。</p> : null}
      <div className="overlay-toolbar">
        <span className="overlay-title">OVERLAY · 隔夜利率</span>
        {OVERLAY_CONFIG.map(({ id, label, cssVariable }) => {
          const overlayMetric = snapshot.metrics[id];
          const overlayLastGood = isLastGood(overlayMetric);
          return <button type="button" key={id} className={`overlay-toggle${overlay[id] ? '' : ' is-off'}${overlayLastGood ? ' is-last-good' : ''}`} data-value-state={valueState(overlayMetric)} style={{ '--series-color': `var(${cssVariable})` } as CSSProperties} aria-label={`${label} 疊加序列${overlayLastGood ? `，${LAST_GOOD_NOTE}` : ''}`} aria-pressed={Boolean(overlay[id])} onClick={() => onOverlay(id)}><i className="overlay-swatch" aria-hidden="true" />{label} <strong>{formatValue(overlayMetric?.value ?? null, overlayMetric?.unit ?? 'percent')}</strong>{overlayLastGood && overlayMetric ? <LastGoodTag status={overlayMetric.quality.status} /> : null}</button>;
        })}
      </div>
      <div className="overlay-chart"><RateOverlayChart series={overlaySeries} selected={overlay} lastGoodIds={overlayLastGoodIds} /></div>
    </section>
  );
}

const STATUS_GROUPS: Array<{ id: string; label: string; match: (metric: Metric) => boolean }> = [
  { id: 'attention', label: '需要留意', match: (metric) => ['STALE', 'ERROR', 'NOT_RELEASED_YET'].includes(metric.quality.status) },
  { id: 'active-free', label: 'ACTIVE FREE', match: (metric) => metric.availability === 'ACTIVE_FREE' && metric.quality.status === 'OK' },
  { id: 'active-proxy', label: 'ACTIVE PROXY', match: (metric) => metric.availability === 'ACTIVE_PROXY' && metric.quality.status === 'OK' },
  { id: 'manual', label: 'MANUAL READY', match: (metric) => metric.availability === 'MANUAL_READY' },
  { id: 'unavailable', label: 'UNAVAILABLE FREE', match: (metric) => metric.availability === 'UNAVAILABLE_FREE' },
];

function StatusGroups({ metrics, onMetric, compact = false }: { metrics: Metric[]; onMetric: (id: string) => void; compact?: boolean }) {
  return (
    <div className={`status-groups${compact ? ' is-compact' : ''}`}>
      {STATUS_GROUPS.map((group) => {
        const items = metrics.filter(group.match);
        if (!items.length) return null;
        return <section className="status-group" key={group.id}><div className="status-group-head"><span>{group.label}</span><b>{items.length}</b></div><div className="chip-list">{items.map((metric) => <button className="chip" data-status={metric.quality.status} type="button" key={metric.metric_id} onClick={() => onMetric(metric.metric_id)}>{metric.label}{metric.context.is_proxy ? <span className="chip-tag">PROXY</span> : null}</button>)}</div></section>;
      })}
    </div>
  );
}

function ReadRail({ snapshot, onMetric }: { snapshot: Snapshot; onMetric: (id: string) => void }) {
  const maxBalance = Math.max(...BALANCE_IDS.map((id) => snapshot.metrics[id]?.value ?? 0), 1);
  return (
    <aside className="panel read-rail" aria-label="今日解讀與指標狀態">
      <section className="read-section">
        <div className="read-kicker">READ · 今日粵文解讀</div><h3 className="read-headline">{snapshot.explanations.headline}</h3>
        <div className="read-bullets">{snapshot.explanations.bullets.slice(0, 2).map((bullet, index) => <div className="read-bullet" key={`${bullet.metric_id}-${index}`}><b className="read-index">0{index + 1}</b><span>{bullet.observation} {bullet.meaning}</span><span className="read-caveat">替代解釋：{bullet.alternative}</span><span className="read-confirm">確認：{bullet.confirmation}</span><strong className="read-judgment">{bullet.judgment}</strong></div>)}</div>
        {snapshot.technical_context.length ? <div className="technical-context"><strong>技術日 CONTEXT</strong>{snapshot.technical_context.slice(0, 2).map((item) => <span key={`${item.date}-${item.note}`}>{item.date} · {item.note}</span>)}</div> : null}
      </section>
      <section className="balance-section">
        <div className="balance-section-head"><span className="balance-kicker">BALANCE SHEET · 存量</span><span className="balance-unit">USD BN</span></div>
        {BALANCE_IDS.map((id, index) => {
          const item = snapshot.metrics[id]; if (!item) return null; const change = changePresentation(item); const lastGood = isLastGood(item);
          return <div className={`balance-row${lastGood ? ' is-last-good' : ''}`} data-value-state={valueState(item)} key={id}><div className="balance-row-head"><span className="balance-label">{item.label}</span><span className="balance-value-state"><strong className="balance-value">{formatValue(item.value, item.unit)}</strong>{lastGood ? <LastGoodTag status={item.quality.status} /> : null}</span><b className={`balance-delta ${deltaClass(change.value)}`}>{formatSignedDelta(change.value, item.unit)} <small>{change.label}</small></b></div><div className="balance-track"><span className="balance-fill" style={{ width: `${Math.max(0, ((item.value ?? 0) / maxBalance) * 100)}%`, '--bar-color': BALANCE_COLORS[index] } as CSSProperties} /></div><small className="balance-meta">as-of {item.observation_date ?? '—'} · {item.frequency}</small></div>;
        })}
      </section>
      <section className="metric-status-section"><div className="not-wired-head"><span className="not-wired-kicker">IMPLEMENTATION STATUS</span><span className="not-wired-count">{Object.keys(snapshot.metrics).length} 個</span></div><p className="not-wired-copy">可用、代理、人工同免費不可用狀態分開顯示；缺失永不當零。</p><StatusGroups metrics={Object.values(snapshot.metrics)} onMetric={onMetric} compact /></section>
    </aside>
  );
}

function EvidenceBlocks({ value, evidenceOnly = false }: { value: SwitchState; evidenceOnly?: boolean }) {
  return (
    <section className={`evidence-section${evidenceOnly ? ' is-evidence-only' : ''}`} aria-label={evidenceOnly ? 'Market Ignition evidence coverage；不設綜合嚴重度' : 'Evidence blocks'}>
      <div className="detail-section-head">
        <span>{evidenceOnly ? 'EVIDENCE COVERAGE · NO COMPOSITE SEVERITY' : 'EVIDENCE BLOCKS'}</span>
        <b>{value.available_blocks}/{value.total_blocks} AVAILABLE</b>
      </div>
      {evidenceOnly ? <p className="evidence-contract">每個 block 只報方向、資料覆蓋同信心；唔會合成 WATCH／STRESS，亦唔會將 unavailable 當 neutral。</p> : null}
      <div className="evidence-grid">
        {value.evidence_blocks.map((block) => (
          <article className="evidence-card" data-evidence-id={block.id} data-direction={block.direction} data-available={block.available} key={block.id} style={evidenceCardStyle(block.available, block.status, evidenceOnly)}>
            <div><strong>{block.label}</strong>{evidenceOnly ? <span className="evidence-direction"><small>DIRECTION</small><b>{evidenceDirectionLabel(block.direction)}</b></span> : <Badge status={block.status} />}</div>
            <p>{block.summary}</p>
            {evidenceOnly ? <small className="evidence-availability">{block.available ? `EVIDENCE AVAILABLE · CONFIDENCE ${block.confidence.toUpperCase()}` : `UNAVAILABLE · CONFIDENCE ${block.confidence.toUpperCase()} · NOT AN IMPLIED NEUTRAL`}</small> : null}
          </article>
        ))}
      </div>
    </section>
  );
}

function PositionStat({ label, value, format = 'decimal' }: { label: string; value: number | null | undefined; format?: 'contracts' | 'percent-oi' | 'pp' | 'decimal' }) {
  const rendered = format === 'contracts' ? formatValue(value, '', 0)
    : format === 'percent-oi' ? formatValue(value, 'percent_open_interest')
      : format === 'pp' ? value == null ? '—' : `${formatSignedDelta(value, '', 2)} pp`
        : formatValue(value, '', 2);
  return <div><dt>{label}</dt><dd className={format === 'pp' ? deltaClass(value) : undefined}>{rendered}</dd></div>;
}

function positioningDirection(value: number | null | undefined) {
  if (value == null) return 'UNAVAILABLE';
  if (value === 0) return 'FLAT';
  return value > 0 ? 'NET LONG' : 'NET SHORT';
}

function CftcPositioningPanel({ snapshot, series, range, onRange, onMetric }: { snapshot: Snapshot; series: SeriesMap; range: RangeKey; onRange: (range: RangeKey) => void; onMetric: (id: string) => void }) {
  const metrics = P1_CFTC_CONFIG.map((item) => snapshot.metrics[item.id]).filter((metric): metric is Metric => Boolean(metric));
  const active = metrics.filter((metric) => ['ACTIVE_FREE', 'ACTIVE_PROXY'].includes(metric.availability) && metric.quality.status === 'OK' && metric.value != null).length;
  const globalLatest = getGlobalLatestDate(Object.fromEntries(P1_CFTC_CONFIG.flatMap(({ id }) => series[id] ? [[id, series[id]]] : [])));
  return (
    <section className="phase-section cftc-section" aria-labelledby="cftc-positioning-title">
      <div className="detail-section-head"><span id="cftc-positioning-title">P1 · CFTC TFF FUTURES ONLY</span><b>{active}/{P1_CFTC_CONFIG.length} SERIES ACTIVE</b></div>
      <div className="cftc-toolbar">
        <p>Asset Manager 同 Leveraged Funds 分開；正負只代表 net-long／net-short positioning，唔係升跌預測。</p>
        <div className="range-cluster"><span className="range-caption">REGIME WINDOW · NOT A FORECAST HORIZON</span><div className="range-group" aria-label="Market Ignition regime window；唔係預測期限">{RANGES.map((item) => <button className={`tab-button${range === item ? ' is-active' : ''}`} aria-pressed={range === item} type="button" key={item} onClick={() => onRange(item)}>{item}</button>)}</div></div>
      </div>
      <div className="cftc-grid">
        {P1_CFTC_CONFIG.map(({ id, contract, category }) => {
          const metric = snapshot.metrics[id];
          if (!metric) return <article className="cftc-card is-missing" key={id}><div className="cftc-card-head"><div><strong>{contract}</strong><span>{category}</span></div><Badge status="UNAVAILABLE" /></div><p>Snapshot 暫時未提供呢條 canonical series；唔會以零補位。</p></article>;
          const stats = metric.statistics;
          const points = windowPoints(series[id]?.observations ?? metric.short_series, range, globalLatest);
          const lastGood = isLastGood(metric);
          return (
            <article className={`cftc-card${lastGood ? ' is-last-good' : ''}`} data-metric-id={id} data-value-state={valueState(metric)} key={id}>
              <div className="cftc-card-head"><div><strong>{contract}</strong><span>{category}</span></div><div className="cftc-badges"><Badge status={metric.availability} label={AVAILABILITY_LABELS[metric.availability]} /><Badge status={metric.quality.status} label={healthText(metric.quality.status)} /></div></div>
              <div className="cftc-readout"><div><small>NET % OPEN INTEREST</small><strong>{formatValue(metric.value, 'percent_open_interest')}</strong>{lastGood ? <LastGoodTag status={metric.quality.status} /> : null}</div><span>{positioningDirection(metric.value)}</span></div>
              <Sparkline points={points} selected label={`${contract} ${category}，${range} regime window`} lastGood={lastGood} />
              <dl className="cftc-stats">
                <PositionStat label="NET CONTRACTS" value={stats.net_position} format="contracts" />
                <PositionStat label="NET % OI" value={stats.net_percent_open_interest ?? metric.value} format="percent-oi" />
                <PositionStat label="8W CHANGE" value={metric.changes.eight_weeks} format="pp" />
                <PositionStat label="12W CHANGE" value={metric.changes.twelve_weeks} format="pp" />
                <PositionStat label="3Y Z-SCORE" value={stats.z_score_3_year} />
                <PositionStat label="OPEN INTEREST" value={stats.open_interest} format="contracts" />
              </dl>
              <div className="cftc-dates"><span><b>AS-OF · TUE POSITIONS</b>{metric.observation_date ?? '—'}</span><span><b>RELEASE</b>{displayTimestamp(metric.released_at)}</span><span><b>PIPELINE UPDATE</b>{displayTimestamp(metric.updated_at)}</span></div>
              <button type="button" className="metric-method" aria-label={`開啟 ${metric.label} 方法、來源與 weekly lag`} onClick={() => onMetric(id)}>方法、來源與 weekly lag →</button>
            </article>
          );
        })}
      </div>
    </section>
  );
}

function RightsGatedInterfaces({ snapshot, onMetric }: { snapshot: Snapshot; onMetric: (id: string) => void }) {
  return (
    <section className="phase-section rights-gate-section" aria-labelledby="rights-gate-title">
      <div className="detail-section-head"><span id="rights-gate-title">P1 · RIGHTS-GATED PROVIDER INTERFACES</span><b>FAIL CLOSED</b></div>
      <p className="rights-gate-intro">未有明確公開再發布權利就保持 null；以下「—」唔代表零、平穩或者 neutral。</p>
      <div className="rights-gate-grid">
        {P1_RIGHTS_GATED_IDS.map((id) => {
          const metric = snapshot.metrics[id];
          if (!metric) return null;
          const reason = metric.quality.failure_reason || metric.source.rights_note || metric.methodology.source_and_license_note;
          return <article className="rights-gate-card" data-metric-id={id} key={id}><div><strong>{metric.label}</strong><Badge status={metric.availability} label={AVAILABILITY_LABELS[metric.availability]} /></div><span className="rights-null">—</span><p><b>RIGHTS HOLD</b>{reason}</p><p><b>PROVIDER INTERFACE</b>{metric.methodology.calculation}</p><button type="button" className="metric-method" aria-label={`開啟 ${metric.label} 完整方法與來源`} onClick={() => onMetric(id)}>完整方法與來源 →</button></article>;
        })}
      </div>
    </section>
  );
}

function ratioValue(value: number | null | undefined) {
  return formatValue(value, '', 2);
}

function coverageValue(value: number | null | undefined) {
  return value == null ? '—' : formatValue(value * 100, 'percent', 1);
}

function countValue(value: number | null | undefined) {
  return formatValue(value, '', 0);
}

function FragilityStat({ label, value, detail, tone }: { label: string; value: string; detail?: string; tone?: string }) {
  return <div><dt>{label}</dt><dd className={tone}>{value}</dd>{detail ? <small>{detail}</small> : null}</div>;
}

function FragilityPanel({ snapshot, series, range, onMetric }: { snapshot: Snapshot; series: SeriesMap; range: RangeKey; onMetric: (id: string) => void }) {
  const macro = snapshot.metrics.nonfinancial_equities_gdp_proxy;
  const form4 = snapshot.metrics.sec_form4_nonderivative_ps_count_ratio_20d;
  const active = P2_ACTIVE_IDS.filter((id) => {
    const metric = snapshot.metrics[id];
    return metric?.quality.status === 'OK' && metric.value != null;
  }).length;
  const p2Series = Object.fromEntries(P2_ACTIVE_IDS.flatMap((id) => series[id] ? [[id, series[id]]] : []));
  const globalLatest = getGlobalLatestDate(p2Series);
  const macroPoints = windowPoints(series[macro.metric_id]?.observations ?? macro.short_series, range, globalLatest);
  const form4Points = windowPoints(series[form4.metric_id]?.observations ?? form4.short_series, range, globalLatest);
  const macroStats = macro.statistics;
  const form4Stats = form4.statistics;
  const macroLastGood = isLastGood(macro);
  const form4LastGood = isLastGood(form4);

  return (
    <section className="phase-section fragility-section" aria-labelledby="fragility-title">
      <div className="detail-section-head"><span id="fragility-title">P2 · BUBBLE / FRAGILITY CONTEXT</span><b>{active}/{P2_ACTIVE_IDS.length + P2_HELD_IDS.length} CONTEXT AVAILABLE</b></div>
      <p className="fragility-contract"><strong>CONTEXT ONLY.</strong> 呢兩組資料獨立顯示，唔會改動 P1 Market Ignition coverage、Overview overall assessment，亦唔會產生 WATCH／STRESS。</p>
      <div className="fragility-grid">
        <article className={`fragility-card${macroLastGood ? ' is-last-good' : ''}`} data-metric-id={macro.metric_id} data-value-state={valueState(macro)}>
          <div className="fragility-card-head"><div><strong>NONFINANCIAL EQUITIES / GDP</strong><span>QUARTERLY GOVERNMENT-ORIGIN PROXY</span></div><div className="cftc-badges"><Badge status={macro.availability} label={AVAILABILITY_LABELS[macro.availability]} /><Badge status={macro.quality.status} label={healthText(macro.quality.status)} /></div></div>
          <div className="fragility-readout"><div><small>CURRENT RATIO</small><strong>{formatValue(macro.value, 'percent')}</strong>{macroLastGood ? <LastGoodTag status={macro.quality.status} /> : null}</div><span>COMMON QUARTER · {macro.context.common_quarter ?? '—'}</span></div>
          <Sparkline points={macroPoints} selected label={`Nonfinancial equities / GDP，${range} regime window`} lastGood={macroLastGood} />
          <dl className="fragility-stats">
            <FragilityStat label="1Q RATIO Δ" value={macro.changes.one_quarter == null ? '—' : `${formatSignedDelta(macro.changes.one_quarter, '', 2)} pp`} tone={deltaClass(macro.changes.one_quarter)} />
            <FragilityStat label="QOQ" value={formatSignedDelta(macroStats.qoq_percent_change, 'percent')} tone={deltaClass(macroStats.qoq_percent_change)} />
            <FragilityStat label="YOY" value={formatSignedDelta(macroStats.yoy_percent_change, 'percent')} tone={deltaClass(macroStats.yoy_percent_change)} />
            <FragilityStat label="10Y PERCENTILE" value={formatValue(macroStats.percentile_10y, 'percent', 1)} detail={`${countValue(macroStats.percentile_10y_sample_size)} common quarters`} />
            <FragilityStat label="EQUITY LIABILITIES" value={formatValue(macroStats.equity_usd_bn, 'USD bn')} />
            <FragilityStat label="NOMINAL GDP" value={formatValue(macroStats.gdp_usd_bn, 'USD bn')} />
          </dl>
          <dl className="fragility-dates">
            <div><dt>EQUITY INPUT AS-OF</dt><dd>{macro.context.equity_observation_date ?? '—'}</dd></div>
            <div><dt>GDP INPUT AS-OF</dt><dd>{macro.context.gdp_observation_date ?? '—'}</dd></div>
            <div><dt>PIPELINE UPDATE</dt><dd>{displayTimestamp(macro.updated_at)}</dd></div>
          </dl>
          <p className="fragility-caveat"><b>PROXY CAVEAT</b>{macro.methodology.proxy_disclosure || macro.methodology.common_misreads}</p>
          <button type="button" className="metric-method" aria-label={`開啟 ${macro.label} 完整方法與來源`} onClick={() => onMetric(macro.metric_id)}>完整方法、revision 風險與來源 →</button>
        </article>

        <article className={`fragility-card${form4LastGood ? ' is-last-good' : ''}`} data-metric-id={form4.metric_id} data-value-state={valueState(form4)}>
          <div className="fragility-card-head"><div><strong>SEC FORM 4 REPORTED P/S</strong><span>NON-DERIVATIVE TRANSACTION-ROW PROXY</span></div><div className="cftc-badges"><Badge status={form4.availability} label={AVAILABILITY_LABELS[form4.availability]} /><Badge status={form4.quality.status} label={healthText(form4.quality.status)} /></div></div>
          <div className="fragility-readout"><div><small>20D COUNT RATIO</small><strong>{ratioValue(form4.value)}</strong>{form4LastGood ? <LastGoodTag status={form4.quality.status} /> : null}</div><span>20 COMPLETED EDGAR INDEX DAYS</span></div>
          <Sparkline points={form4Points} selected label={`SEC Form 4 P/S count ratio，${range} regime window`} lastGood={form4LastGood} />
          <dl className="fragility-stats form4-ratios">
            <FragilityStat label="INCLUSIVE · 20D" value={ratioValue(form4Stats.count_ratio_20d)} />
            <FragilityStat label="INCLUSIVE · 5D" value={ratioValue(form4Stats.ratio_5d)} />
            <FragilityStat label="EXPLICIT-FALSE · 20D" value={ratioValue(form4Stats.ex_explicit_false_count_ratio_20d)} detail={`${coverageValue(form4Stats.ex_explicit_false_coverage_20d)} eligible-row coverage`} />
            <FragilityStat label="EXPLICIT-FALSE · 5D" value={ratioValue(form4Stats.ex_explicit_false_count_ratio_5d)} detail={`${coverageValue(form4Stats.ex_explicit_false_coverage_5d)} eligible-row coverage`} />
          </dl>
          <table className="form4-count-table">
            <caption>P / S ELIGIBLE TRANSACTION-ROW COUNTS</caption>
            <thead><tr><th scope="col">WINDOW</th><th scope="col">P ROWS</th><th scope="col">S ROWS</th><th scope="col">RATIO</th></tr></thead>
            <tbody><tr><th scope="row">5D</th><td>{countValue(form4Stats.purchase_count_5d)}</td><td>{countValue(form4Stats.sale_count_5d)}</td><td>{ratioValue(form4Stats.ratio_5d)}</td></tr><tr><th scope="row">20D</th><td>{countValue(form4Stats.purchase_count_20d)}</td><td>{countValue(form4Stats.sale_count_20d)}</td><td>{ratioValue(form4Stats.count_ratio_20d)}</td></tr></tbody>
          </table>
          <div className="form4-dollar-grid" aria-label="Form 4 dollar ratio coverage">
            {(['5d', '20d'] as const).map((window) => {
              const ratio = form4Stats[`dollar_ratio_${window}`];
              const coverage = form4Stats[`dollar_coverage_rate_${window}`];
              const status = form4.context[`dollar_status_${window}`] ?? 'UNKNOWN';
              return <div key={window}><span>DOLLAR RATIO · {window.toUpperCase()}</span><strong>{ratioValue(ratio)}</strong><small>{coverageValue(coverage)} priced-row coverage · {status.replaceAll('_', ' ')}</small></div>;
            })}
          </div>
          <dl className="form4-audit-grid">
            <FragilityStat label="ELIGIBLE / PRICED ROWS · 20D" value={`${countValue(form4Stats.eligible_transaction_count_20d)} / ${countValue(form4Stats.priced_transaction_count_20d)}`} />
            <FragilityStat label="FILINGS / ACCESSIONS / ISSUERS" value={`${countValue(form4Stats.filings_processed_20d)} / ${countValue(form4Stats.unique_accessions_20d)} / ${countValue(form4Stats.unique_issuers_20d)}`} />
            <FragilityStat label="FORM 4 / FORM 4-A" value={`${countValue(form4Stats.form4_count_20d)} / ${countValue(form4Stats.form4a_count_20d)}`} />
            <FragilityStat label="AMENDMENTS LINKED / REVIEW" value={`${countValue(form4Stats.amendments_linked_20d)} / ${countValue(form4Stats.amendments_review_count_20d)}`} />
            <FragilityStat label="PARSE FAILURES" value={countValue(form4Stats.parse_failures_20d)} tone={form4Stats.parse_failures_20d ? 'is-negative' : 'is-zero'} />
            <FragilityStat label="10B5-1 TRUE / FALSE / UNKNOWN" value={`${countValue(form4Stats.tenb5_true_filings_20d)} / ${countValue(form4Stats.tenb5_false_filings_20d)} / ${countValue(form4Stats.tenb5_unknown_filings_20d)}`} />
          </dl>
          <dl className="fragility-dates form4-windows">
            <div><dt>5D CUTOFF</dt><dd>{form4.context.window_start_5d ?? '—'} → {form4.context.window_end_5d ?? '—'}</dd></div>
            <div><dt>20D CUTOFF</dt><dd>{form4.context.window_start_20d ?? '—'} → {form4.context.window_end_20d ?? '—'}</dd></div>
            <div><dt>PIPELINE UPDATE</dt><dd>{displayTimestamp(form4.updated_at)}</dd></div>
          </dl>
          <p className="fragility-caveat"><b>DEFINITION BOUNDARY</b>P/S includes <strong>open-market OR private</strong> purchases and sales. Ratios count eligible non-derivative transaction rows, not unique insiders or trades. The 10b5-1 sensitivity is filing-level and includes only filings explicitly marked false; amendments that cannot be reliably linked are quarantined for review.</p>
          <button type="button" className="metric-method" aria-label={`開啟 ${form4.label} 完整方法、來源與審核限制`} onClick={() => onMetric(form4.metric_id)}>完整方法、來源與審核限制 →</button>
        </article>
      </div>
    </section>
  );
}

function P2RightsHeld({ snapshot, onMetric }: { snapshot: Snapshot; onMetric: (id: string) => void }) {
  return (
    <section className="phase-section rights-gate-section p2-held-section" aria-labelledby="p2-held-title">
      <div className="detail-section-head"><span id="p2-held-title">P2 · UNAVAILABLE FREE</span><b>{P2_HELD_IDS.length} LOCKED INTERFACES · FAIL CLOSED</b></div>
      <p className="rights-gate-intro">缺少重發權利或 definition-consistent input，所以一律保持 null；以下「—」唔代表零、平穩或 neutral。</p>
      <div className="rights-gate-grid">
        {P2_HELD_IDS.map((id) => {
          const metric = snapshot.metrics[id];
          if (!metric) return null;
          const reason = metric.quality.failure_reason || metric.source.rights_note || metric.methodology.source_and_license_note;
          return <article className="rights-gate-card" data-metric-id={id} key={id}><div><strong>{metric.label}</strong><Badge status={metric.availability} label={AVAILABILITY_LABELS[metric.availability]} /></div><span className="rights-null">—</span><p><b>EXACT HOLD</b>{reason}</p><p><b>FUTURE INTERFACE</b>{metric.methodology.calculation}</p><button type="button" className="metric-method" aria-label={`開啟 ${metric.label} 完整方法與來源`} onClick={() => onMetric(id)}>完整方法與來源 →</button></article>;
        })}
      </div>
    </section>
  );
}

function ConfirmationGrid({ snapshot, onMain, onMetric }: { snapshot: Snapshot; onMain: (id: string) => void; onMetric: (id: string) => void }) {
  return <section className="confirmation-section"><div className="detail-section-head"><span>IORB CONFIRMATION SPREADS</span><b>BACKWARD AS-OF JOIN</b></div><div className="confirmation-grid">{CONFIRMATION_SPREAD_IDS.map((id) => { const metric = snapshot.metrics[id]; if (!metric) return null; const change = changePresentation(metric); const lastGood = isLastGood(metric); return <article className={`metric-card${lastGood ? ' is-last-good' : ''}`} data-value-state={valueState(metric)} key={id}><button type="button" className="metric-card-main" onClick={() => onMain(id)}><span>{metric.label}</span><strong>{formatValue(metric.value, metric.unit)}</strong>{lastGood ? <LastGoodTag status={metric.quality.status} /> : null}<small className={deltaClass(change.value)}>{formatSignedDelta(change.value, metric.unit)} {change.label}</small></button><button type="button" className="metric-method" onClick={() => onMetric(id)}>方法與來源 →</button></article>; })}</div></section>;
}

function OverviewPage(props: Pick<DashboardProps, 'snapshot' | 'series' | 'main' | 'range' | 'overlay' | 'onMain' | 'onRange' | 'onOverlay' | 'onDrawer'>) {
  return <><h2 className="route-heading sr-only" data-route-heading tabIndex={-1}>總覽</h2><main className="body-grid"><LiveTape snapshot={props.snapshot} series={props.series} selected={props.main} onSelect={props.onMain} /><ChartPanel snapshot={props.snapshot} series={props.series} main={props.main} range={props.range} overlay={props.overlay} tabs={OVERVIEW_MAIN_TABS} onMain={props.onMain} onRange={props.onRange} onOverlay={props.onOverlay} /><ReadRail snapshot={props.snapshot} onMetric={props.onDrawer} /></main></>;
}

function LiquidityPage(props: Pick<DashboardProps, 'snapshot' | 'series' | 'main' | 'range' | 'overlay' | 'onMain' | 'onRange' | 'onOverlay' | 'onDrawer'>) {
  const value = props.snapshot.switches.liquidity_fuel;
  return <main className="detail-page"><header className="detail-hero"><div><span className="detail-number">01</span><h2 className="route-heading" data-route-heading tabIndex={-1}>流動性燃料</h2><p>{value.summary}</p></div><div className="detail-assessment" style={statusStyle(value.assessment ?? value.mode)}><span>P0 ASSESSMENT</span><strong>{value.assessment ?? '未能評估'}</strong><small>CONFIDENCE {value.confidence.toUpperCase()}</small></div></header><ConfirmationGrid snapshot={props.snapshot} onMain={props.onMain} onMetric={props.onDrawer} /><ChartPanel snapshot={props.snapshot} series={props.series} main={props.main} range={props.range} overlay={props.overlay} tabs={LIQUIDITY_MAIN_TABS} onMain={props.onMain} onRange={props.onRange} onOverlay={props.onOverlay} /><EvidenceBlocks value={value} /></main>;
}

function PhasePage({ route, snapshot, catalog, catalogError, series, range, onRange, onMetric }: { route: 'market-ignition' | 'fundamental-exit'; snapshot: Snapshot; catalog: CatalogMetric[]; catalogError: string; series: SeriesMap; range: RangeKey; onRange: (range: RangeKey) => void; onMetric: (id: string) => void }) {
  const layer = route === 'market-ignition' ? 'market_ignition' : 'fundamental_exit';
  const value = snapshot.switches[layer];
  const title = route === 'market-ignition' ? '市場引信' : '基本面逃生門';
  const p3Metrics = catalog.filter((item) => item.layer === layer && item.phase === 'P3')
    .map((item) => snapshot.metrics[item.metric_id]).filter((metric): metric is Metric => Boolean(metric));
  const p3Active = p3Metrics.filter((metric) => ['ACTIVE_FREE', 'ACTIVE_PROXY'].includes(metric.availability) && metric.quality.status === 'OK').length;
  return (
    <main className="detail-page">
      <header className="detail-hero">
        <div><span className="detail-number">{route === 'market-ignition' ? '02' : '03'}</span><h2 className="route-heading" data-route-heading tabIndex={-1}>{title}</h2><p>{value.summary}</p></div>
        {route === 'market-ignition'
          ? <div className="detail-assessment is-evidence-only" style={statusStyle('UNKNOWN')}><span>EVIDENCE ONLY</span><strong>{value.available_blocks}/{value.total_blocks} AVAILABLE</strong><small>DIRECTION + CONFIDENCE · NO WATCH/STRESS</small></div>
          : <div className="detail-assessment" style={statusStyle(value.assessment ?? value.mode)}><span>{value.mode.toUpperCase()}</span><strong>{value.assessment ?? '資料未足以評估'}</strong><small>{value.available_blocks}/{value.total_blocks} BLOCKS · {value.confidence.toUpperCase()}</small></div>}
      </header>
      {catalogError ? <div className="inline-error" role="status">Manifest 暫時不可用：{catalogError}</div> : null}
      {route === 'market-ignition' ? <>
        <EvidenceBlocks value={value} evidenceOnly />
        <CftcPositioningPanel snapshot={snapshot} series={series} range={range} onRange={onRange} onMetric={onMetric} />
        <RightsGatedInterfaces snapshot={snapshot} onMetric={onMetric} />
        <FragilityPanel snapshot={snapshot} series={series} range={range} onMetric={onMetric} />
        <P2RightsHeld snapshot={snapshot} onMetric={onMetric} />
      </> : <>
        <section className="phase-section"><div className="detail-section-head"><span>P3 · CAPEX / INDUSTRY DEMAND</span><b>{p3Active}/{p3Metrics.length} ACTIVE</b></div>{p3Metrics.length ? <StatusGroups metrics={p3Metrics} onMetric={onMetric} /> : <p className="phase-empty">呢個 phase 暫時未有可驗證 metric metadata；唔會用假數字補位。</p>}</section>
        <EvidenceBlocks value={value} />
      </>}
    </main>
  );
}

function FooterTicker({ snapshotUrl, onSources }: { snapshotUrl: string; onSources: () => void }) {
  return <footer className="footer-ticker"><strong>USD LIQUIDITY / OPEN MONITOR</strong><span>只供研究，並非投資建議</span><span className="footer-actions"><a href={snapshotUrl} download="snapshot.json">下載 JSON ↓</a><button className="footer-action" type="button" onClick={onSources}>來源與方法 →</button></span></footer>;
}

function CftcLegalNotice() {
  return <p className="cftc-legal-notice"><strong>CFTC TFF Futures Only.</strong> Source acknowledged: U.S. Commodity Futures Trading Commission, <a href="https://publicreporting.cftc.gov/Commitments-of-Traders/TFF-Futures-Only/gpe5-46if" target="_blank" rel="noreferrer">official TFF Futures Only dataset ↗</a> and <a href="https://www.cftc.gov/MarketReports/CommitmentsofTraders/ReleaseSchedule/index.htm" target="_blank" rel="noreferrer">COT release schedule ↗</a>. Positions are measured as of Tuesday and normally released Friday; holiday schedules can delay release. Asset Manager and Leveraged Funds are official reporting categories; neither is “CTA exposure”, and positioning is not a forecast. Under the <a href="https://www.cftc.gov/WebPolicy/index.htm" target="_blank" rel="noreferrer">CFTC Web Policy ↗</a>, government-produced material is generally public domain, while credited third-party material can carry separate rights. No CFTC seal or logo is used. Bubble USD Liquidity Dashboard is not affiliated with, endorsed by, or acting for the CFTC, and the CFTC is not responsible for this presentation.</p>;
}

function SecLegalNotice() {
  return <p className="sec-legal-notice"><strong>SEC EDGAR Form 4.</strong> Filing data are obtained from the <a href="https://www.sec.gov/Archives/edgar/daily-index/" target="_blank" rel="noreferrer">official EDGAR daily indexes ↗</a>. Under the official <a href="https://www.sec.gov/files/form4.pdf" target="_blank" rel="noreferrer">Form 4 instructions ↗</a>, transaction codes P and S cover open-market <em>or private</em> purchases and sales; this dashboard therefore does not label them open-market-only. The count ratio measures eligible non-derivative transaction rows, while missing prices affect dollar coverage. Filing-level 10b5-1 flags are not exact transaction-level classifications, and unlinked amendments are quarantined for review. Public EDGAR information may be reused subject to the SEC’s <a href="https://www.sec.gov/about/privacy-information" target="_blank" rel="noreferrer">privacy and dissemination notice ↗</a>. No SEC seal or logo is used, and Bubble USD Liquidity Dashboard is not affiliated with or endorsed by the SEC.</p>;
}

function Provenance({ snapshot }: { snapshot: Snapshot }) {
  return (
    <section className="provenance-grid">
      <article className="provenance-panel">
        <div className="provenance-kicker">PROVENANCE · COLLECTOR HEALTH</div>
        {Object.entries(snapshot.sources).map(([id, source]) => <div className="source-row" key={id}><div className="source-main">{source.url ? <a className="source-link" href={source.url} target="_blank" rel="noreferrer">{source.name} ↗</a> : <strong>{source.name}</strong>}<span className="source-meta">{source.observation_date ?? '—'} · {FRESHNESS_LABELS[source.freshness]}</span></div><span className="source-quality">{source.tier ?? '—'}</span><Badge status={source.status} label={healthText(source.status)} /></div>)}
      </article>
      <article className="provenance-panel analysis-contract">
        <div className="provenance-kicker">ANALYSIS CONTRACT</div><h2>訊號唔係結論。</h2>
        <p>Overview 嘅總體判讀只代表 P0 流動性燃料；P1–P3 只報 evidence coverage、方向同信心。+{THRESHOLD_BP} bp 係可配置操作門檻，技術日只降低信心。</p>
      </article>
      <article className="provenance-panel source-notices" aria-labelledby="source-notices-title">
        <div className="provenance-kicker" id="source-notices-title">LEGAL · SOURCE NOTICES</div>
        <p><strong>FRED® API.</strong> This product uses the FRED® API but is not endorsed or certified by the Federal Reserve Bank of St. Louis. By using this dashboard, users agree to be bound by the <a href="https://fred.stlouisfed.org/docs/api/terms_of_use.html" target="_blank" rel="noreferrer">FRED® API Terms of Use ↗</a>. Only reviewed government-origin series are enabled; a FRED API key does not grant third-party data rights.</p>
        <p><strong>New York Fed reference rates.</strong> The SOFR, EFFR, OBFR, TGCR and BGCR data are subject to the <a href="https://www.newyorkfed.org/privacy/termsofuse.html" target="_blank" rel="noreferrer">Terms of Use posted at newyorkfed.org ↗</a>. The New York Fed is not responsible for publication of these data by Bubble USD Liquidity Dashboard, does not sanction or endorse this republication, and has no liability for your use. Bubble USD Liquidity Dashboard is not affiliated with the New York Fed. The New York Fed does not sanction, endorse, or recommend any products or services offered by Bubble USD Liquidity Dashboard. © 2026 Federal Reserve Bank of New York. Content from the New York Fed subject to the Terms of Use at newyorkfed.org.</p>
        <CftcLegalNotice />
        <SecLegalNotice />
        <p><strong>Privacy.</strong> This static dashboard does not provide accounts and does not intentionally collect personal information, analytics, or cookies.</p>
      </article>
    </section>
  );
}

interface DrawerProps { mode: 'sources' | string; snapshot: Snapshot; catalog: CatalogMetric[]; catalogError: string; restoreFocus: HTMLElement | null; onClose: () => void }

function TimestampGrid({ observation, released, updated }: { observation: string | null; released: string | null; updated: string | null }) {
  return <dl className="timestamp-grid"><div><dt>OBSERVATION</dt><dd>{observation ?? '—'}</dd></div><div><dt>RELEASED</dt><dd>{displayTimestamp(released)}</dd></div><div><dt>PIPELINE UPDATED</dt><dd>{displayTimestamp(updated)}</dd></div></dl>;
}

function AttemptStatus({ attempt, success }: { attempt: string | null; success: string | null }) {
  return <dl className="attempt-status"><div><dt>LAST ATTEMPT</dt><dd>{displayTimestamp(attempt)}</dd></div><div><dt>LAST SUCCESS</dt><dd>{displayTimestamp(success)}</dd></div></dl>;
}

function formatStatistic(name: string, value: number): string {
  if (name === 'sample_size' || name.endsWith('_sample_size') || name.includes('_count_') ||
    name.startsWith('unique_') || name.startsWith('filings_processed_') || name.startsWith('form4') ||
    name.startsWith('amendments_') || name.startsWith('parse_failures_') || name.startsWith('tenb5_') ||
    ['net_position', 'open_interest', 'long_position', 'short_position', 'spread_position', 'operation_count'].includes(name)) {
    return formatValue(value, '', 0);
  }
  if (name.includes('coverage_rate') || name.startsWith('ex_explicit_false_coverage_')) return formatValue(value * 100, 'percent', 1);
  if (name === 'percentile_10y' || name === 'qoq_percent_change' || name === 'yoy_percent_change') return formatValue(value, 'percent', 2);
  if (name === 'equity_usd_bn' || name === 'gdp_usd_bn') return formatValue(value, 'USD bn');
  if (name.includes('ratio')) return formatValue(value, '', 2);
  if (name === 'net_percent_open_interest') return formatValue(value, 'percent_open_interest');
  if (name === 'change_8_weeks' || name === 'change_12_weeks') return `${formatSignedDelta(value, '', 2)} pp`;
  return formatValue(value);
}

function Statistics({ values }: { values: Metric['statistics'] }) {
  const entries = Object.entries(values);
  return <section className="drawer-statistics" aria-label="Metric statistics"><h3>STATISTICS</h3>{entries.length ? <dl>{entries.map(([name, value]) => <div key={name}><dt>{name}</dt><dd>{value == null ? '—' : formatStatistic(name, value)}</dd></div>)}</dl> : <p>無額外統計輸出。</p>}</section>;
}

function SourceDrawerRow({ source }: { source: CollectorSource }) {
  return <article className="drawer-source"><div className="drawer-source-main"><strong>{source.name}</strong><span className="source-meta">{source.tier ?? '—'} · {FRESHNESS_LABELS[source.freshness]}</span>{source.url ? <a href={source.url} target="_blank" rel="noreferrer">官方來源 ↗</a> : null}</div><Badge status={source.status} label={healthText(source.status)} /><TimestampGrid observation={source.observation_date} released={source.released_at} updated={source.updated_at} /><AttemptStatus attempt={source.last_attempt_at} success={source.last_success_at} /><p className="rights-note"><b>RIGHTS / USE</b>{source.rights_note || '未提供授權備註。'}</p>{source.failure_reason ? <p className="drawer-error">{source.failure_reason}</p> : null}</article>;
}

function Drawer({ mode, snapshot, catalog, catalogError, restoreFocus, onClose }: DrawerProps) {
  const closeRef = useRef<HTMLButtonElement>(null); const drawerRef = useRef<HTMLElement>(null);
  useEffect(() => { const overflow = document.body.style.overflow; document.body.style.overflow = 'hidden'; closeRef.current?.focus(); const onKeyDown = (event: KeyboardEvent) => { if (event.key === 'Escape') { event.preventDefault(); onClose(); return; } if (event.key !== 'Tab' || !drawerRef.current) return; const focusable = [...drawerRef.current.querySelectorAll<HTMLElement>('button, a[href], [tabindex]:not([tabindex="-1"])')].filter((element) => !element.hasAttribute('disabled')); if (!focusable.length) return; const first = focusable[0]; const last = focusable.at(-1)!; if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); } else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); } }; document.addEventListener('keydown', onKeyDown); return () => { document.removeEventListener('keydown', onKeyDown); document.body.style.overflow = overflow; if (restoreFocus?.isConnected) restoreFocus.focus(); window.requestAnimationFrame(() => { if (restoreFocus?.isConnected) restoreFocus.focus(); }); }; }, [onClose, restoreFocus]);
  const sourceMode = mode === 'sources'; const metric = sourceMode ? undefined : snapshot.metrics[mode]; const catalogMetric = sourceMode ? undefined : catalog.find((item) => item.metric_id === mode);
  const definitions: Array<[string, keyof Metric['methodology']]> = [['回答問題', 'question'], ['精確定義', 'definition'], ['點解要睇', 'why_it_matters'], ['方向判讀', 'direction'], ['計算方法', 'calculation'], ['頻率與滯後', 'frequency_and_lag'], ['常見誤判', 'common_misreads'], ['技術扭曲', 'technical_distortions'], ['一齊確認', 'confirm_with'], ['唔可以推論', 'cannot_infer'], ['來源／授權', 'source_and_license_note'], ['Proxy disclosure', 'proxy_disclosure']];
  return <div className="drawer-scrim" onClick={(event: MouseEvent<HTMLDivElement>) => { if (event.target === event.currentTarget) onClose(); }}><aside className="drawer" ref={drawerRef} role="dialog" aria-modal="true" aria-labelledby="drawer-title"><button className="drawer-close" type="button" ref={closeRef} onClick={onClose} aria-label="關閉">×</button><div className="drawer-kicker">{sourceMode ? 'PROVENANCE' : 'METRIC METHODOLOGY'}</div><h2 id="drawer-title">{sourceMode ? '來源與健康狀態' : metric?.label ?? mode}</h2>{!sourceMode && catalogError ? <p className="drawer-catalog-warning" role="status">Manifest／方法目錄暫時不可用（{catalogError}）。以下 snapshot metric 資料仍可查看，但方法目錄完整性未能確認。</p> : null}{sourceMode ? <>{Object.entries(snapshot.sources).map(([id, source]) => <SourceDrawerRow key={id} source={source} />)}<section className="drawer-legal-notice" aria-label="CFTC and SEC source notices"><CftcLegalNotice /><SecLegalNotice /></section></> : metric ? <><div className="drawer-badges"><Badge status={metric.availability} label={AVAILABILITY_LABELS[metric.availability]} /><Badge status={metric.quality.status} label={healthText(metric.quality.status)} /><Badge status={metric.quality.freshness} label={FRESHNESS_LABELS[metric.quality.freshness]} /></div><TimestampGrid observation={metric.observation_date} released={metric.released_at} updated={metric.updated_at} /><AttemptStatus attempt={metric.quality.last_attempt_at} success={metric.quality.last_success_at} /><Statistics values={metric.statistics} /><p className="rights-note"><b>RIGHTS / USE</b>{metric.source.rights_note || metric.methodology.source_and_license_note}</p>{metric.quality.failure_reason ? <p className="drawer-error">{metric.quality.failure_reason}</p> : null}<dl className="drawer-def">{definitions.map(([term, key]) => { const content = metric.methodology[key]; const text = Array.isArray(content) ? content.join('、') : content; return text ? <div key={key}><dt>{term}</dt><dd>{text}</dd></div> : null; })}</dl></> : <p className="drawer-message">{catalogError || (catalogMetric ? 'Snapshot metric 暫時未提供。' : '方法資料暫時未提供。')}</p>}</aside></div>;
}

export interface DashboardProps {
  snapshot: Snapshot; catalog: CatalogMetric[]; catalogError: string; series: SeriesMap; seriesErrors: Record<string, string>; seriesLoading: boolean;
  route: RouteId; main: string; range: RangeKey; overlay: Record<string, boolean>; drawer: 'sources' | string | null; baseUrl: string;
  onMain: (id: string) => void; onRange: (range: RangeKey) => void; onOverlay: (id: string) => void; onDrawer: (mode: 'sources' | string | null) => void;
}

export function Dashboard(props: DashboardProps) {
  const drawerTriggerRef = useRef<HTMLElement | null>(null);
  const openDrawer = useCallback((mode: 'sources' | string | null) => {
    if (mode === null) {
      props.onDrawer(null);
      return;
    }
    const active = document.activeElement;
    drawerTriggerRef.current = active instanceof HTMLElement && active !== document.body ? active : null;
    props.onDrawer(mode);
  }, [props.onDrawer]);
  const closeDrawer = useCallback(() => props.onDrawer(null), [props.onDrawer]);
  const openSources = useCallback(() => openDrawer('sources'), [openDrawer]);
  return <div className="app-shell"><div className="deck"><StatusBar snapshot={props.snapshot} route={props.route} onOpenSources={openSources} /><SwitchStrip snapshot={props.snapshot} route={props.route} /><div className="series-live-region" role="status" aria-live="polite">{props.seriesLoading ? '載入本頁完整時間序列…' : Object.keys(props.seriesErrors).length ? `${Object.keys(props.seriesErrors).length} 條完整時間序列暫不可用，已使用 snapshot 短序列。` : '本頁完整時間序列已載入。'}</div>{props.route === 'overview' ? <OverviewPage {...props} onDrawer={openDrawer} /> : props.route === 'liquidity-fuel' ? <LiquidityPage {...props} onDrawer={openDrawer} /> : <PhasePage route={props.route} snapshot={props.snapshot} catalog={props.catalog} catalogError={props.catalogError} series={props.series} range={props.range} onRange={props.onRange} onMetric={openDrawer} />}<FooterTicker snapshotUrl={`${props.baseUrl}data/snapshot.json`} onSources={openSources} /></div><Provenance snapshot={props.snapshot} />{props.drawer ? <Drawer mode={props.drawer} snapshot={props.snapshot} catalog={props.catalog} catalogError={props.catalogError} restoreFocus={drawerTriggerRef.current} onClose={closeDrawer} /> : null}</div>;
}

export function StateScreen({ error }: { error?: string }) {
  return <main className="state-screen" role={error ? 'alert' : 'status'} aria-live="polite">{error ? <><h1>暫時未能載入數據</h1><p>現有 v2 snapshot 無法讀取（{error}）。請稍後再試；系統不會以零代替缺失值。</p></> : <><div className="loader" aria-hidden="true" /><p>載入已驗證 v2 snapshot…</p></>}</main>;
}
