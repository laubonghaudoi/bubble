import { useEffect, useMemo, useState } from 'react';
import { Dashboard, StateScreen } from './components/DashboardPanels';
import {
  DEFAULT_OVERLAY,
  loadDashboardCore,
  loadRouteSeries,
  LIQUIDITY_MAIN_TABS,
  OVERVIEW_MAIN_TABS,
  parseRouteTarget,
  routeMetricIds,
  snapshotSeriesFallback,
  type DashboardCore,
  type RangeKey,
  type RouteId,
  type RouteTarget,
  type SeriesMap,
} from './dashboard';

const baseUrl = import.meta.env.BASE_URL;

function currentRoute(): RouteTarget {
  return parseRouteTarget(window.location.hash);
}

export default function App() {
  const [core, setCore] = useState<DashboardCore | null>(null);
  const [error, setError] = useState('');
  const [initialRoute] = useState<RouteTarget>(() => currentRoute());
  const [route, setRoute] = useState<RouteId>(initialRoute.route);
  const [section, setSection] = useState<string | null>(initialRoute.section);
  const [series, setSeries] = useState<SeriesMap>({});
  const [seriesErrors, setSeriesErrors] = useState<Record<string, string>>({});
  const [seriesLoading, setSeriesLoading] = useState(true);
  const [main, setMain] = useState('sofr_iorb_spread_bp');
  const [range, setRange] = useState<RangeKey>('3M');
  const [overlay, setOverlay] = useState<Record<string, boolean>>({ ...DEFAULT_OVERLAY });
  const [drawer, setDrawer] = useState<'sources' | string | null>(null);

  useEffect(() => {
    document.documentElement.removeAttribute('data-theme');
    document.querySelector<HTMLMetaElement>('meta[name="theme-color"]')?.setAttribute('content', '#000000');
    try { window.localStorage.removeItem('liq-theme'); } catch { /* storage can be unavailable */ }
  }, []);

  useEffect(() => {
    const target = parseRouteTarget(window.location.hash);
    if (!window.location.hash || !target.valid) {
      window.history.replaceState(null, '', `${window.location.pathname}${window.location.search}#/overview`);
    }
    const onHashChange = () => {
      const next = currentRoute();
      setRoute(next.route);
      setSection(next.section);
    };
    window.addEventListener('hashchange', onHashChange);
    return () => window.removeEventListener('hashchange', onHashChange);
  }, []);

  useEffect(() => {
    let live = true;
    loadDashboardCore(baseUrl)
      .then((result) => { if (live) setCore(result); })
      .catch((reason: unknown) => {
        if (live) setError(reason instanceof Error ? reason.message : String(reason));
      });
    return () => { live = false; };
  }, []);

  useEffect(() => {
    if (!core) return;
    let live = true;
    const ids = routeMetricIds(route, core.catalog, core.snapshot);
    setSeries(Object.fromEntries(ids.map((id) => [id, snapshotSeriesFallback(core.snapshot, id)])));
    setSeriesErrors({});
    setSeriesLoading(true);
    loadRouteSeries(baseUrl, route, core.snapshot, core.catalog)
      .then((result) => {
        if (!live) return;
        setSeries(result.series);
        setSeriesErrors(result.errors);
        setSeriesLoading(false);
      });
    return () => { live = false; };
  }, [core, route]);

  useEffect(() => {
    if (!core) return;
    const allowed: readonly string[] = route === 'overview' ? OVERVIEW_MAIN_TABS.map(({ id }) => id)
      : route === 'liquidity-fuel' ? LIQUIDITY_MAIN_TABS.map(({ id }) => id) : [];
    if (allowed.length && !allowed.includes(main)) setMain('sofr_iorb_spread_bp');
  }, [core, main, route]);

  useEffect(() => {
    if (!core) return;
    const frame = window.requestAnimationFrame(() => {
      if (section) {
        const target = document.getElementById(section);
        target?.scrollIntoView?.({ block: 'start' });
        target?.focus({ preventScroll: true });
        return;
      }
      document.querySelector<HTMLElement>('[data-route-heading]')?.focus();
    });
    return () => window.cancelAnimationFrame(frame);
  }, [core, route, section]);

  const availableMain = useMemo(() => main in (core?.snapshot.metrics ?? {}) ? main : 'sofr_iorb_spread_bp', [core, main]);

  if (error) return <StateScreen error={error} />;
  if (!core) return <StateScreen />;

  return (
    <Dashboard
      snapshot={core.snapshot}
      catalog={core.catalog}
      catalogError={core.catalogError ?? ''}
      series={series}
      seriesErrors={seriesErrors}
      seriesLoading={seriesLoading}
      route={route}
      main={availableMain}
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
