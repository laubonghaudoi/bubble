// @vitest-environment jsdom

import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import snapshotJson from '../public/data/snapshot.json';
import manifestJson from '../public/data/manifest.json';
import App from './App';
import {
  SERIES_IDS,
  loadDashboardData,
  snapshotSeriesFallback,
  type DashboardData,
} from './dashboard';
import type { CatalogMetric, Snapshot } from './types';

vi.mock('./components/Charts', () => ({
  MainMetricChart: ({ label }: { label: string }) => <div role="img" aria-label={`${label} 圖表`} />,
  OVERLAY_CONFIG: [
    { id: 'sofr', label: 'SOFR', colour: 'accent', cssVariable: '--series-sofr' },
    { id: 'iorb', label: 'IORB', colour: 'negative', cssVariable: '--series-iorb' },
    { id: 'effr', label: 'EFFR', colour: 'ink', cssVariable: '--series-effr' },
    { id: 'obfr', label: 'OBFR', colour: 'positive', cssVariable: '--series-obfr' },
    { id: 'tgcr', label: 'TGCR', colour: 'warning', cssVariable: '--series-tgcr' },
    { id: 'bgcr', label: 'BGCR', colour: 'unavailable', cssVariable: '--series-bgcr' },
  ],
  RateOverlayChart: () => <div role="img" aria-label="隔夜利率疊加圖" />,
  Sparkline: ({ label }: { label: string }) => <svg role="img" aria-label={label} />,
}));

vi.mock('./dashboard', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./dashboard')>();
  return { ...actual, loadDashboardData: vi.fn() };
});

const snapshot = snapshotJson as unknown as Snapshot;
const catalog = manifestJson.metrics as unknown as CatalogMetric[];

function dashboardData(overrides: Partial<DashboardData> = {}): DashboardData {
  return {
    snapshot,
    catalog,
    catalogError: null,
    series: Object.fromEntries(SERIES_IDS.map((id) => [id, snapshotSeriesFallback(snapshot, id)])),
    seriesErrors: {},
    ...overrides,
  };
}

