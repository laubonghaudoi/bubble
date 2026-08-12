// @vitest-environment jsdom

import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import App from './App';
import {
  loadDashboardCore,
  loadRouteSeries,
  routeMetricIds,
  snapshotSeriesFallback,
  type RouteId,
} from './dashboard';
import { makeCatalog, makeSnapshot } from './test-fixtures';

vi.mock('./components/Charts', () => ({
  MainMetricChart: ({ label, lastGood }: { label: string; lastGood?: boolean }) => <div role="img" aria-label={`${label} 圖表${lastGood ? '，最後成功值，並非今日新值' : ''}`} />,
  OVERLAY_CONFIG: [
    { id: 'sofr', label: 'SOFR', colour: '#0064FA', cssVariable: '--series-sofr' },
    { id: 'iorb', label: 'IORB', colour: '#E51503', cssVariable: '--series-iorb' },
    { id: 'effr', label: 'EFFR', colour: '#000000', cssVariable: '--series-effr' },
    { id: 'obfr', label: 'OBFR', colour: '#338736', cssVariable: '--series-obfr' },
    { id: 'tgcr', label: 'TGCR', colour: '#8A4A00', cssVariable: '--series-tgcr' },
    { id: 'bgcr', label: 'BGCR', colour: '#767676', cssVariable: '--series-bgcr' },
  ],
  RateOverlayChart: ({ lastGoodIds = [] }: { lastGoodIds?: readonly string[] }) => <div role="img" aria-label={`隔夜利率疊加圖${lastGoodIds.length ? `，最後成功值：${lastGoodIds.join('、')}` : ''}`} />,
  Sparkline: ({ label, lastGood }: { label: string; lastGood?: boolean }) => <svg role="img" aria-label={`${label}${lastGood ? '，最後成功值，並非今日新值' : ''}`} />,
}));

vi.mock('./dashboard', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./dashboard')>();
  return { ...actual, loadDashboardCore: vi.fn(), loadRouteSeries: vi.fn() };
});

const snapshot = makeSnapshot({
  reserve_balances: { changes: { one_observation: 1, five_observations: 5, one_week: 2, four_weeks: 4 } },
});
const catalog = makeCatalog();

function routeSeries(route: RouteId) {
  return {
    series: Object.fromEntries(routeMetricIds(route, catalog, snapshot).map((id) => [id, snapshotSeriesFallback(snapshot, id)])),
    errors: {},
  };
}

async function findRouteHeading(name: string) {
  return waitFor(() => {
    const heading = [...document.querySelectorAll<HTMLElement>('.route-heading')]
      .find((item) => item.textContent === name);
    expect(heading).toBeDefined();
    return heading!;
  });
}

