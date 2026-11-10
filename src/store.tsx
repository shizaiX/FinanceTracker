import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import type { AppData, Category } from './types';
import { EMPTY_DATA } from './defaults';
import { money as fmtMoney } from './utils';

const KEY = 'finanzen.data.v1';

function load(): AppData {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return EMPTY_DATA;
    return normalize(JSON.parse(raw));
  } catch {
    return EMPTY_DATA;
  }
}

/** Füllt fehlende Felder auf, damit auch ältere/importierte Daten funktionieren */
export function normalize(input: Partial<AppData>): AppData {
  if (!input || typeof input !== 'object') throw new Error('Ungültige Daten');
  return {
    version: 1,
    transactions: Array.isArray(input.transactions) ? input.transactions : [],
    recurring: Array.isArray(input.recurring) ? input.recurring : [],
    goals: Array.isArray(input.goals) ? input.goals.map((g) => ({ ...g, deposits: g.deposits ?? [] })) : [],
    budgets: Array.isArray(input.budgets) ? input.budgets : [],
    categories: Array.isArray(input.categories) && input.categories.length ? input.categories : EMPTY_DATA.categories,
    settings: { ...EMPTY_DATA.settings, ...(input.settings ?? {}) },
  };
}

interface Toast {
  id: number;
  text: string;
  undo?: () => void;
}

interface Store {
  data: AppData;
  update: (fn: (d: AppData) => AppData) => void;
  replace: (d: AppData) => void;
  /** Ändern mit Rückgängig-Option im Toast */
  updateWithUndo: (text: string, fn: (d: AppData) => AppData) => void;
  toast: Toast | null;
  showToast: (text: string) => void;
  dismissToast: () => void;
  cat: (id: string) => Category;
  money: (v: number, opts?: { compact?: boolean; sign?: boolean }) => string;
}

const Ctx = createContext<Store | null>(null);

const FALLBACK_CAT: Category = { id: '?', name: 'Unbekannt', emoji: '❔', color: '#64748b', type: 'expense' };

export function StoreProvider({ children }: { children: ReactNode }) {
  const [data, setData] = useState<AppData>(load);
  const [toast, setToast] = useState<Toast | null>(null);
  const timer = useRef<number | undefined>(undefined);

  useEffect(() => {
    try {
      localStorage.setItem(KEY, JSON.stringify(data));
    } catch {
      /* Speicher voll / privat-Modus */
    }
  }, [data]);

  // Sync zwischen mehreren Tabs
  useEffect(() => {
    const onStorage = (e: StorageEvent) => {
      if (e.key === KEY && e.newValue) {
        try {
          setData(normalize(JSON.parse(e.newValue)));
        } catch {
          /* ignore */
        }
      }
    };
    window.addEventListener('storage', onStorage);
    return () => window.removeEventListener('storage', onStorage);
  }, []);

  const pushToast = useCallback((t: Omit<Toast, 'id'>) => {
    window.clearTimeout(timer.current);
    setToast({ ...t, id: Date.now() });
    timer.current = window.setTimeout(() => setToast(null), t.undo ? 5000 : 2500);
  }, []);

  const update = useCallback((fn: (d: AppData) => AppData) => setData((d) => fn(d)), []);

  const updateWithUndo = useCallback(
    (text: string, fn: (d: AppData) => AppData) => {
      setData((prev) => {
        const next = fn(prev);
        pushToast({ text, undo: () => setData(prev) });
        return next;
      });
    },
    [pushToast]
  );

  const catMap = useMemo(() => new Map(data.categories.map((c) => [c.id, c])), [data.categories]);
  const cat = useCallback((id: string) => catMap.get(id) ?? FALLBACK_CAT, [catMap]);

  const { currency, hideAmounts } = data.settings;
  const money = useCallback(
    (v: number, opts?: { compact?: boolean; sign?: boolean }) =>
      hideAmounts ? '•••••' : fmtMoney(v, currency, opts),
    [currency, hideAmounts]
  );

  const value: Store = {
    data,
    update,
    replace: setData,
    updateWithUndo,
    toast,
    showToast: (text) => pushToast({ text }),
    dismissToast: () => setToast(null),
    cat,
    money,
  };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useStore() {
  const s = useContext(Ctx);
  if (!s) throw new Error('StoreProvider fehlt');
  return s;
}
