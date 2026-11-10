import type { AppData, Category } from './types';

export const PALETTE = [
  '#7c5cff', '#22c55e', '#f97316', '#06b6d4', '#ec4899', '#eab308',
  '#3b82f6', '#ef4444', '#14b8a6', '#a855f7', '#84cc16', '#f43f5e',
];

export const DEFAULT_CATEGORIES: Category[] = [
  // Ausgaben
  { id: 'food', name: 'Lebensmittel', emoji: '🛒', color: '#22c55e', type: 'expense' },
  { id: 'eating', name: 'Essen & Trinken', emoji: '🍔', color: '#f97316', type: 'expense' },
  { id: 'transport', name: 'Mobilität', emoji: '🚗', color: '#3b82f6', type: 'expense' },
  { id: 'housing', name: 'Wohnen', emoji: '🏠', color: '#7c5cff', type: 'expense' },
  { id: 'utilities', name: 'Nebenkosten', emoji: '💡', color: '#eab308', type: 'expense' },
  { id: 'subscriptions', name: 'Abos', emoji: '📺', color: '#ec4899', type: 'expense' },
  { id: 'insurance', name: 'Versicherung', emoji: '🛡️', color: '#14b8a6', type: 'expense' },
  { id: 'shopping', name: 'Shopping', emoji: '🛍️', color: '#a855f7', type: 'expense' },
  { id: 'health', name: 'Gesundheit', emoji: '💊', color: '#ef4444', type: 'expense' },
  { id: 'leisure', name: 'Freizeit', emoji: '🎉', color: '#06b6d4', type: 'expense' },
  { id: 'travel', name: 'Reisen', emoji: '✈️', color: '#84cc16', type: 'expense' },
  { id: 'education', name: 'Bildung', emoji: '📚', color: '#f43f5e', type: 'expense' },
  { id: 'other-exp', name: 'Sonstiges', emoji: '📦', color: '#64748b', type: 'expense' },
  // Einnahmen
  { id: 'salary', name: 'Gehalt', emoji: '💼', color: '#22c55e', type: 'income' },
  { id: 'sidejob', name: 'Nebenjob', emoji: '🧰', color: '#06b6d4', type: 'income' },
  { id: 'gifts', name: 'Geschenke', emoji: '🎁', color: '#ec4899', type: 'income' },
  { id: 'refund', name: 'Erstattung', emoji: '↩️', color: '#eab308', type: 'income' },
  { id: 'invest', name: 'Kapitalerträge', emoji: '📈', color: '#7c5cff', type: 'income' },
  { id: 'other-inc', name: 'Sonstiges', emoji: '💰', color: '#64748b', type: 'income' },
];

export const EMPTY_DATA: AppData = {
  version: 1,
  transactions: [],
  recurring: [],
  goals: [],
  budgets: [],
  categories: DEFAULT_CATEGORIES,
  settings: { currency: 'EUR', theme: 'system', hideAmounts: false },
};