beforeEach(() => {
  window.localStorage.clear();
  window.localStorage.setItem('liq-theme', 'dark');
  document.documentElement.dataset.theme = 'dark';
  const meta = document.querySelector<HTMLMetaElement>('meta[name="theme-color"]') ?? document.createElement('meta');
  meta.name = 'theme-color';
  meta.content = '#ffffff';
  if (!meta.isConnected) document.head.append(meta);
  vi.mocked(loadDashboardData).mockResolvedValue(dashboardData());
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('App dashboard interactions', () => {
  it('loads the ordered terminal deck and keeps zero scores distinct from missing values', async () => {
    render(<App />);
    expect(screen.getByRole('status')).toHaveTextContent('載入已驗證 snapshot');
    await screen.findByText('USD·LIQ');

    const switchHeadings = screen.getAllByRole('heading', { level: 2 }).slice(0, 3);
    expect(switchHeadings.map((heading) => heading.textContent)).toEqual(['流動性燃料', '市場引信', '基本面逃生門']);
    expect(screen.getAllByText('0/4')).toHaveLength(3);
    expect(screen.getByText('缺失數據永不當作零，只標示未接通。')).toBeVisible();
  }, 15_000);

  it('clears the legacy theme preference and supports tabs, ranges, and overlay toggles', async () => {
    render(<App />);
    await screen.findByText('USD·LIQ');

    expect(document.documentElement).not.toHaveAttribute('data-theme');
    expect(window.localStorage.getItem('liq-theme')).toBeNull();
    expect(document.querySelector('meta[name="theme-color"]')).toHaveAttribute('content', '#000000');
    expect(screen.queryByRole('button', { name: /切換至.*主題/ })).not.toBeInTheDocument();
    expect(screen.queryByText('DARK')).not.toBeInTheDocument();
    expect(screen.queryByText('LIGHT')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'SOFR 主圖指標' }));
    expect(screen.getByRole('button', { name: 'SOFR 主圖指標' })).toHaveAttribute('aria-pressed', 'true');
    fireEvent.click(screen.getByRole('button', { name: '1M' }));
    expect(screen.getByRole('button', { name: '1M' })).toHaveAttribute('aria-pressed', 'true');
    const obfr = screen.getByRole('button', { name: 'OBFR 疊加序列' });
    fireEvent.click(obfr);
    expect(obfr).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('link', { name: /下載 JSON/ })).toHaveAttribute('download', 'snapshot.json');
  }, 15_000);

  it('maps status tones and every delta sign to semantic classes', async () => {
    const semanticSnapshot = JSON.parse(JSON.stringify(snapshot)) as Snapshot;
    semanticSnapshot.overall_status = 'neutral';
    semanticSnapshot.switches.liquidity_fuel.status = 'ample';
    semanticSnapshot.switches.market_ignition.status = 'watch';
    semanticSnapshot.switches.fundamental_exit.status = 'stress';
    semanticSnapshot.metrics.sofr.delta_1d = 1;
    semanticSnapshot.metrics.iorb.delta_1d = -1;
    semanticSnapshot.metrics.effr.delta_1d = 0;
    semanticSnapshot.metrics.obfr.delta_1d = null;
    semanticSnapshot.metrics.fed_total_assets.delta_1d = 0;
    vi.mocked(loadDashboardData).mockResolvedValueOnce(dashboardData({ snapshot: semanticSnapshot }));

    render(<App />);
    await screen.findByText('USD·LIQ');

    const switches = [...document.querySelectorAll<HTMLElement>('.switch-card')];
    expect(switches[0].style.getPropertyValue('--status-color')).toBe('var(--positive)');
    expect(switches[0].style.getPropertyValue('--status-fg')).toBe('var(--positive-fg)');
    expect(switches[1].style.getPropertyValue('--status-color')).toBe('var(--warning)');
    expect(switches[2].style.getPropertyValue('--status-color')).toBe('var(--negative)');
    expect(document.querySelector<HTMLElement>('.overall-pill')?.style.getPropertyValue('--status-color')).toBe('var(--neutral)');
    expect(document.querySelector<HTMLElement>('.health-dot')?.style.getPropertyValue('--health-color')).toBe('var(--warning)');

    const tapeDelta = (ticker: string) => [...document.querySelectorAll<HTMLElement>('.tape-row')]
      .find((row) => row.querySelector('.tape-label')?.textContent === ticker)
      ?.querySelector<HTMLElement>('.tape-delta');
    expect(tapeDelta('SOFR')).toHaveClass('is-positive');
    expect(tapeDelta('IORB')).toHaveClass('is-negative');
    expect(tapeDelta('EFFR')).toHaveClass('is-zero');
    expect(tapeDelta('OBFR')).toHaveClass('is-missing');
    expect(tapeDelta('OBFR')).toHaveTextContent('—');

    const balanceRow = [...document.querySelectorAll<HTMLElement>('.balance-row')]
      .find((row) => row.querySelector('.balance-label')?.textContent === 'Fed Total Assets');
    expect(balanceRow?.querySelector('.balance-delta')).toHaveClass('is-zero');
  }, 15_000);

  it('opens both drawers and closes the modal with Escape while restoring focus', async () => {
    render(<App />);
    await screen.findByText('USD·LIQ');

    const sources = screen.getByRole('button', { name: '查看來源與健康狀態' });
    sources.focus();
    fireEvent.click(sources);
    expect(await screen.findByRole('dialog', { name: '來源與健康狀態' })).toBeVisible();
    expect(screen.getByRole('button', { name: '關閉' })).toHaveFocus();
    fireEvent.keyDown(document, { key: 'Escape' });
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(sources).toHaveFocus();

    fireEvent.click(sources);
    fireEvent.click(document.querySelector('.drawer-scrim')!);
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(sources).toHaveFocus();

    fireEvent.click(screen.getByRole('button', { name: /Gamma flip level/ }));
    expect(await screen.findByRole('dialog', { name: 'Gamma flip level' })).toHaveTextContent('計算方法');
  }, 15_000);

  it('keeps manifest failure nonfatal and announces fatal snapshot errors', async () => {
    vi.mocked(loadDashboardData).mockResolvedValueOnce(dashboardData({ catalog: [], catalogError: 'manifest offline' }));
    const first = render(<App />);
    await screen.findByText('USD·LIQ');
    fireEvent.click(screen.getByRole('button', { name: /Gamma flip level/ }));
    expect(await screen.findByRole('dialog')).toHaveTextContent('manifest offline');
    first.unmount();

    vi.mocked(loadDashboardData).mockRejectedValueOnce(new Error('snapshot offline'));
    render(<App />);
    expect(await screen.findByRole('alert')).toHaveTextContent('snapshot offline');
    expect(screen.getByRole('alert')).toHaveTextContent('不會以零代替缺失值');
  }, 15_000);
});
