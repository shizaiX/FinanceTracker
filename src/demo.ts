import type { AppData, Transaction } from './types';
import { EMPTY_DATA } from './defaults';
import { addMonths, currentMonth, daysInMonth, pad, todayISO, uid } from './utils';

/** Erzeugt realistische Beispieldaten für die letzten 6 Monate */
export function demoData(): AppData {
  const now = currentMonth();
  const start = `${addMonths(now, -6)}-01`;
  const today = todayISO();
  const rnd = (a: number, b: number) => Math.round((a + Math.random() * (b - a)) * 100) / 100;
  const tx: Transaction[] = [];
  const spend: [string, string[], number, number, number][] = [
    // Kategorie, Notizen, min, max, Anzahl/Monat
    ['food', ['REWE', 'Lidl', 'Aldi', 'Edeka', 'Bäcker'], 6, 75, 10],
    ['eating', ['Pizza', 'Döner', 'Café', 'Sushi', 'Mensa'], 4, 38, 7],
    ['transport', ['Tanken', 'Parken', 'Bahn'], 3, 70, 3],
    ['shopping', ['Amazon', 'Zalando', 'H&M', 'Elektronik'], 12, 120, 2],
    ['leisure', ['Kino', 'Konzert', 'Bar', 'Fitness-Kurs'], 9, 60, 3],
    ['health', ['Apotheke', 'Drogerie'], 4, 30, 2],
  ];
  for (let i = -6; i <= 0; i++) {
    const m = addMonths(now, i);
    const dim = daysInMonth(m);
    for (const [cat, notes, min, max, n] of spend) {
      const count = Math.max(1, Math.round(n * (0.7 + Math.random() * 0.6)));
      for (let k = 0; k < count; k++) {
        const date = `${m}-${pad(1 + Math.floor(Math.random() * dim))}`;
        if (date > today) continue;
        tx.push({ id: uid(), type: 'expense', amount: rnd(min, max), categoryId: cat, note: notes[Math.floor(Math.random() * notes.length)], date });
      }
    }
    if (Math.random() > 0.6) {
      const date = `${m}-${pad(1 + Math.floor(Math.random() * 27))}`;
      if (date <= today) tx.push({ id: uid(), type: 'income', amount: rnd(40, 250), categoryId: 'sidejob', note: 'Nachhilfe', date });
    }
  }
  const dep = (months: number, amount: number) =>
    Array.from({ length: months }, (_, i) => ({ id: uid(), date: `${addMonths(now, i - months + 1)}-01`, amount }));

  return {
    ...EMPTY_DATA,
    transactions: tx,
    recurring: [
      { id: uid(), type: 'income', name: 'Gehalt', amount: 2850, categoryId: 'salary', interval: 'monthly', startDate: start.slice(0, 8) + '28', active: true },
      { id: uid(), type: 'expense', name: 'Miete', amount: 890, categoryId: 'housing', interval: 'monthly', startDate: start.slice(0, 8) + '01', active: true },
      { id: uid(), type: 'expense', name: 'Strom', amount: 68, categoryId: 'utilities', interval: 'monthly', startDate: start.slice(0, 8) + '05', active: true },
      { id: uid(), type: 'expense', name: 'Internet', amount: 39.99, categoryId: 'utilities', interval: 'monthly', startDate: start.slice(0, 8) + '10', active: true },
      { id: uid(), type: 'expense', name: 'Handyvertrag', amount: 19.99, categoryId: 'subscriptions', interval: 'monthly', startDate: start.slice(0, 8) + '15', active: true },
      { id: uid(), type: 'expense', name: 'Netflix', amount: 13.99, categoryId: 'subscriptions', interval: 'monthly', startDate: start.slice(0, 8) + '12', active: true },
      { id: uid(), type: 'expense', name: 'Spotify', amount: 11.99, categoryId: 'subscriptions', interval: 'monthly', startDate: start.slice(0, 8) + '18', active: true },
      { id: uid(), type: 'expense', name: 'Fitnessstudio', amount: 29.9, categoryId: 'leisure', interval: 'monthly', startDate: start.slice(0, 8) + '03', active: true },
      { id: uid(), type: 'expense', name: 'Haftpflicht', amount: 64, categoryId: 'insurance', interval: 'yearly', startDate: `${addMonths(now, -3)}-15`, active: true },
      { id: uid(), type: 'expense', name: 'Deutschlandticket', amount: 58, categoryId: 'transport', interval: 'monthly', startDate: start.slice(0, 8) + '01', active: true },
    ],
    goals: [
      { id: uid(), name: 'Notgroschen', emoji: '🛟', color: '#22c55e', target: 5000, deposits: [{ id: uid(), date: start, amount: 1500 }, ...dep(6, 150)], createdAt: start },
      { id: uid(), name: 'Urlaub Portugal', emoji: '🏖️', color: '#06b6d4', target: 1800, deadline: `${addMonths(now, 7)}-15`, deposits: dep(5, 120), createdAt: start },
      { id: uid(), name: 'Neues Laptop', emoji: '💻', color: '#7c5cff', target: 1400, deposits: dep(3, 80), createdAt: start },
    ],
    budgets: [
      { categoryId: 'food', limit: 350 },
      { categoryId: 'eating', limit: 150 },
      { categoryId: 'shopping', limit: 120 },
    ],
  };
}
