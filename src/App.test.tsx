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
  document.documentElement.dataset.theme = 'light';
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

  it('persists theme and supports tabs, ranges, and overlay toggles', async () => {
    render(<App />);
    await screen.findByText('USD·LIQ');

    fireEvent.click(screen.getByRole('button', { name: '切換至深色主題' }));
    await waitFor(() => expect(document.documentElement.dataset.theme).toBe('dark'));
    expect(window.localStorage.getItem('liq-theme')).toBe('dark');
    expect(screen.getByRole('button', { name: '切換至淺色主題' })).toHaveTextContent('LIGHT');

    fireEvent.click(screen.getByRole('button', { name: 'SOFR 主圖指標' }));
    expect(screen.getByRole('button', { name: 'SOFR 主圖指標' })).toHaveAttribute('aria-pressed', 'true');
    fireEvent.click(screen.getByRole('button', { name: '1M' }));
    expect(screen.getByRole('button', { name: '1M' })).toHaveAttribute('aria-pressed', 'true');
    const obfr = screen.getByRole('button', { name: 'OBFR 疊加序列' });
    fireEvent.click(obfr);
    expect(obfr).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('link', { name: /下載 JSON/ })).toHaveAttribute('download', 'snapshot.json');
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
