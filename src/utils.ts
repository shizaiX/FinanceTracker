import type { AppData, Interval, Recurring, TxType } from './types';

export const uid = () =>
  (crypto.randomUUID?.() ?? `${Date.now().toString(36)}${Math.random().toString(36).slice(2)}`);

/* ---------- Datum ---------- */

export const pad = (n: number) => String(n).padStart(2, '0');
export const toISO = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
export const todayISO = () => toISO(new Date());
export const parseISO = (s: string) => {
  const [y, m, d] = s.split('-').map(Number);
  return new Date(y, (m || 1) - 1, d || 1);
};

/** Monatsschlüssel YYYY-MM */
export type MonthKey = string;
export const monthKey = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}`;
export const currentMonth = () => monthKey(new Date());
export const addMonths = (key: MonthKey, n: number): MonthKey => {
  const [y, m] = key.split('-').map(Number);
  return monthKey(new Date(y, m - 1 + n, 1));
};
export const daysInMonth = (key: MonthKey) => {
  const [y, m] = key.split('-').map(Number);
  return new Date(y, m, 0).getDate();
};
export const monthLabel = (key: MonthKey, style: 'long' | 'short' = 'long') => {
  const [y, m] = key.split('-').map(Number);
  const d = new Date(y, m - 1, 1);
  if (style === 'short') return d.toLocaleDateString('de-DE', { month: 'short' }).replace('.', '');
  return d.toLocaleDateString('de-DE', { month: 'long', year: 'numeric' });
};
export const lastMonths = (n: number, end: MonthKey = currentMonth()): MonthKey[] =>
  Array.from({ length: n }, (_, i) => addMonths(end, i - n + 1));

export const dayLabel = (iso: string) => {
  const today = todayISO();
  const y = toISO(new Date(Date.now() - 864e5));
  if (iso === today) return 'Heute';
  if (iso === y) return 'Gestern';
  return parseISO(iso).toLocaleDateString('de-DE', { weekday: 'long', day: 'numeric', month: 'long' });
};
export const shortDate = (iso: string) =>
  parseISO(iso).toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' });

/* ---------- Geld ---------- */

const fmtCache = new Map<string, Intl.NumberFormat>();
export function money(v: number, currency = 'EUR', opts: { compact?: boolean; sign?: boolean } = {}) {
  const key = `${currency}|${opts.compact}|${opts.sign}`;
  let f = fmtCache.get(key);
  if (!f) {
    f = new Intl.NumberFormat('de-DE', {
      style: 'currency',
      currency,
      notation: opts.compact ? 'compact' : 'standard',
      maximumFractionDigits: opts.compact ? 1 : 2,
      minimumFractionDigits: opts.compact ? 0 : 2,
      signDisplay: opts.sign ? 'exceptZero' : 'auto',
    });
    fmtCache.set(key, f);
  }
  return f.format(v);
}

/** "12,50" oder "12.50" -> 12.5 */
export const parseAmount = (s: string) => {
  const clean = s.replace(/\s/g, '').replace(/\.(?=\d{3}(\D|$))/g, '').replace(',', '.');
  const n = parseFloat(clean);
  return Number.isFinite(n) ? Math.round(n * 100) / 100 : NaN;
};

/* ---------- Wiederkehrende Posten ---------- */

export const INTERVALS: { id: Interval; label: string; perYear: number; months: number }[] = [
  { id: 'weekly', label: 'Wöchentlich', perYear: 52, months: 0 },
  { id: 'monthly', label: 'Monatlich', perYear: 12, months: 1 },
  { id: 'quarterly', label: 'Vierteljährlich', perYear: 4, months: 3 },
  { id: 'halfyearly', label: 'Halbjährlich', perYear: 2, months: 6 },
  { id: 'yearly', label: 'Jährlich', perYear: 1, months: 12 },
];
export const intervalLabel = (i: Interval) => INTERVALS.find((x) => x.id === i)?.label ?? i;

/** Durchschnittlicher Monatsbetrag (z. B. Jahres-Abo / 12) */
export const monthlyEquivalent = (r: Recurring) =>
  (r.amount * (INTERVALS.find((x) => x.id === r.interval)?.perYear ?? 12)) / 12;

/** Liefert die Buchungstermine (ISO) eines wiederkehrenden Postens in einem Monat */
export function occurrencesInMonth(r: Recurring, key: MonthKey): string[] {
  if (!r.active) return [];
  const [y, m] = key.split('-').map(Number);
  const start = parseISO(r.startDate);
  const end = r.endDate ? parseISO(r.endDate) : null;
  const first = new Date(y, m - 1, 1);
  const last = new Date(y, m, 0);
  if (start > last || (end && end < first)) return [];

  const inRange = (d: Date) => d >= start && d >= first && d <= last && (!end || d <= end);
  const out: string[] = [];

  if (r.interval === 'weekly') {
    const d = new Date(start);
    if (d < first) {
      const diff = Math.ceil((first.getTime() - d.getTime()) / (7 * 864e5));
      d.setDate(d.getDate() + diff * 7);
    }
    while (d <= last) {
      if (inRange(d)) out.push(toISO(d));
      d.setDate(d.getDate() + 7);
    }
    return out;
  }

  const step = INTERVALS.find((x) => x.id === r.interval)!.months;
  const monthsSinceStart = (y - start.getFullYear()) * 12 + (m - 1 - start.getMonth());
  if (monthsSinceStart < 0 || monthsSinceStart % step !== 0) return [];
  const day = Math.min(start.getDate(), last.getDate());
  const d = new Date(y, m - 1, day);
  if (inRange(d)) out.push(toISO(d));
  return out;
}

/* ---------- Monatsauswertung ---------- */

export interface MonthSummary {
  month: MonthKey;
  fixedIncome: number;
  fixedExpense: number;
  varIncome: number;
  varExpense: number;
  saved: number; // Einzahlungen in Sparziele (netto)
  income: number;
  expense: number;
  balance: number; // Einnahmen - Ausgaben - Sparen
  byCategory: Record<string, number>; // nur Ausgaben (fix + variabel)
  incomeByCategory: Record<string, number>;
}

export function summarize(data: AppData, key: MonthKey): MonthSummary {
  const s: MonthSummary = {
    month: key, fixedIncome: 0, fixedExpense: 0, varIncome: 0, varExpense: 0, saved: 0,
    income: 0, expense: 0, balance: 0, byCategory: {}, incomeByCategory: {},
  };
  const add = (type: TxType, cat: string, amount: number) => {
    const bucket = type === 'expense' ? s.byCategory : s.incomeByCategory;
    bucket[cat] = (bucket[cat] ?? 0) + amount;
  };
  for (const r of data.recurring) {
    const n = occurrencesInMonth(r, key).length;
    if (!n) continue;
    const amt = r.amount * n;
    if (r.type === 'income') s.fixedIncome += amt;
    else s.fixedExpense += amt;
    add(r.type, r.categoryId, amt);
  }
  for (const t of data.transactions) {
    if (!t.date.startsWith(key)) continue;
    if (t.type === 'income') s.varIncome += t.amount;
    else s.varExpense += t.amount;
    add(t.type, t.categoryId, t.amount);
  }
  for (const g of data.goals) for (const d of g.deposits) if (d.date.startsWith(key)) s.saved += d.amount;
  s.income = s.fixedIncome + s.varIncome;
  s.expense = s.fixedExpense + s.varExpense;
  s.balance = s.income - s.expense - s.saved;
  return s;
}

export const goalSaved = (g: { deposits: { amount: number }[] }) =>
  g.deposits.reduce((a, d) => a + d.amount, 0);

/** Anzahl Monate von heute bis Datum (mind. 1) */
export const monthsUntil = (iso: string) => {
  const now = new Date();
  const d = parseISO(iso);
  const m = (d.getFullYear() - now.getFullYear()) * 12 + (d.getMonth() - now.getMonth());
  return Math.max(1, m + (d.getDate() >= now.getDate() ? 1 : 0));
};

export const clamp = (v: number, a: number, b: number) => Math.min(b, Math.max(a, v));

export function downloadFile(name: string, content: string, type: string) {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
