import { lazy, Suspense, useEffect, useState } from 'react';
import { BarChart3, CalendarRange, Home, Plus, ReceiptText } from 'lucide-react';
import { useStore } from './store';
import Dashboard from './pages/Dashboard';
import Transactions from './pages/Transactions';
import Plan, { type PlanTab } from './pages/Plan';
import Settings from './pages/Settings';
import { TransactionForm } from './components/forms';
import { Toast } from './components/ui';

const Stats = lazy(() => import('./pages/Stats'));

export type Tab = 'home' | 'tx' | 'stats' | 'plan' | 'settings';

const NAV: { id: Tab; label: string; icon: typeof Home }[] = [
  { id: 'home', label: 'Übersicht', icon: Home },
  { id: 'tx', label: 'Buchungen', icon: ReceiptText },
  { id: 'stats', label: 'Statistik', icon: BarChart3 },
  { id: 'plan', label: 'Planung', icon: CalendarRange },
];

export default function App() {
  const { data } = useStore();
  const [tab, setTab] = useState<Tab>(() => (location.hash.slice(1) as Tab) || 'home');
  const [planTab, setPlanTab] = useState<PlanTab>('fixed');
  const [adding, setAdding] = useState(false);

  // Theme anwenden
  useEffect(() => {
    const apply = () => {
      const t = data.settings.theme;
      const dark = t === 'dark' || (t === 'system' && matchMedia('(prefers-color-scheme: dark)').matches);
      document.documentElement.dataset.theme = dark ? 'dark' : 'light';
      document.querySelector('meta[name="theme-color"]')?.setAttribute('content', dark ? '#0b0d12' : '#f4f5f9');
    };
    apply();
    const mq = matchMedia('(prefers-color-scheme: dark)');
    mq.addEventListener('change', apply);
    return () => mq.removeEventListener('change', apply);
  }, [data.settings.theme]);

  // Tab im Hash merken (Zurück-Taste & Neuladen)
  useEffect(() => {
    if (location.hash.slice(1) !== tab) history.replaceState(null, '', `#${tab}`);
    window.scrollTo({ top: 0 });
  }, [tab]);

  const go = (t: Tab) => setTab(t);

  return (
    <div className="app">
      {tab === 'home' && <Dashboard go={go} />}
      {tab === 'tx' && <Transactions />}
      {tab === 'stats' && <Suspense fallback={<div className="page" />}><Stats /></Suspense>}
      {tab === 'plan' && <Plan tab={planTab} setTab={setPlanTab} />}
      {tab === 'settings' && <Settings back={() => setTab('home')} />}

      <nav className="nav">
        <div className="nav-inner">
          {NAV.slice(0, 2).map((n) => <NavBtn key={n.id} {...n} on={tab === n.id} onClick={() => go(n.id)} />)}
          <button className="fab" aria-label="Neue Buchung" onClick={() => setAdding(true)}>
            <Plus size={28} strokeWidth={2.5} />
          </button>
          {NAV.slice(2).map((n) => <NavBtn key={n.id} {...n} on={tab === n.id} onClick={() => go(n.id)} />)}
        </div>
      </nav>

      {adding && <TransactionForm onClose={() => setAdding(false)} />}
      <Toast />
    </div>
  );
}

function NavBtn({ label, icon: Icon, on, onClick }: { label: string; icon: typeof Home; on: boolean; onClick: () => void }) {
  return (
    <button className={`nav-btn ${on ? 'on' : ''}`} onClick={onClick} aria-current={on ? 'page' : undefined}>
      <Icon size={22} strokeWidth={on ? 2.4 : 2} />
      {label}
    </button>
  );
}
