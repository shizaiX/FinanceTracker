import { useMemo, useState } from 'react';
import { CalendarClock, Eye, EyeOff, PiggyBank, Settings as Cog, TrendingDown, TrendingUp, Wallet } from 'lucide-react';
import { useStore } from '../store';
import type { Goal, Transaction } from '../types';
import {
  addMonths, currentMonth, daysInMonth, goalSaved, monthLabel, occurrencesInMonth, parseISO, summarize, todayISO,
} from '../utils';
import { Avatar, Bar, Empty, Ring } from '../components/ui';
import { TxRow } from '../components/TxRow';
import { DepositForm, TransactionForm } from '../components/forms';
import type { Tab } from '../App';

export default function Dashboard({ go }: { go: (t: Tab) => void }) {
  const { data, update, money, cat } = useStore();
  const [editTx, setEditTx] = useState<Transaction | null>(null);
  const [depositGoal, setDepositGoal] = useState<Goal | null>(null);

  const month = currentMonth();
  const today = todayISO();
  const s = useMemo(() => summarize(data, month), [data, month]);

  const dayOfMonth = new Date().getDate();
  const daysLeft = daysInMonth(month) - dayOfMonth + 1;

  // Noch ausstehende Fixposten in diesem Monat
  const upcoming = useMemo(() => {
    const list: { id: string; name: string; date: string; amount: number; type: 'income' | 'expense'; categoryId: string }[] = [];
    for (const r of data.recurring) {
      for (const d of [...occurrencesInMonth(r, month), ...occurrencesInMonth(r, addMonths(month, 1))]) {
        if (d >= today) list.push({ id: r.id + d, name: r.name, date: d, amount: r.amount, type: r.type, categoryId: r.categoryId });
      }
    }
    return list.sort((a, b) => a.date.localeCompare(b.date)).slice(0, 4);
  }, [data.recurring, month, today]);

  // Bereits angefallene Fixposten zählen; noch ausstehende Ausgaben werden reserviert
  const pendingFixedExpense = data.recurring
    .filter((r) => r.type === 'expense')
    .flatMap((r) => occurrencesInMonth(r, month).filter((d) => d > today).map(() => r.amount))
    .reduce((a, b) => a + b, 0);
  const perDay = s.balance / daysLeft;

  const spentToday = data.transactions.filter((t) => t.date === today && t.type === 'expense').reduce((a, t) => a + t.amount, 0);
  const savingsRate = s.income > 0 ? (s.saved + Math.max(0, s.balance)) / s.income : 0;

  // Vergleich variable Ausgaben bis zum gleichen Tag im Vormonat
  const prevMonth = addMonths(month, -1);
  const prevSamePoint = data.transactions
    .filter((t) => t.type === 'expense' && t.date.startsWith(prevMonth) && parseISO(t.date).getDate() <= dayOfMonth)
    .reduce((a, t) => a + t.amount, 0);
  const diffPct = prevSamePoint > 0 ? (s.varExpense - prevSamePoint) / prevSamePoint : null;

  const recent = [...data.transactions].sort((a, b) => b.date.localeCompare(a.date)).slice(0, 5);
  const budgets = data.budgets
    .map((b) => ({ ...b, spent: s.byCategory[b.categoryId] ?? 0 }))
    .sort((a, b) => b.spent / b.limit - a.spent / a.limit)
    .slice(0, 3);
  const hidden = data.settings.hideAmounts;
  const isEmpty = !data.transactions.length && !data.recurring.length;

  return (
    <div className="page">
      <div className="topbar">
        <div>
          <div className="sub">{monthLabel(month)}</div>
          <h1>Übersicht</h1>
        </div>
        <div className="row" style={{ gap: 8 }}>
          <button className="icon-btn" aria-label="Beträge verbergen" onClick={() => update((d) => ({ ...d, settings: { ...d.settings, hideAmounts: !hidden } }))}>
            {hidden ? <EyeOff size={18} /> : <Eye size={18} />}
          </button>
          <button className="icon-btn" aria-label="Einstellungen" onClick={() => go('settings')}>
            <Cog size={18} />
          </button>
        </div>
      </div>

      <div className="hero">
        <div className="label">Noch verfügbar diesen Monat</div>
        <div className="big num">{money(s.balance)}</div>
        <div className="hero-stats">
          <div>
            <div className="k">Einnahmen</div>
            <div className="v num">{money(s.income, { compact: s.income >= 1e5 })}</div>
          </div>
          <div>
            <div className="k">Ausgaben</div>
            <div className="v num">{money(s.expense, { compact: s.expense >= 1e5 })}</div>
          </div>
          <div>
            <div className="k">Gespart</div>
            <div className="v num">{money(s.saved, { compact: s.saved >= 1e5 })}</div>
          </div>
        </div>
      </div>

      {isEmpty ? (
        <div className="card" style={{ marginTop: 16 }}>
          <Empty
            icon="👋"
            text="Willkommen! Lege zuerst deine fixen Einnahmen (z. B. Gehalt) und Fixkosten (z. B. Miete) an – danach siehst du hier, was dir jeden Monat bleibt."
            action={<button className="btn primary" onClick={() => go('plan')}>Fixposten anlegen</button>}
          />
        </div>
      ) : (
        <>
          <div className="tiles" style={{ marginTop: 14 }}>
            <div className="tile">
              <div className="k"><Wallet size={14} /> Pro Tag</div>
              <div className={`v num ${perDay < 0 ? 'neg' : ''}`}>{money(perDay)}</div>
              <div className="h">noch {daysLeft} {daysLeft === 1 ? 'Tag' : 'Tage'}</div>
            </div>
            <div className="tile">
              <div className="k"><TrendingDown size={14} /> Heute ausgegeben</div>
              <div className="v num">{money(spentToday)}</div>
              <div className="h">{perDay > 0 ? `${Math.round((spentToday / perDay) * 100)} % vom Tagesbudget` : '—'}</div>
            </div>
            <div className="tile">
              <div className="k"><PiggyBank size={14} /> Sparquote</div>
              <div className="v num">{s.income > 0 ? `${Math.round(savingsRate * 100)} %` : '—'}</div>
              <div className="h">inkl. Rest dieses Monats</div>
            </div>
            <div className="tile">
              <div className="k"><CalendarClock size={14} /> Noch fällig</div>
              <div className="v num">{money(pendingFixedExpense)}</div>
              <div className="h">Fixkosten bis Monatsende</div>
            </div>
          </div>

          {diffPct !== null && Math.abs(diffPct) >= 0.01 && !hidden && (
            <div className="card insight" style={{ marginTop: 10 }}>
              <div className="ic" style={{ background: diffPct > 0 ? 'var(--red-soft)' : 'var(--green-soft)', color: diffPct > 0 ? 'var(--red)' : 'var(--green)' }}>
                {diffPct > 0 ? <TrendingUp size={18} /> : <TrendingDown size={18} />}
              </div>
              <div className="small">
                <b>{Math.abs(Math.round(diffPct * 100))} % {diffPct > 0 ? 'mehr' : 'weniger'}</b> variable Ausgaben als bis zum {dayOfMonth}. im Vormonat
                <span className="faint"> ({money(prevSamePoint)} → {money(s.varExpense)})</span>
              </div>
            </div>
          )}
        </>
      )}

      {budgets.length > 0 && (
        <>
          <div className="section-title">
            <h2>Budgets</h2>
            <button className="link" onClick={() => go('plan')}>Alle</button>
          </div>
          <div className="card stack">
            {budgets.map((b) => {
              const c = cat(b.categoryId);
              const ratio = b.spent / b.limit;
              return (
                <div key={b.categoryId}>
                  <div className="between small" style={{ marginBottom: 6 }}>
                    <span>{c.emoji} {c.name}</span>
                    <span className="num">
                      <b className={ratio > 1 ? 'neg' : ''}>{money(b.spent)}</b> <span className="faint">/ {money(b.limit)}</span>
                    </span>
                  </div>
                  <Bar value={b.spent} max={b.limit} color={ratio > 1 ? 'var(--red)' : ratio > 0.8 ? 'var(--orange)' : c.color} />
                </div>
              );
            })}
          </div>
        </>
      )}

      {upcoming.length > 0 && (
        <>
          <div className="section-title">
            <h2>Demnächst fällig</h2>
            <button className="link" onClick={() => go('plan')}>Fixposten</button>
          </div>
          <div className="card flush">
            {upcoming.map((u) => (
              <div key={u.id} className="list-item">
                <Avatar cat={cat(u.categoryId)} size={38} />
                <div className="grow">
                  <div className="li-title ellipsis">{u.name}</div>
                  <div className="li-sub">{u.date === today ? 'Heute' : parseISO(u.date).toLocaleDateString('de-DE', { weekday: 'short', day: 'numeric', month: 'short' })}</div>
                </div>
                <div className={`li-amt num ${u.type === 'income' ? 'pos' : ''}`}>{u.type === 'income' ? '+' : '−'}{money(u.amount)}</div>
              </div>
            ))}
          </div>
        </>
      )}

      {data.goals.length > 0 && (
        <>
          <div className="section-title">
            <h2>Sparziele</h2>
            <button className="link" onClick={() => go('plan')}>Alle</button>
          </div>
          <div className="chips" style={{ gap: 10 }}>
            {data.goals.slice(0, 6).map((g) => {
              const saved = goalSaved(g);
              return (
                <button key={g.id} className="card" style={{ minWidth: 150, textAlign: 'left', padding: 14 }} onClick={() => setDepositGoal(g)}>
                  <Ring pct={saved / g.target} color={g.color} size={52} label={<span style={{ fontSize: 20 }}>{g.emoji}</span>} />
                  <div className="li-title ellipsis" style={{ marginTop: 8 }}>{g.name}</div>
                  <div className="small faint num">{money(saved)} / {money(g.target, { compact: true })}</div>
                </button>
              );
            })}
          </div>
        </>
      )}

      <div className="section-title">
        <h2>Letzte Buchungen</h2>
        {recent.length > 0 && <button className="link" onClick={() => go('tx')}>Alle</button>}
      </div>
      <div className="card flush">
        {recent.length ? (
          recent.map((t) => (
            <TxRow key={t.id} tx={t} onClick={() => setEditTx(t)} showDate={t.date === today ? 'Heute' : parseISO(t.date).toLocaleDateString('de-DE', { day: 'numeric', month: 'short' })} />
          ))
        ) : (
          <Empty icon="🧾" text="Noch keine Buchungen. Tippe auf + um deine erste Ausgabe zu erfassen." />
        )}
      </div>

      {editTx && <TransactionForm initial={editTx} onClose={() => setEditTx(null)} />}
      {depositGoal && <DepositForm goal={depositGoal} onClose={() => setDepositGoal(null)} />}
    </div>
  );
}
