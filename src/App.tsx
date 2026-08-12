import { useEffect, useState } from 'react';
import { Dashboard, StateScreen } from './components/DashboardPanels';
import {
  DEFAULT_OVERLAY,
  loadDashboardData,
  type DashboardData,
  type RangeKey,
} from './dashboard';

const baseUrl = import.meta.env.BASE_URL;

export default function App() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [error, setError] = useState('');
  const [main, setMain] = useState('sofr_iorb_spread');
  const [range, setRange] = useState<RangeKey>('3M');
  const [overlay, setOverlay] = useState<Record<string, boolean>>({ ...DEFAULT_OVERLAY });
  const [drawer, setDrawer] = useState<'sources' | string | null>(null);

  useEffect(() => {
    document.documentElement.removeAttribute('data-theme');
    document.querySelector<HTMLMetaElement>('meta[name="theme-color"]')?.setAttribute('content', '#000000');
    try { window.localStorage.removeItem('liq-theme'); } catch { /* storage can be unavailable */ }
  }, []);

  useEffect(() => {
    let live = true;
    loadDashboardData(baseUrl)
      .then((result) => { if (live) setData(result); })
      .catch((reason: unknown) => {
        if (live) setError(reason instanceof Error ? reason.message : String(reason));
      });
    return () => { live = false; };
  }, []);

  if (error) return <StateScreen error={error} />;
  if (!data) return <StateScreen />;

  return (
    <Dashboard
      snapshot={data.snapshot}
      catalog={data.catalog}
      catalogError={data.catalogError ?? ''}
      series={data.series}
      main={main}
      range={range}
      overlay={overlay}
      drawer={drawer}
      baseUrl={baseUrl}
      onMain={setMain}
      onRange={setRange}
      onOverlay={(id) => setOverlay((current) => ({ ...current, [id]: !current[id] }))}
      onDrawer={setDrawer}
    />
  );
}
