import {
  type CSSProperties,
  type MouseEvent,
  useEffect,
  useMemo,
  useRef,
} from 'react';
import type { CatalogMetric, Snapshot, Source } from '../types';
import type { RangeKey, SeriesMap } from '../dashboard';
import {
  getGlobalLatestDate,
  THRESHOLD_BP,
  windowPoints,
} from '../dashboard';
import { MainMetricChart, OVERLAY_CONFIG, RateOverlayChart, Sparkline } from './Charts';

const SWITCHES = [
  { id: 'liquidity_fuel', number: '01', kicker: 'LIQUIDITY FUEL', title: '流動性燃料' },
  { id: 'market_ignition', number: '02', kicker: 'MARKET IGNITION', title: '市場引信' },
  { id: 'fundamental_exit', number: '03', kicker: 'FUNDAMENTAL EXIT', title: '基本面逃生門' },
] as const;

const TAPE_GROUPS = [
  {
    label: 'DAILY · 隔夜價格與流量',
    ids: ['sofr_iorb_spread', 'sofr', 'iorb', 'effr', 'obfr', 'tgcr', 'bgcr', 'tga_daily'],
  },
  {
    label: 'WEEKLY · Fed 資產負債表',
    ids: ['reserve_balances', 'fed_total_assets', 'tga_weekly_h41'],
  },
] as const;

