export type TxType = 'income' | 'expense';
export type Interval = 'weekly' | 'monthly' | 'quarterly' | 'halfyearly' | 'yearly';

export interface Category {
  id: string;
  name: string;
  emoji: string;
  color: string;
  type: TxType;
}

/** Einzelne (variable) Buchung, z. B. Einkauf, Restaurant, Bonus */
export interface Transaction {
  id: string;
  type: TxType;
  amount: number;
  categoryId: string;
  note: string;
  date: string; // YYYY-MM-DD
}

/** Fixe Einnahme oder fixe Ausgabe (Gehalt, Miete, Abos …) */
export interface Recurring {
  id: string;
  type: TxType;
  name: string;
  amount: number;
  categoryId: string;
  interval: Interval;
  startDate: string; // YYYY-MM-DD, bestimmt auch den Buchungstag
  endDate?: string;
  active: boolean;
}

export interface Deposit {
  id: string;
  date: string;
  amount: number; // negativ = Entnahme
}

export interface Goal {
  id: string;
  name: string;
  emoji: string;
  color: string;
  target: number;
  deadline?: string;
  deposits: Deposit[];
  createdAt: string;
}

export interface Budget {
  categoryId: string;
  limit: number; // pro Monat
}

export interface Settings {
  currency: string;
  theme: 'system' | 'dark' | 'light';
  hideAmounts: boolean;
}

export interface AppData {
  version: 1;
  transactions: Transaction[];
  recurring: Recurring[];
  goals: Goal[];
  budgets: Budget[];
  categories: Category[];
  settings: Settings;
}
