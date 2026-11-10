import { useState } from 'react';
import { Pencil, Plus, Trash2 } from 'lucide-react';
import { useStore } from '../store';
import type { Budget, Goal, Recurring, TxType } from '../types';
import {
  currentMonth, daysInMonth, goalSaved, intervalLabel, monthlyEquivalent, monthsUntil, parseISO, shortDate, summarize,
} from '../utils';
import { Bar, Empty, Ring, Seg, Sheet } from '../components/ui';
import { FixedRow } from '../components/TxRow';
import { BudgetForm, DepositForm, GoalForm, RecurringForm } from '../components/forms';

export type PlanTab = 'fixed' | 'goals' | 'budgets';

export default function Plan({ tab, setTab }: { tab: PlanTab; setTab: (t: PlanTab) => void }) {
  return (
    <div className="page">
      <div className="topbar">
        <h1>Planung</h1>
      </div>
      <Seg
        options={[{ id: 'fixed', label: 'Fixposten' }, { id: 'goals', label: 'Sparziele' }, { id: 'budgets', label: 'Budgets' }]}
        value={tab}
        onChange={setTab}
      />
      {tab === 'fixed' && <Fixed />}
      {tab === 'goals' && <Goals />}
      {tab === 'budgets' && <Budgets />}
    </div>
  );
}

/* ---------------- Fixposten ---------------- */

function Fixed() {
  const { data, money } = useStore();
  const [form, setForm] = useState<{ initial?: Recurring; type: TxType } | null>(null);

  const active = data.recurring.filter((r) => r.active);
  const inc = active.filter((r) => r.type === 'income').reduce((a, r) => a + monthlyEquivalent(r), 0);
  const exp = active.filter((r) => r.type === 'expense').reduce((a, r) => a + monthlyEquivalent(r), 0);
  const free = inc - exp;
  const sorted = (type: TxType) =>
    data.recurring.filter((r) => r.type === type).sort((a, b) => Number(b.active) - Number(a.active) || monthlyEquivalent(b) - monthlyEquivalent(a));

  const sub = (r: Recurring) => {
    const day = parseISO(r.startDate).getDate();
    const when = r.interval === 'weekly'
      ? parseISO(r.startDate).toLocaleDateString('de-DE', { weekday: 'long' })
      : `am ${day}.`;
    const eq = r.interval !== 'monthly' ? ` · ≈ ${money(monthlyEquivalent(r))}/Mon.` : '';
    return `${intervalLabel(r.interval)} ${when}${eq}${r.active ? '' : ' · pausiert'}${r.endDate ? ` · bis ${shortDate(r.endDate)}` : ''}`;
  };

  return (
    <>
      <div className="card" style={{ marginTop: 14 }}>
        <div className="small muted">Bleibt monatlich nach Fixkosten</div>
        <div className={`num ${free < 0 ? 'neg' : ''}`} style={{ fontSize: 30, fontWeight: 760, letterSpacing: '-0.02em', margin: '2px 0 12px' }}>
          {money(free)}
        </div>
        <div className="bar" style={{ height: 10 }}>
          <i style={{ width: `${inc > 0 ? Math.min(100, (exp / inc) * 100) : exp > 0 ? 100 : 0}%`, background: exp > inc ? 'var(--red)' : 'var(--accent)' }} />
        </div>
        <div className="between small" style={{ marginTop: 8 }}>
          <span className="pos num">+{money(inc)} Einnahmen</span>
          <span className="muted num">−{money(exp)} Fixkosten</span>
        </div>
        {inc > 0 && <div className="tiny faint" style={{ marginTop: 6 }}>{Math.round((exp / inc) * 100)} % deines fixen Einkommens sind verplant · Jahreskosten: {money(exp * 12)}</div>}
      </div>

      {(['income', 'expense'] as TxType[]).map((type) => (
        <div key={type}>
          <div className="section-title">
            <h2>{type === 'income' ? 'Fixe Einnahmen' : 'Fixe Ausgaben'}</h2>
            <button className="link row" style={{ gap: 4 }} onClick={() => setForm({ type })}>
              <Plus size={16} /> Hinzufügen
            </button>
          </div>
          <div className="card flush">
            {sorted(type).length ? (
              sorted(type).map((r) => (
                <FixedRow key={r.id} name={r.name} amount={r.amount} type={r.type} categoryId={r.categoryId} sub={sub(r)} muted={!r.active} onClick={() => setForm({ initial: r, type })} />
              ))
            ) : (
              <Empty
                icon={type === 'income' ? '💼' : '🏠'}
                text={type === 'income' ? 'Gehalt, Kindergeld, Mieteinnahmen …' : 'Miete, Strom, Handy, Versicherungen, Abos …'}
              />
            )}
          </div>
        </div>
      ))}

      {form && <RecurringForm initial={form.initial} defaultType={form.type} onClose={() => setForm(null)} />}
    </>
  );
}

/* ---------------- Sparziele ---------------- */