const TAPE_IDS = TAPE_GROUPS.flatMap((group) => [...group.ids]);
const TICKERS: Record<string, string> = {
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

const MAIN_TABS = [
  ['sofr_iorb_spread', 'SOFR−IORB'],
  ['sofr', 'SOFR'],
  ['iorb', 'IORB'],
  ['effr', 'EFFR'],
  ['tga_daily', 'TGA'],
  ['reserve_balances', 'RESERVES'],
  ['fed_total_assets', 'WALCL'],
] as const;

const BALANCE_IDS = ['fed_total_assets', 'reserve_balances', 'tga_daily', 'tga_weekly_h41'] as const;
const BALANCE_COLORS = ['var(--balance-1)', 'var(--balance-2)', 'var(--balance-3)', 'var(--balance-4)'];
const RANGES: RangeKey[] = ['1M', '3M', '1Y', 'MAX'];

const STATUS_TEXT: Record<string, string> = {
  ok: '正常',
  stale: '過期',
  missing: '未接通',
  error: '抓取錯誤',
  not_released: '尚未發布',
  manual_update_due: '待人工更新',
  paid_data_unavailable: '需供應商',
};

const UNIT_LABEL: Record<string, string> = {
  bp: 'BASIS POINTS',
  percent: 'PERCENT',
  'USD bn': 'USD BILLIONS',
};

function fixedDigits(unit: string) {
  if (unit === 'percent') return 2;
  if (unit === 'bp') return 1;
  if (unit === 'USD bn') return 0;
  return 2;
}

export function formatMetricValue(value: number | null | undefined, unit = '') {
  if (value == null) return '—';
  const digits = fixedDigits(unit);
  const formatted = new Intl.NumberFormat('en-US', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value);
  if (unit === 'bp') return `${formatted} bp`;
  if (unit === 'percent') return `${formatted}%`;
  if (unit === 'USD bn') return `${formatted}B`;
  return formatted;
}

function formatDelta(value: number | null | undefined, unit: string, withUnit = false) {
  if (value == null) return '—';
  const digits = unit === 'USD bn' || unit === 'bp' ? 1 : 2;
  const result = `${value > 0 ? '+' : ''}${new Intl.NumberFormat('en-US', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value)}`;
  if (!withUnit) return result;
  if (unit === 'bp') return `${result} bp`;
  if (unit === 'percent') return `${result}%`;
  if (unit === 'USD bn') return `${result}B`;
  return result;
}

function deltaClass(value: number | null | undefined) {
  if (value == null) return 'is-missing';
  if (value === 0) return 'is-zero';
  return value > 0 ? 'is-positive' : 'is-negative';
}

type StatusTone = 'positive' | 'neutral' | 'warning' | 'negative' | 'unavailable';

function statusTone(status: string): StatusTone {
  if (['normal', 'ample', 'ok'].includes(status)) return 'positive';
  if (status === 'neutral') return 'neutral';
  if (['watch', 'elevated', 'stale', 'not_released', 'manual_update_due'].includes(status)) return 'warning';
  if (['tightening', 'warning', 'stress', 'error'].includes(status)) return 'negative';
  return 'unavailable';
}

function statusStyle(status: string): CSSProperties {
  const tone = statusTone(status);
  return {
    '--status-color': `var(--${tone})`,
    '--status-fg': `var(--${tone}-fg)`,
  } as CSSProperties;
}

function updateStamp(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '—';
  return date.toISOString().slice(5, 16).replace('T', ' ');
}

function Badge({ status }: { status: string }) {
  return <span className={`badge badge-${status}`} data-status={status} style={statusStyle(status)}>{STATUS_TEXT[status] ?? status}</span>;
}

interface StatusBarProps {
  snapshot: Snapshot;
  onOpenSources: () => void;
}

function StatusBar({ snapshot, onOpenSources }: StatusBarProps) {
  const total = Object.keys(snapshot.sources).length;
  const healthTone = total > 0 && snapshot.source_health.ok === total
    ? 'var(--positive)'
    : snapshot.source_health.ok > 0
      ? 'var(--warning)'
      : 'var(--negative)';
  const overall = snapshot.overall_status || 'unavailable';
  return (
    <header className="status-bar">
      <div className="brand"><span className="brand-mark">USD·LIQ</span>
      <span className="brand-divider" aria-hidden="true" />
      <h1 className="brand-title">美元流動性監測</h1></div>
      <div className="status-cluster">
        <span className="status-item">MKT <strong>{snapshot.market_date ?? '—'}</strong></span>
        <span className="status-item">UPD <strong>{updateStamp(snapshot.generated_at)}</strong></span>
        <button className="status-item source-status" onClick={onOpenSources} type="button" aria-label="查看來源與健康狀態">
          SRC <strong>{snapshot.source_health.ok}/{total}</strong>
          <span className="health-dot" style={{ '--health-color': healthTone } as CSSProperties} aria-hidden="true" />
        </button>
        <span className="overall-pill" style={statusStyle(overall)}>{overall.toUpperCase()}</span>
      </div>
    </header>
  );
}

function SwitchStrip({ snapshot }: { snapshot: Snapshot }) {
  return (
    <section className="switch-strip" aria-label="三個監測開關">
      {SWITCHES.map((config) => {
        const value = snapshot.switches[config.id];
        const score = Math.max(0, Math.min(4, value?.score ?? 0));
        const style = statusStyle(value?.status ?? 'unavailable');
        return (
          <article className="switch-card" key={config.id} style={style}>
            <div className="switch-head">
              <span className="switch-number">{config.number}</span>
              <span className="switch-kicker">{config.kicker}</span>
              <strong className="switch-status">{value?.status ?? 'unavailable'}</strong>
            </div>
            <div className="switch-title-row">
              <h2>{config.title}</h2>
              <div className="meter" aria-label={`${score} / 4`}>
                {[0, 1, 2, 3].map((segment) => <span className={`meter-segment${segment < score ? ' is-filled' : ''}`} key={segment} />)}
              </div>
              <b className="switch-score">{score}/4</b>
            </div>
            <p className="switch-summary">{value?.summary ?? '資料暫時未提供。'}</p>
            <div className="switch-confidence">CONFIDENCE {(value?.confidence ?? 'low').toUpperCase()}</div>
          </article>
        );
      })}
    </section>
  );
}

interface LiveTapeProps {
  snapshot: Snapshot;
  series: SeriesMap;
  selected: string;
  onSelect: (id: string) => void;
}

function LiveTape({ snapshot, series, selected, onSelect }: LiveTapeProps) {
  const activeCount = TAPE_IDS.filter((id) => snapshot.metrics[id]?.value != null).length;
  return (
    <section className="panel tape-panel" aria-labelledby="live-tape-title">
      <div className="panel-header" id="live-tape-title"><span>LIVE TAPE</span><span>{activeCount} ACTIVE</span></div>
      <div className="tape-head" aria-hidden="true"><span>METRIC</span><span>TREND</span><span>LAST</span><span>1D Δ</span></div>
      <div className="tape-scroll">
        {TAPE_GROUPS.map((group) => (
          <div className="tape-group" key={group.label}>
            <h3 className="tape-group-title">{group.label}</h3>
            {group.ids.map((id) => {
              const metric = snapshot.metrics[id];
              if (!metric) return null;
              return (
                <button
                  className={`tape-row${selected === id ? ' is-selected' : ''}`}
                  type="button"
                  key={id}
                  onClick={() => onSelect(id)}
                  aria-pressed={selected === id}
                  title={`${metric.label} · as-of ${metric.as_of ?? '—'}`}
                >
                  <span className="tape-label">{TICKERS[id] ?? metric.label}</span>
                  <Sparkline points={series[id]?.observations ?? metric.short_series ?? []} selected={selected === id} label={metric.label} />
                  <strong className="tape-value">{formatMetricValue(metric.value, metric.unit)}</strong>
                  <span className={`tape-delta ${deltaClass(metric.delta_1d)}`}>{formatDelta(metric.delta_1d, metric.unit)}</span>
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
  onMain: (id: string) => void;
  onRange: (range: RangeKey) => void;
  onOverlay: (id: string) => void;
}

function ChartPanel({ snapshot, series, main, range, overlay, onMain, onRange, onOverlay }: ChartPanelProps) {
  const globalLatest = getGlobalLatestDate(series);
  const metric = snapshot.metrics[main] ?? snapshot.metrics.sofr_iorb_spread;
  const points = windowPoints(series[main]?.observations ?? metric.short_series ?? [], range, globalLatest);
  const overlaySeries = useMemo(() => Object.fromEntries(
    OVERLAY_CONFIG
      .filter(({ id }) => overlay[id])
      .map(({ id }) => [id, windowPoints(series[id]?.observations ?? snapshot.metrics[id]?.short_series ?? [], range, globalLatest)]),
  ), [globalLatest, overlay, range, series, snapshot.metrics]);
  const start = points[0]?.date ?? '—';
  const end = points.at(-1)?.date ?? '—';
  return (
    <section className="panel chart-panel" aria-label="主要流動性圖表">
      <div className="chart-toolbar">
        <div className="tab-group" aria-label="主要指標">
          {MAIN_TABS.map(([id, label]) => (
            <button className={`tab-button${main === id ? ' is-active' : ''}`} aria-label={`${label} 主圖指標`} aria-pressed={main === id} type="button" key={id} onClick={() => onMain(id)}>{label}</button>
          ))}
        </div>
        <div className="range-group" aria-label="圖表範圍">
          {RANGES.map((item) => <button className={`tab-button${range === item ? ' is-active' : ''}`} aria-pressed={range === item} type="button" key={item} onClick={() => onRange(item)}>{item}</button>)}
        </div>
      </div>
      <div className="readout">
        <div className="readout-primary">
          <div className="readout-label">{metric.label} · {UNIT_LABEL[metric.unit] ?? metric.unit.toUpperCase()}</div>
          <div className="readout-value">{formatMetricValue(metric.value, metric.unit)}</div>
        </div>
        <span className={`readout-delta ${deltaClass(metric.delta_1d)}`}>{formatDelta(metric.delta_1d, metric.unit, true)} 1D</span>
        <div className="readout-meta"><span>{start} → {end} · {points.length} pts</span><span>HOVER 睇每日數值</span></div>
      </div>
      <div className="main-chart">
        <MainMetricChart metricId={main} label={metric.label} unit={metric.unit} points={points} thresholdBp={THRESHOLD_BP} />
      </div>
      <div className="overlay-toolbar">
        <span className="overlay-title">OVERLAY · 隔夜利率</span>
        {OVERLAY_CONFIG.map(({ id, label, cssVariable }) => {
          const item = snapshot.metrics[id];
          return (
            <button
              type="button"
              key={id}
              className={`overlay-toggle${overlay[id] ? '' : ' is-off'}`}
              style={{ '--series-color': `var(${cssVariable})` } as CSSProperties}
              aria-label={`${label} 疊加序列`}
              aria-pressed={Boolean(overlay[id])}
              onClick={() => onOverlay(id)}
            >
              <i className="overlay-swatch" data-series={id} aria-hidden="true" />{label} <strong>{formatMetricValue(item?.value ?? null, item?.unit ?? 'percent')}</strong>
            </button>
          );
        })}
      </div>
      <div className="overlay-chart">
        <RateOverlayChart series={overlaySeries} selected={overlay} />
      </div>
    </section>
  );
}

function ReadRail({ snapshot, catalog, onMetric }: { snapshot: Snapshot; catalog: CatalogMetric[]; onMetric: (id: string) => void }) {
  const maxBalance = Math.max(...BALANCE_IDS.map((id) => snapshot.metrics[id]?.value ?? 0), 1);
  const missing = Object.entries(snapshot.metrics).filter(([id]) => !TAPE_IDS.some((tapeId) => tapeId === id));
  const catalogById = Object.fromEntries(catalog.map((item) => [item.id, item]));
  return (
    <aside className="panel read-rail" aria-label="今日解讀與指標狀態">
      <section className="read-section">
        <div className="read-kicker">READ · 今日粵文解讀</div>
        <h3 className="read-headline">{snapshot.explanations.headline}</h3>
        <div className="read-bullets">
        {snapshot.explanations.bullets.slice(0, 2).map((bullet, index) => (
          <div className="read-bullet" key={`${bullet.observation}-${index}`}><b className="read-index">0{index + 1}</b>{bullet.observation} {bullet.meaning}<span className="read-caveat">⚠ {bullet.caveat}</span></div>
        ))}
        </div>
        {snapshot.technical_context.length > 0 && (
          <div className="technical-context"><strong>技術日 CONTEXT</strong>{snapshot.technical_context.slice(0, 2).map((item) => <span key={`${item.date}-${item.note}`}>{item.date} · {item.note}</span>)}</div>
        )}
      </section>
      <section className="balance-section">
        <div className="balance-section-head"><span className="balance-kicker">BALANCE SHEET · 存量</span><span className="balance-unit">USD BN</span></div>
        {BALANCE_IDS.map((id, index) => {
          const item = snapshot.metrics[id];
          if (!item) return null;
          return (
            <div className="balance-row" key={id}>
              <div className="balance-row-head"><span className="balance-label">{item.label}</span><strong className="balance-value">{formatMetricValue(item.value, item.unit)}</strong><b className={`balance-delta ${deltaClass(item.delta_1d)}`}>{formatDelta(item.delta_1d, item.unit)}</b></div>
              <div className="balance-track"><span className="balance-fill" style={{ width: `${Math.max(0, ((item.value ?? 0) / maxBalance) * 100)}%`, '--bar-color': BALANCE_COLORS[index] } as CSSProperties} /></div>
              <small className="balance-meta">as-of {item.as_of ?? '—'} · {id === 'tga_daily' ? 'daily' : 'weekly'}</small>
            </div>
          );
        })}
      </section>
      <section className="not-wired-section">
        <div className="not-wired-head"><span className="not-wired-kicker">未接通 · NOT WIRED</span><span className="not-wired-count">{missing.length} 個</span></div>
        <p className="not-wired-copy">缺失數據永不當作零，只標示未接通。</p>
        <div className="chip-list">
          {missing.map(([id, metric]) => {
            const availability = catalogById[id]?.availability;
            const tag = metric.status === 'paid_data_unavailable' || availability === 'paid_required'
              ? 'PAID'
              : metric.status === 'manual_update_due'
                ? 'MANUAL'
                : '—';
            return <button className={`chip${metric.status === 'paid_data_unavailable' ? ' is-paid' : ''}${metric.status === 'manual_update_due' ? ' is-manual' : ''}`} data-status={metric.status} type="button" key={id} onClick={() => onMetric(id)}>{metric.label} <span className="chip-tag">{tag}</span></button>;
          })}
        </div>
      </section>
    </aside>
  );
}

function FooterTicker({ snapshotUrl, onSources }: { snapshotUrl: string; onSources: () => void }) {
  return (
    <footer className="footer-ticker">
      <strong>USD LIQUIDITY / OPEN MONITOR</strong><span>只供研究，並非投資建議</span>
      <span className="footer-actions"><a href={snapshotUrl} download="snapshot.json">下載 JSON ↓</a><button className="footer-action" type="button" onClick={onSources}>來源與方法 →</button></span>
    </footer>
  );
}

function Provenance({ snapshot }: { snapshot: Snapshot }) {
  const legend = [
    ['positive', 'OK / 正常', '官方來源已更新，數值可用。'],
    ['warning', 'WATCH / 過期', '數值存在但過期或待人工更新。'],
    ['negative', 'STRESS / 缺失', '抓取錯誤或需要付費供應商。'],
    ['unavailable', 'NOT WIRED', '尚未接通，永不以零代替。'],
  ];
  return (
    <section className="provenance-grid">
      <article className="provenance-panel">
        <div className="provenance-kicker">PROVENANCE · 來源健康</div>
        {Object.entries(snapshot.sources).map(([id, source]) => (
          <div className="source-row" key={id}>
            <div className="source-main"><a className="source-link" href={source.url} target="_blank" rel="noreferrer">{source.name} ↗</a><span className="source-meta">{source.frequency} · as-of {source.as_of ?? '—'}</span></div>
            <span className="source-quality">{source.quality.toUpperCase()}</span><Badge status={source.status} />
          </div>
        ))}
      </article>
      <article className="provenance-panel analysis-contract">
        <div className="provenance-kicker">ANALYSIS CONTRACT</div>
        <h2>訊號唔係結論。</h2>
        <p>本儀錶板將 price、stock/flow 同 backstop 分組，避免重複計算相關利率。+{THRESHOLD_BP} bp 係可配置操作門檻，唔係固定危機線；技術日只降低信心，唔會刪除原始觀察。</p>
        <div className="contract-legend">{legend.map(([tone, label, description]) => <div className="contract-item" key={label}><div className="contract-item-head"><span className="contract-swatch" style={{ '--legend-color': `var(--${tone})` } as CSSProperties} aria-hidden="true" /><b>{label}</b></div><p>{description}</p></div>)}</div>
      </article>
    </section>
  );
}

interface DrawerProps {
  mode: 'sources' | string;
  snapshot: Snapshot;
  catalog: CatalogMetric[];
  catalogError: string;
  onClose: () => void;
}

function Drawer({ mode, snapshot, catalog, catalogError, onClose }: DrawerProps) {
  const closeRef = useRef<HTMLButtonElement>(null);
  const drawerRef = useRef<HTMLElement>(null);
  useEffect(() => {
    const active = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    closeRef.current?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key !== 'Tab' || !drawerRef.current) return;
      const focusable = [...drawerRef.current.querySelectorAll<HTMLElement>('button, a[href], [tabindex]:not([tabindex="-1"])')].filter((element) => !element.hasAttribute('disabled'));
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable.at(-1)!;
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    };
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('keydown', onKeyDown);
      document.body.style.overflow = previousOverflow;
      active?.focus();
    };
  }, [onClose]);
  const onScrim = (event: MouseEvent<HTMLDivElement>) => { if (event.target === event.currentTarget) onClose(); };
  const sourceMode = mode === 'sources';
  const metric = sourceMode ? undefined : snapshot.metrics[mode];
  const catalogMetric = sourceMode ? undefined : catalog.find((item) => item.id === mode);
  const definitions: Array<[string, keyof CatalogMetric]> = [
    ['回答問題', 'question_answered'], ['點解要睇', 'why_track'], ['常見誤判', 'false_positives'],
    ['一齊確認', 'confirm_with'], ['唔可以推論', 'cannot_conclude'], ['計算方法', 'methodology'],
  ];
  const title = sourceMode ? '來源與健康狀態' : (catalogMetric?.label ?? metric?.label ?? mode);
  return (
    <div className="drawer-scrim" onClick={onScrim}>
      <aside className="drawer" ref={drawerRef} role="dialog" aria-modal="true" aria-labelledby="drawer-title">
        <button className="drawer-close" type="button" ref={closeRef} onClick={onClose} aria-label="關閉">×</button>
        <div className="drawer-kicker">{sourceMode ? 'PROVENANCE' : 'METRIC METHODOLOGY'}</div>
        <h2 id="drawer-title">{title}</h2>
        <div className="drawer-subtitle">{sourceMode
          ? `${snapshot.source_health.ok} / ${Object.keys(snapshot.sources).length} 來源正常`
          : catalogMetric
            ? `${catalogMetric.frequency} · ${catalogMetric.quality} · ${catalogMetric.availability}`
            : '方法資料暫時未提供'}</div>
        {sourceMode ? Object.entries(snapshot.sources).map(([id, source]) => <DrawerSource key={id} source={source} />) : (
          catalogMetric ? <dl className="drawer-def">{definitions.map(([term, key]) => catalogMetric[key] ? <div key={key}><dt>{term}</dt><dd>{String(catalogMetric[key])}</dd></div> : null)}</dl>
            : <p className="drawer-message">{catalogError || '方法資料暫時未提供。'}</p>
        )}
      </aside>
    </div>
  );
}

function DrawerSource({ source }: { source: Source }) {
  return <div className="drawer-source"><div className="drawer-source-main"><strong>{source.name}</strong><span className="source-meta">{source.frequency} · as-of {source.as_of ?? '—'}</span><a href={source.url} target="_blank" rel="noreferrer">官方來源 ↗</a></div><Badge status={source.status} /></div>;
}

export interface DashboardProps {
  snapshot: Snapshot;
  catalog: CatalogMetric[];
  catalogError: string;
  series: SeriesMap;
  main: string;
  range: RangeKey;
  overlay: Record<string, boolean>;
  drawer: 'sources' | string | null;
  baseUrl: string;
  onMain: (id: string) => void;
  onRange: (range: RangeKey) => void;
  onOverlay: (id: string) => void;
  onDrawer: (mode: 'sources' | string | null) => void;
}

export function Dashboard({ snapshot, catalog, catalogError, series, main, range, overlay, drawer, baseUrl, onMain, onRange, onOverlay, onDrawer }: DashboardProps) {
  const openSources = () => onDrawer('sources');
  return (
    <div className="app-shell">
      <div className="deck">
        <StatusBar snapshot={snapshot} onOpenSources={openSources} />
        <SwitchStrip snapshot={snapshot} />
        <main className="body-grid">
          <LiveTape snapshot={snapshot} series={series} selected={main} onSelect={onMain} />
          <ChartPanel snapshot={snapshot} series={series} main={main} range={range} overlay={overlay} onMain={onMain} onRange={onRange} onOverlay={onOverlay} />
          <ReadRail snapshot={snapshot} catalog={catalog} onMetric={onDrawer} />
        </main>
        <FooterTicker snapshotUrl={`${baseUrl}data/snapshot.json`} onSources={openSources} />
      </div>
      <Provenance snapshot={snapshot} />
      {drawer && <Drawer mode={drawer} snapshot={snapshot} catalog={catalog} catalogError={catalogError} onClose={() => onDrawer(null)} />}
    </div>
  );
}

export function StateScreen({ error }: { error?: string }) {
  return (
    <main className="state-screen" role={error ? 'alert' : 'status'} aria-live="polite">
      {error ? <><h1>暫時未能載入數據</h1><p>現有 snapshot 無法讀取（{error}）。請稍後再試；系統不會以零代替缺失值。</p></> : <><div className="loader" aria-hidden="true" /><p>載入已驗證 snapshot…</p></>}
    </main>
  );
}
