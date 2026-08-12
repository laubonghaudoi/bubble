import { useEffect, useState } from 'react';
import { Dashboard, StateScreen } from './components/DashboardPanels';
import {
  DEFAULT_OVERLAY,
  loadDashboardData,
  type DashboardData,
  type RangeKey,
  type Theme,
} from './dashboard';

const baseUrl = import.meta.env.BASE_URL;

function initialTheme(): Theme {
  if (typeof window === 'undefined') return 'light';
  try {
    const stored = window.localStorage.getItem('liq-theme');
    return stored === 'dark' || stored === 'light' ? stored : 'light';
  } catch {
    return 'light';
  }
}

const seededTheme = initialTheme();
if (typeof document !== 'undefined') document.documentElement.dataset.theme = seededTheme;

export default function App() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [error, setError] = useState('');
  const [theme, setTheme] = useState<Theme>(seededTheme);
  const [main, setMain] = useState('sofr_iorb_spread');
  const [range, setRange] = useState<RangeKey>('3M');
  const [overlay, setOverlay] = useState<Record<string, boolean>>({ ...DEFAULT_OVERLAY });
  const [drawer, setDrawer] = useState<'sources' | string | null>(null);

  useEffect(() => {
    let live = true;
    loadDashboardData(baseUrl)
      .then((result) => { if (live) setData(result); })
      .catch((reason: unknown) => {
        if (live) setError(reason instanceof Error ? reason.message : String(reason));
      });
    return () => { live = false; };
  }, []);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    const meta = document.querySelector<HTMLMetaElement>('meta[name="theme-color"]');
    meta?.setAttribute('content', theme === 'dark' ? '#000000' : '#ffffff');
    try { window.localStorage.setItem('liq-theme', theme); } catch { /* storage can be unavailable */ }
  }, [theme]);

  if (error) return <StateScreen error={error} />;
  if (!data) return <StateScreen />;

  return (
    <Dashboard
      snapshot={data.snapshot}
      catalog={data.catalog}
      catalogError={data.catalogError ?? ''}
      series={data.series}
      theme={theme}
      main={main}
      range={range}
      overlay={overlay}
      drawer={drawer}
      baseUrl={baseUrl}
      onThemeToggle={() => setTheme((current) => {
        const next = current === 'dark' ? 'light' : 'dark';
        document.documentElement.dataset.theme = next;
        return next;
      })}
      onMain={setMain}
      onRange={setRange}
      onOverlay={(id) => setOverlay((current) => ({ ...current, [id]: !current[id] }))}
      onDrawer={setDrawer}
    />
  );
}