function Goals() {
  const { data, money } = useStore();
  const [form, setForm] = useState<{ initial?: Goal } | null>(null);
  const [detail, setDetail] = useState<string | null>(null);
  const [deposit, setDeposit] = useState<Goal | null>(null);

  const total = data.goals.reduce((a, g) => a + goalSaved(g), 0);
  const target = data.goals.reduce((a, g) => a + g.target, 0);
  const monthlyNeed = data.goals.reduce((a, g) => {
    const rest = g.target - goalSaved(g);
    return g.deadline && rest > 0 ? a + rest / monthsUntil(g.deadline) : a;
  }, 0);
  const detailGoal = data.goals.find((g) => g.id === detail);

  return (
    <>
      <div className="card" style={{ marginTop: 14 }}>
        <div className="between">
          <div>
            <div className="small muted">Insgesamt gespart</div>
            <div className="num" style={{ fontSize: 30, fontWeight: 760, letterSpacing: '-0.02em' }}>{money(total)}</div>
            <div className="small faint num">von {money(target)}</div>
          </div>
          <Ring pct={target ? total / target : 0} color="var(--accent)" size={72} />
        </div>
        {monthlyNeed > 0 && (
          <div className="small muted" style={{ marginTop: 10 }}>
            Für alle Zieltermine brauchst du ca. <b className="num" style={{ color: 'var(--text)' }}>{money(monthlyNeed)}</b> pro Monat.
          </div>
        )}
      </div>

      <div className="section-title">
        <h2>Deine Ziele</h2>
        <button className="link row" style={{ gap: 4 }} onClick={() => setForm({})}>
          <Plus size={16} /> Neues Ziel
        </button>
      </div>

      {data.goals.length === 0 ? (
        <div className="card">
          <Empty icon="🎯" text="Spare gezielt auf Urlaub, Auto oder einen Notgroschen." action={<button className="btn primary" onClick={() => setForm({})}>Sparziel erstellen</button>} />
        </div>
      ) : (
        <div className="stack">
          {data.goals.map((g) => {
            const saved = goalSaved(g);
            const rest = Math.max(0, g.target - saved);
            const done = saved >= g.target;
            return (
              <button key={g.id} className="card goal-card" style={{ textAlign: 'left' }} onClick={() => setDetail(g.id)}>
                <Ring pct={saved / g.target} color={g.color} label={<span style={{ fontSize: 24 }}>{g.emoji}</span>} />
                <div className="grow">
                  <div className="between">
                    <div className="li-title ellipsis">{g.name}</div>
                    {done ? <span className="badge good">Erreicht 🎉</span> : <span className="badge">{Math.round((saved / g.target) * 100)} %</span>}
                  </div>
                  <div className="num" style={{ margin: '4px 0 2px' }}>
                    <b>{money(saved)}</b> <span className="faint small">/ {money(g.target)}</span>
                  </div>
                  <div className="tiny faint">
                    {done ? 'Glückwunsch!' : g.deadline
                      ? `${money(rest / monthsUntil(g.deadline))}/Monat bis ${shortDate(g.deadline)}`
                      : `Noch ${money(rest)}`}
                  </div>
                </div>
              </button>
            );
          })}
        </div>
      )}

      {detailGoal && !deposit && !form && (
        <GoalDetail goal={detailGoal} onClose={() => setDetail(null)} onDeposit={() => setDeposit(detailGoal)} onEdit={() => setForm({ initial: detailGoal })} />
      )}
      {deposit && <DepositForm goal={deposit} onClose={() => setDeposit(null)} />}
      {form && (
        <GoalForm
          initial={form.initial}
          onClose={() => {
            setForm(null);
            if (form.initial && !data.goals.some((g) => g.id === form.initial!.id)) setDetail(null);
          }}
        />
      )}
    </>
  );
}