beforeEach(() => {
  window.history.replaceState(null, '', '/#/overview');
  window.localStorage.clear();
  window.localStorage.setItem('liq-theme', 'dark');
  document.documentElement.dataset.theme = 'dark';
  const meta = document.querySelector<HTMLMetaElement>('meta[name="theme-color"]') ?? document.createElement('meta');
  meta.name = 'theme-color'; meta.content = '#ffffff'; if (!meta.isConnected) document.head.append(meta);
  vi.mocked(loadDashboardCore).mockResolvedValue({ snapshot, catalog, catalogError: null });
  vi.mocked(loadRouteSeries).mockImplementation(async (_base, route) => routeSeries(route));
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('v2 routed dashboard', () => {
  it('renders overview with ON RRP/SRF and frequency-aware changes, without NOT WIRED', async () => {
    render(<App />);
    expect(screen.getByRole('status')).toHaveTextContent('v2 snapshot');
    await screen.findByText('USD·LIQ');
    expect(screen.getByText('ON RRP')).toBeVisible();
    expect(screen.getByText('SRF')).toBeVisible();
    expect(screen.queryByText(/NOT WIRED/)).not.toBeInTheDocument();
    expect(screen.getAllByText('1 OBS').length).toBeGreaterThan(0);
    expect(screen.getAllByText('1W').length).toBeGreaterThan(0);
    expect(screen.getByText('IMPLEMENTATION STATUS')).toBeVisible();
    expect(screen.getByRole('button', { name: '8W' })).toBeVisible();
    expect(screen.getByRole('button', { name: '12W' })).toBeVisible();
    expect(screen.getByText('REGIME WINDOW')).toBeVisible();
    expect(screen.getByText(/uses the FRED® API but is not endorsed/)).toBeVisible();
    expect(screen.getByRole('link', { name: /FRED® API Terms of Use/ })).toHaveAttribute(
      'href',
      'https://fred.stlouisfed.org/docs/api/terms_of_use.html',
    );
    expect(screen.getByText(/New York Fed is not responsible for publication/)).toBeVisible();
    expect(screen.getByText(/is not affiliated with the New York Fed/)).toBeVisible();
    expect(screen.getByText(/does not sanction, endorse, or recommend/)).toBeVisible();
    expect(screen.getByText(/Positions are measured as of Tuesday and normally released Friday/)).toBeVisible();
    expect(screen.getByText(/neither is “CTA exposure”/)).toBeVisible();
    expect(screen.getByRole('link', { name: /official TFF Futures Only dataset/ })).toHaveAttribute('href', 'https://publicreporting.cftc.gov/Commitments-of-Traders/TFF-Futures-Only/gpe5-46if');
    expect(screen.getByRole('link', { name: /COT release schedule/ })).toHaveAttribute('href', 'https://www.cftc.gov/MarketReports/CommitmentsofTraders/ReleaseSchedule/index.htm');
    expect(screen.getByRole('link', { name: /CFTC Web Policy/ })).toHaveAttribute('href', 'https://www.cftc.gov/WebPolicy/index.htm');
    expect(screen.getByText(/No CFTC seal or logo is used/)).toBeVisible();
    expect(window.localStorage.getItem('liq-theme')).toBeNull();
    expect(document.documentElement).not.toHaveAttribute('data-theme');
  });

  it('supports deep links, hash navigation, route focus, and switch-card arrow navigation', async () => {
    window.history.replaceState(null, '', '/#/market-ignition');
    render(<App />);
    const marketHeading = await findRouteHeading('市場引信');
    await waitFor(() => expect(marketHeading).toHaveFocus());
    expect(screen.getByText(/P1 · CFTC TFF FUTURES ONLY/)).toBeVisible();
    expect(screen.getByText(/P2 · BUBBLE/)).toBeVisible();
    expect(vi.mocked(loadRouteSeries)).toHaveBeenCalledWith(expect.any(String), 'market-ignition', snapshot, catalog);

    const switches = screen.getAllByRole('link').filter((link) => link.classList.contains('switch-card'));
    expect(switches.map((link) => link.getAttribute('href'))).toEqual(['#/liquidity-fuel', '#/market-ignition', '#/fundamental-exit']);
    switches[0].focus();
    fireEvent.keyDown(switches[0], { key: 'ArrowRight' });
    expect(switches[1]).toHaveFocus();

    window.location.hash = '#/fundamental-exit';
    window.dispatchEvent(new HashChangeEvent('hashchange'));
    const fundamentalHeading = await findRouteHeading('基本面逃生門');
    await waitFor(() => expect(fundamentalHeading).toHaveFocus());
    expect(screen.getByText(/P3 · CAPEX/)).toBeVisible();

    window.location.hash = '#/overview';
    window.dispatchEvent(new HashChangeEvent('hashchange'));
    const overviewHeading = await findRouteHeading('總覽');
    await waitFor(() => expect(overviewHeading).toHaveFocus());
  });

  it('renders P1 as four evidence-only blocks with quantitative CFTC cards and fail-closed rights holds', async () => {
    window.history.replaceState(null, '', '/#/market-ignition');
    const { container } = render(<App />);
    await findRouteHeading('市場引信');

    expect(snapshot.switches.market_ignition.assessment).toBeNull();
    const coverage = screen.getByRole('region', { name: /Market Ignition evidence coverage/ });
    expect(coverage).toHaveTextContent('1/4 AVAILABLE');
    expect(coverage.querySelectorAll('.evidence-card')).toHaveLength(4);
    expect(coverage).toHaveTextContent('MIXED');
    expect(coverage).toHaveTextContent('CONFIDENCE LOW');
    expect(coverage).toHaveTextContent('UNAVAILABLE · CONFIDENCE UNKNOWN · NOT AN IMPLIED NEUTRAL');
    const directions = [...coverage.querySelectorAll<HTMLElement>('.evidence-direction b')].map(({ textContent }) => textContent);
    expect(directions).toEqual(['UNKNOWN', 'MIXED', 'UNKNOWN', 'UNKNOWN']);
    expect(directions.join(' ')).not.toMatch(/WATCH|STRESS|NEUTRAL/);

    const cftc = screen.getByRole('region', { name: 'P1 · CFTC TFF FUTURES ONLY' });
    expect(cftc.querySelectorAll('.cftc-card')).toHaveLength(4);
    expect(within(cftc).getAllByText('E-MINI S&P 500')).toHaveLength(2);
    expect(within(cftc).getAllByText('NASDAQ-100 CONSOLIDATED')).toHaveLength(2);
    expect(within(cftc).getAllByText('ASSET MANAGER / INSTITUTIONAL')).toHaveLength(2);
    expect(within(cftc).getAllByText('LEVERAGED FUNDS · PROXY')).toHaveLength(2);
    expect(within(cftc).getAllByText('免費自動')).toHaveLength(2);
    expect(within(cftc).getAllByText('免費代理')).toHaveLength(2);
    expect(within(cftc).getAllByText('123,456')).toHaveLength(2);
    expect(within(cftc).getAllByText('+1.25 pp')).toHaveLength(2);
    expect(within(cftc).getAllByText('-0.75 pp')).toHaveLength(2);
    expect(within(cftc).getAllByText('NET LONG')).toHaveLength(2);
    expect(within(cftc).getAllByText('NET SHORT')).toHaveLength(2);
    expect(within(cftc).getAllByText('AS-OF · TUE POSITIONS')).toHaveLength(4);

    fireEvent.click(within(cftc).getByRole('button', { name: '12W' }));
    expect(within(cftc).getByRole('button', { name: '12W' })).toHaveAttribute('aria-pressed', 'true');
    expect(within(cftc).getAllByRole('img', { name: /12W regime window/ })).toHaveLength(4);

    const gates = screen.getByRole('region', { name: 'P1 · RIGHTS-GATED PROVIDER INTERFACES' });
    const vix = gates.querySelector<HTMLElement>('[data-metric-id="vix_vix3m_term_structure_proxy"]');
    expect(vix).toHaveTextContent('—');
    expect(vix).toHaveTextContent('No redistribution-cleared Cboe feed is configured.');
    expect(vix).toHaveTextContent('免費數據不足');
    expect(container.querySelector('[data-metric-id="vix_vix3m_term_structure_proxy"] .rights-null')).toHaveTextContent('—');
  });

  it('renders P2 as an independent 2/8 fragility context with exact proxy and audit boundaries', async () => {
    window.history.replaceState(null, '', '/#/market-ignition');
    const { container } = render(<App />);
    await findRouteHeading('市場引信');

    const p1 = screen.getByRole('region', { name: /Market Ignition evidence coverage/ });
    expect(p1).toHaveTextContent('1/4 AVAILABLE');
    expect(snapshot.switches.market_ignition.assessment).toBeNull();
    expect(snapshot.overall_assessment).toBe(snapshot.switches.liquidity_fuel.assessment);

    const fragility = screen.getByRole('region', { name: 'P2 · BUBBLE / FRAGILITY CONTEXT' });
    expect(fragility).toHaveTextContent('2/8 CONTEXT AVAILABLE');
    expect(fragility).toHaveTextContent('CONTEXT ONLY');
    expect(fragility.querySelectorAll('.fragility-card')).toHaveLength(2);
    expect(fragility.querySelector('.badge-watch, .badge-stress')).toBeNull();

    const macro = fragility.querySelector<HTMLElement>('[data-metric-id="nonfinancial_equities_gdp_proxy"]')!;
    expect(macro).toHaveTextContent('184.25%');
    expect(macro).toHaveTextContent('+3.10 pp');
    expect(macro).toHaveTextContent('+1.71%');
    expect(macro).toHaveTextContent('+9.42%');
    expect(macro).toHaveTextContent('88.5%');
    expect(macro).toHaveTextContent('40 common quarters');
    expect(macro).toHaveTextContent('56,800B');
    expect(macro).toHaveTextContent('30,828B');
    expect(macro).toHaveTextContent('2026-Q1');
    expect(macro).toHaveTextContent('Nonfinancial corporate equity liabilities are not total U.S. equity market capitalization.');

    const form4 = fragility.querySelector<HTMLElement>('[data-metric-id="sec_form4_nonderivative_ps_count_ratio_20d"]')!;
    expect(form4).toHaveTextContent('0.42');
    expect(form4).toHaveTextContent('0.55');
    expect(form4).toHaveTextContent('EXPLICIT-FALSE · 20D');
    expect(form4).toHaveTextContent('0.61');
    expect(form4).toHaveTextContent('81.0% eligible-row coverage');
    expect(form4).toHaveTextContent('76.0% priced-row coverage · INSUFFICIENT PRICE COVERAGE');
    expect(form4).toHaveTextContent('84.0% priced-row coverage · PUBLISHED');
    expect(form4).toHaveTextContent('138 / 116');
    expect(form4).toHaveTextContent('107 / 104 / 88');
    expect(form4).toHaveTextContent('103 / 4');
    expect(form4).toHaveTextContent('2 / 2');
    expect(form4).toHaveTextContent('44 / 51 / 12');
    expect(form4).toHaveTextContent('2026-07-15 → 2026-08-11');
    expect(form4).toHaveTextContent(/P\/S includes open-market OR private/);
    expect(form4).toHaveTextContent(/filing-level and includes only filings explicitly marked false/);
    expect(form4).toHaveTextContent(/amendments that cannot be reliably linked are quarantined for review/);

    fireEvent.click(within(form4).getByRole('button', { name: /完整方法、來源與審核限制/ }));
    const form4Drawer = await screen.findByRole('dialog', { name: 'SEC Form 4 non-derivative P/S count ratio · 20D' });
    expect(form4Drawer).toHaveTextContent('dollar_coverage_rate_20d');
    expect(form4Drawer).toHaveTextContent('84.0%');
    expect(form4Drawer).toHaveTextContent('eligible_transaction_count_20d');
    expect(form4Drawer).toHaveTextContent('138');
    expect(form4Drawer).not.toHaveTextContent('138.00');
    fireEvent.keyDown(document, { key: 'Escape' });
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());

    const held = screen.getByRole('region', { name: 'P2 · UNAVAILABLE FREE' });
    expect(held).toHaveTextContent('6 LOCKED INTERFACES · FAIL CLOSED');
    expect(held.querySelectorAll('.rights-gate-card')).toHaveLength(6);
    expect(held.querySelectorAll('.rights-null')).toHaveLength(6);
    expect(held).toHaveTextContent('FINRA terms do not clear automated database construction or public redistribution.');
    expect(held).toHaveTextContent('A consistent reproducible forward-earnings consensus is proprietary.');
    expect(held).toHaveTextContent('Reliable dealer net-gamma and trade-direction inputs are not publicly available.');
    expect(container.querySelector('[data-metric-id="put_call_vol_skew"]')).toBeNull();
  });

  it('keeps the P2 snapshot fallback visible when the methodology manifest fails', async () => {
    window.history.replaceState(null, '', '/#/market-ignition');
    vi.mocked(loadDashboardCore).mockResolvedValueOnce({ snapshot, catalog: [], catalogError: '503 manifest offline' });
    render(<App />);
    await findRouteHeading('市場引信');
    expect(screen.getByText('Manifest 暫時不可用：503 manifest offline')).toHaveAttribute('role', 'status');
    expect(screen.getByRole('region', { name: 'P2 · BUBBLE / FRAGILITY CONTEXT' })).toHaveTextContent('2/8 CONTEXT AVAILABLE');
    expect(screen.getByRole('region', { name: 'P2 · UNAVAILABLE FREE' }).querySelectorAll('.rights-gate-card')).toHaveLength(6);
  });

  it('renders the detailed P0 page and confirmation spreads', async () => {
    window.history.replaceState(null, '', '/#/liquidity-fuel');
    render(<App />);
    await findRouteHeading('流動性燃料');
    expect(screen.getByText('IORB CONFIRMATION SPREADS')).toBeVisible();
    expect(screen.getByRole('button', { name: /EFFR_IORB_SPREAD_BP/ })).toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: /EFFR_IORB_SPREAD_BP/ }));
    expect(screen.getByRole('button', { name: 'EFFR−IORB 主圖指標' })).toHaveAttribute('aria-pressed', 'true');
    fireEvent.click(screen.getByRole('button', { name: 'RESERVES 主圖指標' }));
    expect(screen.getByRole('img', { name: 'RESERVE_BALANCES 圖表' })).toBeVisible();
    expect(screen.getByText(/2\.9T.*銀行體系規模/)).toBeVisible();
  });

  it('shows v2 availability, health, freshness, timestamps and rights in the drawer', async () => {
    window.history.replaceState(null, '', '/#/market-ignition');
    render(<App />);
    await findRouteHeading('市場引信');
    const metricButton = screen.getByRole('button', { name: /開啟 CFTC_E_MINI_SP500_LEVERAGED_FUNDS_NET_PCT_OI 方法/ });
    metricButton.focus();
    fireEvent.click(metricButton);
    const dialog = await screen.findByRole('dialog', { name: 'CFTC_E_MINI_SP500_LEVERAGED_FUNDS_NET_PCT_OI' });
    expect(dialog).toHaveTextContent('免費代理');
    expect(dialog).toHaveTextContent('正常');
    expect(dialog).toHaveTextContent('新鮮');
    expect(dialog).toHaveTextContent('OBSERVATION');
    expect(dialog).toHaveTextContent('RELEASED');
    expect(dialog).toHaveTextContent('PIPELINE UPDATED');
    expect(dialog).toHaveTextContent('LAST ATTEMPT');
    expect(dialog).toHaveTextContent('STATISTICS');
    expect(dialog).toHaveTextContent('net_position');
    expect(dialog).toHaveTextContent('-45,678');
    expect(dialog).not.toHaveTextContent('-45,678.00');
    expect(dialog).toHaveTextContent('-0.75 pp');
    expect(dialog).toHaveTextContent('RIGHTS / USE');
    fireEvent.keyDown(document, { key: 'Escape' });
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(metricButton).toHaveFocus();

    fireEvent.click(screen.getByRole('button', { name: '查看來源與健康狀態' }));
    const sourcesDialog = await screen.findByRole('dialog', { name: '來源與健康狀態' });
    expect(sourcesDialog).toHaveTextContent('LAST ATTEMPT');
    expect(sourcesDialog).toHaveTextContent('LAST SUCCESS');
    expect(within(sourcesDialog).getByRole('link', { name: /official TFF Futures Only dataset/ })).toBeVisible();
    expect(within(sourcesDialog).getByRole('link', { name: /CFTC Web Policy/ })).toBeVisible();
    expect(within(sourcesDialog).getByRole('link', { name: /official EDGAR daily indexes/ })).toHaveAttribute('href', 'https://www.sec.gov/Archives/edgar/daily-index/');
    expect(within(sourcesDialog).getByRole('link', { name: /Form 4 instructions/ })).toHaveAttribute('href', 'https://www.sec.gov/files/form4.pdf');
    expect(sourcesDialog).toHaveTextContent(/transaction codes P and S cover open-market or private/);
    expect(sourcesDialog).toHaveTextContent(/not affiliated with or endorsed by the SEC/);
  });

  it('keeps non-OK numeric values visible but labels every dashboard surface as last-good', async () => {
    const staleQuality = {
      status: 'STALE' as const,
      freshness: 'STALE' as const,
      last_attempt_at: '2026-08-12T17:32:49Z',
      last_success_at: '2026-08-11T17:32:49Z',
      failure_reason: 'collector offline',
      sample_size: 40,
    };
    const notReleasedQuality = {
      ...staleQuality,
      status: 'NOT_RELEASED_YET' as const,
      freshness: 'LATE' as const,
      failure_reason: 'today\'s release is not available yet',
    };
    const staleSnapshot = makeSnapshot({
      sofr_iorb_spread_bp: { value: 1, quality: staleQuality },
      sofr: { value: 1, quality: notReleasedQuality },
      reserve_balances: { value: 1, quality: staleQuality },
    });
    vi.mocked(loadDashboardCore).mockResolvedValueOnce({ snapshot: staleSnapshot, catalog, catalogError: null });

    const { container } = render(<App />);
    await screen.findByText('USD·LIQ');

    const tapeRows = [...container.querySelectorAll<HTMLElement>('.tape-row')];
    const spreadRow = tapeRows.find((row) => row.querySelector('.tape-label')?.textContent === 'SOFR−IORB');
    const sofrRow = tapeRows.find((row) => row.querySelector('.tape-label')?.textContent === 'SOFR');
    const iorbRow = tapeRows.find((row) => row.querySelector('.tape-label')?.textContent === 'IORB');
    expect(spreadRow).toHaveAttribute('data-value-state', 'last-good');
    expect(spreadRow).toHaveTextContent('1.0 bp');
    expect(spreadRow?.querySelector('.last-good-tag')).toHaveTextContent('LAST-GOOD');
    expect(sofrRow).toHaveAttribute('data-value-state', 'last-good');
    expect(sofrRow?.querySelector('.last-good-tag')).toHaveTextContent('LAST-GOOD');
    expect(iorbRow).toHaveAttribute('data-value-state', 'current');
    expect(iorbRow?.querySelector('.last-good-tag')).toBeNull();

    const readout = container.querySelector<HTMLElement>('.readout[data-value-state="last-good"]');
    expect(readout).toHaveTextContent('1.0 bp');
    expect(readout?.querySelector('.last-good-tag')).toHaveTextContent('LAST-GOOD');
    expect(screen.getByRole('img', { name: /SOFR_IORB_SPREAD_BP 圖表.*並非今日新值/ })).toBeVisible();
    expect(screen.getByRole('img', { name: 'SOFR_IORB_SPREAD_BP，最後成功值，並非今日新值' })).toBeVisible();

    const sofrOverlay = screen.getByRole('button', { name: /SOFR 疊加序列.*並非今日新值/ });
    expect(sofrOverlay).toHaveAttribute('data-value-state', 'last-good');
    expect(sofrOverlay.querySelector('.last-good-tag')).toHaveTextContent('LAST-GOOD');
    expect(screen.getByRole('img', { name: /隔夜利率疊加圖，最後成功值：.*sofr/ })).toBeVisible();

    const reserves = [...container.querySelectorAll<HTMLElement>('.balance-row')]
      .find((row) => row.querySelector('.balance-label')?.textContent === 'RESERVE_BALANCES');
    expect(reserves).toHaveAttribute('data-value-state', 'last-good');
    expect(reserves?.querySelector('.last-good-tag')).toHaveTextContent('LAST-GOOD');

    window.location.hash = '#/liquidity-fuel';
    window.dispatchEvent(new HashChangeEvent('hashchange'));
    await findRouteHeading('流動性燃料');
    const confirmation = container.querySelector<HTMLElement>('.metric-card[data-value-state="last-good"]');
    expect(confirmation).toHaveTextContent('SOFR_IORB_SPREAD_BP');
    expect(confirmation?.querySelector('.last-good-tag')).toHaveTextContent('LAST-GOOD');
  });

  it('marks methodology/catalog data unavailable in every metric drawer when manifest loading fails', async () => {
    vi.mocked(loadDashboardCore).mockResolvedValueOnce({ snapshot, catalog: [], catalogError: '503 manifest offline' });
    render(<App />);
    await screen.findByText('USD·LIQ');

    for (const metricLabel of ['SOFR_IORB_SPREAD_BP', 'IORB']) {
      fireEvent.click(screen.getByRole('button', { name: metricLabel }));
      const dialog = await screen.findByRole('dialog', { name: metricLabel });
      expect(dialog).toHaveTextContent('Manifest／方法目錄暫時不可用');
      expect(dialog).toHaveTextContent('503 manifest offline');
      expect(dialog).toHaveTextContent('方法目錄完整性未能確認');
      fireEvent.keyDown(document, { key: 'Escape' });
      await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    }
  });

  it('announces per-series fallback and fatal v2 snapshot errors', async () => {
    vi.mocked(loadRouteSeries).mockResolvedValueOnce({
      series: routeSeries('overview').series,
      errors: { sofr: '503 offline' },
    });
    const first = render(<App />);
    await screen.findByText('USD·LIQ');
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('1 條完整時間序列'));
    first.unmount();

    vi.mocked(loadDashboardCore).mockRejectedValueOnce(new Error('Invalid v2 snapshot payload'));
    render(<App />);
    expect(await screen.findByRole('alert')).toHaveTextContent('Invalid v2 snapshot payload');
    expect(screen.getByRole('alert')).toHaveTextContent('不會以零代替缺失值');
  });
});
