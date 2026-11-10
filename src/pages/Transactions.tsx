import { useMemo, useState } from 'react';
import { Search } from 'lucide-react';
import { useStore } from '../store';
import type { Recurring, Transaction } from '../types';
import { currentMonth, dayLabel, occurrencesInMonth, type MonthKey } from '../utils';
import { Empty, MonthNav } from '../components/ui';
import { FixedRow, TxRow } from '../components/TxRow';
import { RecurringForm, TransactionForm } from '../components/forms';

type Filter = 'all' | 'expense' | 'income';
type Row = { kind: 'tx'; tx: Transaction } | { kind: 'fix'; r: Recurring; date: string };

export default function Transactions() {
  const { data, money, cat } = useStore();
  const [month, setMonth] = useState<MonthKey>(currentMonth());
  const [q, setQ] = useState('');
  const [filter, setFilter] = useState<Filter>('all');
  const [catFilter, setCatFilter] = useState('');
  const [showFixed, setShowFixed] = useState(false);
  const [edit, setEdit] = useState<Transaction | null>(null);
  const [editFix, setEditFix] = useState<Recurring | null>(null);

  const rows = useMemo(() => {
    const query = q.trim().toLowerCase();
    const match = (type: string, categoryId: string, text: string) =>
      (filter === 'all' || filter === type) &&
      (!catFilter || catFilter === categoryId) &&
      (!query || text.toLowerCase().includes(query) || cat(categoryId).name.toLowerCase().includes(query));

    const out: (Row & { date: string })[] = [];
    // Bei Suche alle Monate durchsuchen
    for (const tx of data.transactions) {
      if (!query && !tx.date.startsWith(month)) continue;
      if (match(tx.type, tx.categoryId, tx.note)) out.push({ kind: 'tx', tx, date: tx.date });
    }
    if (showFixed && !query) {
      for (const r of data.recurring)
        for (const d of occurrencesInMonth(r, month)) if (match(r.type, r.categoryId, r.name)) out.push({ kind: 'fix', r, date: d });
    }
    out.sort((a, b) => b.date.localeCompare(a.date));
    const groups: { date: string; rows: Row[]; total: number }[] = [];
    for (const row of out) {
      let g = groups[groups.length - 1];
      if (!g || g.date !== row.date) groups.push((g = { date: row.date, rows: [], total: 0 }));
      g.rows.push(row);
      const amt = row.kind === 'tx' ? row.tx.amount : row.r.amount;
      const type = row.kind === 'tx' ? row.tx.type : row.r.type;
      g.total += type === 'income' ? amt : -amt;
    }
    return { groups, count: out.length, income: out.reduce((a, r) => a + (amtType(r) > 0 ? amtType(r) : 0), 0), expense: out.reduce((a, r) => a + (amtType(r) < 0 ? -amtType(r) : 0), 0) };
  }, [data, month, q, filter, catFilter, showFixed, cat]);

  const usedCats = data.categories.filter((c) => filter === 'all' || c.type === filter);

  return (
    <div className="page">
      <div className="topbar">
        <h1>Buchungen</h1>
      </div>
      <div className="stack">
        <div className="search">
          <Search size={18} />
          <input className="input" placeholder="Suchen (alle Monate) …" value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
        {!q && <MonthNav value={month} onChange={setMonth} allowFuture />}
        <div className="chips">
          {(['all', 'expense', 'income'] as Filter[]).map((f) => (
            <button key={f} className={`chip ${filter === f ? 'on' : ''}`} onClick={() => { setFilter(f); setCatFilter(''); }}>
              {f === 'all' ? 'Alle' : f === 'expense' ? 'Ausgaben' : 'Einnahmen'}
            </button>
          ))}
          <button className={`chip ${showFixed ? 'on' : ''}`} onClick={() => setShowFixed(!showFixed)}>Fixposten</button>
          <select className="chip" value={catFilter} onChange={(e) => setCatFilter(e.target.value)} style={catFilter ? { background: 'var(--accent)', color: '#fff' } : undefined}>
            <option value="">Kategorie</option>
            {usedCats.map((c) => <option key={c.id} value={c.id}>{c.emoji} {c.name}</option>)}
          </select>
        </div>
        <div className="tiles">
          <div className="tile">
            <div className="k">Eingänge</div>
            <div className="v num pos">+{money(rows.income)}</div>
          </div>
          <div className="tile">
            <div className="k">Ausgänge</div>
            <div className="v num">−{money(rows.expense)}</div>
          </div>
        </div>
      </div>

      {rows.groups.length === 0 ? (
        <div className="card" style={{ marginTop: 16 }}>
          <Empty icon={q ? '🔍' : '🧾'} text={q ? 'Keine Treffer.' : 'Keine Buchungen in diesem Zeitraum.'} />
        </div>
      ) : (
        rows.groups.map((g) => (
          <div key={g.date}>
            <div className="day-head">
              <span>{dayLabel(g.date)}{q ? ` ${g.date.slice(0, 4)}` : ''}</span>
              <span className="num">{money(g.total, { sign: true })}</span>
            </div>
            <div className="card flush">
              {g.rows.map((r) =>
                r.kind === 'tx' ? (
                  <TxRow key={r.tx.id} tx={r.tx} onClick={() => setEdit(r.tx)} />
                ) : (
                  <FixedRow key={r.r.id + r.date} name={r.r.name} amount={r.r.amount} type={r.r.type} categoryId={r.r.categoryId} sub={`Fixposten · ${cat(r.r.categoryId).name}`} onClick={() => setEditFix(r.r)} />
                )
              )}
            </div>
          </div>
        ))
      )}

      {edit && <TransactionForm initial={edit} onClose={() => setEdit(null)} />}
      {editFix && <RecurringForm initial={editFix} onClose={() => setEditFix(null)} />}
    </div>
  );
}

function amtType(r: Row) {
  const amt = r.kind === 'tx' ? r.tx.amount : r.r.amount;
  const type = r.kind === 'tx' ? r.tx.type : r.r.type;
  return type === 'income' ? amt : -amt;
}