function GoalDetail({ goal, onClose, onDeposit, onEdit }: { goal: Goal; onClose: () => void; onDeposit: () => void; onEdit: () => void }) {
  const { money, updateWithUndo } = useStore();
  const saved = goalSaved(goal);
  const rest = Math.max(0, goal.target - saved);
  const deps = [...goal.deposits].sort((a, b) => b.date.localeCompare(a.date));
  // Durchschnittliche Sparrate der letzten Monate -> Prognose
  const months = new Set(goal.deposits.map((d) => d.date.slice(0, 7))).size || 1;
  const avg = saved / months;
  const eta = rest > 0 && avg > 0 ? Math.ceil(rest / avg) : null;

  return (
    <Sheet title={`${goal.emoji} ${goal.name}`} onClose={onClose}>
      <div className="stack">
        <div className="row" style={{ gap: 16 }}>
          <Ring pct={saved / goal.target} color={goal.color} size={92} />
          <div>
            <div className="num" style={{ fontSize: 26, fontWeight: 760 }}>{money(saved)}</div>
            <div className="faint small num">von {money(goal.target)} · noch {money(rest)}</div>
            {goal.deadline && rest > 0 && (
              <div className="small" style={{ marginTop: 4 }}>
                <b className="num">{money(rest / monthsUntil(goal.deadline))}</b> <span className="muted">/ Monat bis {shortDate(goal.deadline)}</span>
              </div>
            )}
            {eta && <div className="tiny faint">Bei Ø {money(avg)}/Monat erreicht in ca. {eta} {eta === 1 ? 'Monat' : 'Monaten'}</div>}
          </div>
        </div>
        <div className="two">
          <button className="btn primary" onClick={onDeposit}><Plus size={18} /> Einzahlen</button>
          <button className="btn" onClick={onEdit}><Pencil size={16} /> Bearbeiten</button>
        </div>
        <div>
          <div className="small muted" style={{ fontWeight: 600, margin: '6px 2px 8px' }}>Verlauf</div>
          <div className="card flush">
            {deps.length ? deps.map((d) => (
              <div key={d.id} className="list-item">
                <div className="grow">
                  <div className="li-title">{d.amount >= 0 ? 'Einzahlung' : 'Entnahme'}</div>
                  <div className="li-sub">{shortDate(d.date)}</div>
                </div>
                <div className={`li-amt num ${d.amount >= 0 ? 'pos' : 'neg'}`}>{money(d.amount, { sign: true })}</div>
                <button
                  className="icon-btn" style={{ width: 34, height: 34 }} aria-label="Eintrag löschen"
                  onClick={() => updateWithUndo('Eintrag gelöscht', (data) => ({
                    ...data,
                    goals: data.goals.map((g) => (g.id === goal.id ? { ...g, deposits: g.deposits.filter((x) => x.id !== d.id) } : g)),
                  }))}
                >
                  <Trash2 size={15} />
                </button>
              </div>
            )) : <Empty icon="🪙" text="Noch keine Einzahlungen." />}
          </div>
        </div>
      </div>
    </Sheet>
  );
}

/* ---------------- Budgets ---------------- */

function Budgets() {
  const { data, money, cat } = useStore();
  const [form, setForm] = useState<{ initial?: Budget } | null>(null);
  const month = currentMonth();
  const s = summarize(data, month);
  const progress = new Date().getDate() / daysInMonth(month);
  const totalLimit = data.budgets.reduce((a, b) => a + b.limit, 0);
  const totalSpent = data.budgets.reduce((a, b) => a + (s.byCategory[b.categoryId] ?? 0), 0);

  return (
    <>
      {data.budgets.length > 0 && (
        <div className="card" style={{ marginTop: 14 }}>
          <div className="small muted">Budgets diesen Monat</div>
          <div className="num" style={{ fontSize: 28, fontWeight: 760, margin: '2px 0 10px' }}>
            {money(totalLimit - totalSpent)} <span className="small faint" style={{ fontWeight: 500 }}>übrig</span>
          </div>
          <div style={{ position: 'relative' }}>
            <Bar value={totalSpent} max={totalLimit} color={totalSpent > totalLimit ? 'var(--red)' : 'var(--accent)'} />
            <div title="Heute" style={{ position: 'absolute', top: -3, bottom: -3, width: 2, borderRadius: 2, background: 'var(--text-2)', left: `${progress * 100}%` }} />
          </div>
          <div className="tiny faint" style={{ marginTop: 6 }}>Strich = heutiger Stand im Monat ({Math.round(progress * 100)} %)</div>
        </div>
      )}

      <div className="section-title">
        <h2>Kategorien-Budgets</h2>
        <button className="link row" style={{ gap: 4 }} onClick={() => setForm({})}>
          <Plus size={16} /> Budget
        </button>
      </div>

      {data.budgets.length === 0 ? (
        <div className="card">
          <Empty icon="📊" text="Setze monatliche Limits pro Kategorie, z. B. 300 € für Lebensmittel. Du wirst gewarnt, wenn du sie überschreitest." action={<button className="btn primary" onClick={() => setForm({})}>Budget festlegen</button>} />
        </div>
      ) : (
        <div className="card stack">
          {data.budgets.map((b) => {
            const c = cat(b.categoryId);
            const spent = s.byCategory[b.categoryId] ?? 0;
            const ratio = spent / b.limit;
            const status = ratio > 1 ? ['bad', 'Überschritten'] : ratio > progress + 0.1 ? ['warn', 'Zu schnell'] : ['good', 'Im Plan'];
            return (
              <button key={b.categoryId} style={{ textAlign: 'left' }} onClick={() => setForm({ initial: b })}>
                <div className="between" style={{ marginBottom: 6 }}>
                  <span className="row" style={{ gap: 8, fontWeight: 600 }}>{c.emoji} {c.name}</span>
                  <span className={`badge ${status[0]}`}>{status[1]}</span>
                </div>
                <Bar value={spent} max={b.limit} color={ratio > 1 ? 'var(--red)' : ratio > 0.8 ? 'var(--orange)' : c.color} />
                <div className="between tiny" style={{ marginTop: 5 }}>
                  <span className="muted num">{money(spent)} von {money(b.limit)}</span>
                  <span className={`num ${ratio > 1 ? 'neg' : 'faint'}`}>{ratio > 1 ? `${money(spent - b.limit)} drüber` : `${money(b.limit - spent)} übrig`}</span>
                </div>
              </button>
            );
          })}
        </div>
      )}
      {form && <BudgetForm initial={form.initial} onClose={() => setForm(null)} />}
    </>
  );
}
