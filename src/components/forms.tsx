import { useMemo, useState } from 'react';
import { Trash2 } from 'lucide-react';
import { useStore } from '../store';
import type { Budget, Category, Goal, Interval, Recurring, Transaction, TxType } from '../types';
import { INTERVALS, parseAmount, todayISO, uid } from '../utils';
import { PALETTE } from '../defaults';
import { AmountInput, CategoryPicker, Seg, Sheet, Switch, TypeToggle } from './ui';

const amountStr = (n?: number) => (n ? String(n).replace('.', ',') : '');
const firstCat = (cats: Category[], type: TxType) => cats.find((c) => c.type === type)?.id ?? '';

/* ---------------- Buchung ---------------- */

export function TransactionForm({ initial, defaultType = 'expense', onClose }: { initial?: Transaction; defaultType?: TxType; onClose: () => void }) {
  const { data, update, updateWithUndo, showToast } = useStore();
  const [type, setType] = useState<TxType>(initial?.type ?? defaultType);
  const [amount, setAmount] = useState(amountStr(initial?.amount));
  const [categoryId, setCategoryId] = useState(initial?.categoryId ?? firstCat(data.categories, type));
  const [note, setNote] = useState(initial?.note ?? '');
  const [date, setDate] = useState(initial?.date ?? todayISO());

  const value = parseAmount(amount);
  const valid = value > 0 && categoryId;

  const suggestions = useMemo(() => {
    const seen = new Set<string>();
    for (const t of [...data.transactions].reverse()) {
      if (t.note && t.categoryId === categoryId) seen.add(t.note);
      if (seen.size >= 8) break;
    }
    return [...seen];
  }, [data.transactions, categoryId]);

  const switchType = (t: TxType) => {
    setType(t);
    if (data.categories.find((c) => c.id === categoryId)?.type !== t) setCategoryId(firstCat(data.categories, t));
  };

  const save = () => {
    if (!valid) return;
    const tx: Transaction = { id: initial?.id ?? uid(), type, amount: value, categoryId, note: note.trim(), date };
    update((d) => ({
      ...d,
      transactions: initial ? d.transactions.map((t) => (t.id === tx.id ? tx : t)) : [...d.transactions, tx],
    }));
    showToast(initial ? 'Buchung aktualisiert' : 'Buchung gespeichert');
    onClose();
  };

  const remove = () => {
    if (!initial) return;
    updateWithUndo('Buchung gelöscht', (d) => ({ ...d, transactions: d.transactions.filter((t) => t.id !== initial.id) }));
    onClose();
  };

  return (
    <Sheet title={initial ? 'Buchung bearbeiten' : 'Neue Buchung'} onClose={onClose}>
      <form className="stack" onSubmit={(e) => (e.preventDefault(), save())}>
        <TypeToggle value={type} onChange={switchType} />
        <AmountInput value={amount} onChange={setAmount} autoFocus={!initial} />
        <CategoryPicker type={type} value={categoryId} onChange={setCategoryId} />
        <div className="two">
          <div className="field">
            <label>Notiz</label>
            <input className="input" list="note-suggestions" value={note} onChange={(e) => setNote(e.target.value)} placeholder="optional" />
            <datalist id="note-suggestions">
              {suggestions.map((s) => <option key={s} value={s} />)}
            </datalist>
          </div>
          <div className="field">
            <label>Datum</label>
            <input className="input" type="date" value={date} onChange={(e) => setDate(e.target.value || todayISO())} />
          </div>
        </div>
        <button className="btn primary block" disabled={!valid}>Speichern</button>
        {initial && (
          <button type="button" className="btn danger block" onClick={remove}>
            <Trash2 size={18} /> Löschen
          </button>
        )}
      </form>
    </Sheet>
  );
}

/* ---------------- Fixe Einnahme / Ausgabe ---------------- */

export function RecurringForm({ initial, defaultType = 'expense', onClose }: { initial?: Recurring; defaultType?: TxType; onClose: () => void }) {
  const { data, update, updateWithUndo, showToast } = useStore();
  const [type, setType] = useState<TxType>(initial?.type ?? defaultType);
  const [name, setName] = useState(initial?.name ?? '');
  const [amount, setAmount] = useState(amountStr(initial?.amount));
  const [categoryId, setCategoryId] = useState(initial?.categoryId ?? (type === 'income' ? 'salary' : 'housing'));
  const [interval, setIntv] = useState<Interval>(initial?.interval ?? 'monthly');
  const [startDate, setStartDate] = useState(initial?.startDate ?? todayISO());
  const [endDate, setEndDate] = useState(initial?.endDate ?? '');
  const [active, setActive] = useState(initial?.active ?? true);

  const value = parseAmount(amount);
  const valid = value > 0 && name.trim() && categoryId;

  const switchType = (t: TxType) => {
    setType(t);
    if (data.categories.find((c) => c.id === categoryId)?.type !== t) setCategoryId(firstCat(data.categories, t));
  };

  const save = () => {
    if (!valid) return;
    const r: Recurring = {
      id: initial?.id ?? uid(), type, name: name.trim(), amount: value, categoryId, interval,
      startDate, endDate: endDate || undefined, active,
    };
    update((d) => ({ ...d, recurring: initial ? d.recurring.map((x) => (x.id === r.id ? r : x)) : [...d.recurring, r] }));
    showToast('Gespeichert');
    onClose();
  };

  const remove = () => {
    if (!initial) return;
    updateWithUndo(`„${initial.name}" gelöscht`, (d) => ({ ...d, recurring: d.recurring.filter((x) => x.id !== initial.id) }));
    onClose();
  };

  return (
    <Sheet title={initial ? 'Fixposten bearbeiten' : type === 'income' ? 'Fixe Einnahme' : 'Fixe Ausgabe'} onClose={onClose}>
      <form className="stack" onSubmit={(e) => (e.preventDefault(), save())}>
        <TypeToggle value={type} onChange={switchType} />
        <AmountInput value={amount} onChange={setAmount} />
        <div className="field">
          <label>Bezeichnung</label>
          <input className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder={type === 'income' ? 'z. B. Gehalt' : 'z. B. Miete, Netflix'} />
        </div>
        <div className="field">
          <label>Rhythmus</label>
          <select className="input" value={interval} onChange={(e) => setIntv(e.target.value as Interval)}>
            {INTERVALS.map((i) => <option key={i.id} value={i.id}>{i.label}</option>)}
          </select>
        </div>
        <div className="two">
          <div className="field">
            <label>{interval === 'weekly' ? 'Erste Zahlung' : 'Fällig ab (Tag)'}</label>
            <input className="input" type="date" value={startDate} onChange={(e) => setStartDate(e.target.value || todayISO())} />
          </div>
          <div className="field">
            <label>Endet am</label>
            <input className="input" type="date" value={endDate} min={startDate} onChange={(e) => setEndDate(e.target.value)} />
          </div>
        </div>
        <div className="field">
          <label>Kategorie</label>
          <CategoryPicker type={type} value={categoryId} onChange={setCategoryId} />
        </div>
        <div className="card between" style={{ padding: '12px 14px' }}>
          <div>
            <div style={{ fontWeight: 600 }}>Aktiv</div>
            <div className="small faint">Pausierte Posten werden nicht eingerechnet</div>
          </div>
          <Switch on={active} onChange={setActive} label="Aktiv" />
        </div>
        <button className="btn primary block" disabled={!valid}>Speichern</button>
        {initial && (
          <button type="button" className="btn danger block" onClick={remove}>
            <Trash2 size={18} /> Löschen
          </button>
        )}
      </form>
    </Sheet>
  );
}

/* ---------------- Sparziel ---------------- */

const GOAL_EMOJIS = ['🎯', '🏖️', '🚗', '🏠', '💻', '📱', '🎓', '💍', '🛟', '🎮', '🚲', '🐶'];

export function GoalForm({ initial, onClose }: { initial?: Goal; onClose: () => void }) {
  const { update, updateWithUndo, showToast } = useStore();
  const [name, setName] = useState(initial?.name ?? '');
  const [emoji, setEmoji] = useState(initial?.emoji ?? '🎯');
  const [color, setColor] = useState(initial?.color ?? PALETTE[0]);
  const [target, setTarget] = useState(amountStr(initial?.target));
  const [deadline, setDeadline] = useState(initial?.deadline ?? '');
  const [start, setStart] = useState('');

  const value = parseAmount(target);
  const valid = value > 0 && name.trim();

  const save = () => {
    if (!valid) return;
    const startAmt = parseAmount(start);
    const g: Goal = initial
      ? { ...initial, name: name.trim(), emoji, color, target: value, deadline: deadline || undefined }
      : {
          id: uid(), name: name.trim(), emoji, color, target: value, deadline: deadline || undefined, createdAt: todayISO(),
          deposits: startAmt > 0 ? [{ id: uid(), date: todayISO(), amount: startAmt }] : [],
        };
    update((d) => ({ ...d, goals: initial ? d.goals.map((x) => (x.id === g.id ? g : x)) : [...d.goals, g] }));
    showToast('Sparziel gespeichert');
    onClose();
  };

  const remove = () => {
    if (!initial) return;
    updateWithUndo(`Sparziel „${initial.name}" gelöscht`, (d) => ({ ...d, goals: d.goals.filter((x) => x.id !== initial.id) }));
    onClose();
  };

  return (
    <Sheet title={initial ? 'Sparziel bearbeiten' : 'Neues Sparziel'} onClose={onClose}>
      <form className="stack" onSubmit={(e) => (e.preventDefault(), save())}>
        <div className="field">
          <label>Zielbetrag</label>
          <AmountInput value={target} onChange={setTarget} />
        </div>
        <div className="field">
          <label>Name</label>
          <input className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="z. B. Urlaub, Notgroschen" />
        </div>
        <div className="field">
          <label>Symbol</label>
          <div className="chips" style={{ flexWrap: 'wrap' }}>
            {GOAL_EMOJIS.map((e) => (
              <button type="button" key={e} className={`chip ${emoji === e ? 'on' : ''}`} style={{ fontSize: 18, padding: '6px 10px' }} onClick={() => setEmoji(e)}>
                {e}
              </button>
            ))}
          </div>
        </div>
        <div className="field">
          <label>Farbe</label>
          <div className="swatches">
            {PALETTE.map((c) => (
              <button type="button" key={c} aria-label={c} className={`swatch ${color === c ? 'on' : ''}`} style={{ background: c }} onClick={() => setColor(c)} />
            ))}
          </div>
        </div>
        <div className="two">
          <div className="field">
            <label>Zieldatum</label>
            <input className="input" type="date" value={deadline} min={todayISO()} onChange={(e) => setDeadline(e.target.value)} />
          </div>
          {!initial && (
            <div className="field">
              <label>Bereits gespart</label>
              <input className="input" inputMode="decimal" placeholder="0,00" value={start} onChange={(e) => setStart(e.target.value)} />
            </div>
          )}
        </div>
        <button className="btn primary block" disabled={!valid}>Speichern</button>
        {initial && (
          <button type="button" className="btn danger block" onClick={remove}>
            <Trash2 size={18} /> Sparziel löschen
          </button>
        )}
      </form>
    </Sheet>
  );
}

export function DepositForm({ goal, onClose }: { goal: Goal; onClose: () => void }) {
  const { update, showToast } = useStore();
  const [mode, setMode] = useState<'in' | 'out'>('in');
  const [amount, setAmount] = useState('');
  const [date, setDate] = useState(todayISO());
  const value = parseAmount(amount);

  const save = () => {
    if (!(value > 0)) return;
    const dep = { id: uid(), date, amount: mode === 'in' ? value : -value };
    update((d) => ({ ...d, goals: d.goals.map((g) => (g.id === goal.id ? { ...g, deposits: [...g.deposits, dep] } : g)) }));
    showToast(mode === 'in' ? `Eingezahlt in „${goal.name}"` : `Entnommen aus „${goal.name}"`);
    onClose();
  };

  return (
    <Sheet title={`${goal.emoji} ${goal.name}`} onClose={onClose}>
      <form className="stack" onSubmit={(e) => (e.preventDefault(), save())}>
        <Seg options={[{ id: 'in', label: 'Einzahlen' }, { id: 'out', label: 'Entnehmen' }]} value={mode} onChange={setMode} />
        <AmountInput value={amount} onChange={setAmount} autoFocus />
        <div className="field">
          <label>Datum</label>
          <input className="input" type="date" value={date} onChange={(e) => setDate(e.target.value || todayISO())} />
        </div>
        <button className="btn primary block" disabled={!(value > 0)}>
          {mode === 'in' ? 'Einzahlen' : 'Entnehmen'}
        </button>
      </form>
    </Sheet>
  );
}

/* ---------------- Budget ---------------- */

export function BudgetForm({ initial, onClose }: { initial?: Budget; onClose: () => void }) {
  const { data, update, showToast } = useStore();
  const free = data.categories.filter((c) => c.type === 'expense' && (c.id === initial?.categoryId || !data.budgets.some((b) => b.categoryId === c.id)));
  const [categoryId, setCategoryId] = useState(initial?.categoryId ?? free[0]?.id ?? '');
  const [limit, setLimit] = useState(amountStr(initial?.limit));
  const value = parseAmount(limit);

  const save = () => {
    if (!(value > 0) || !categoryId) return;
    const b: Budget = { categoryId, limit: value };
    update((d) => ({ ...d, budgets: [...d.budgets.filter((x) => x.categoryId !== initial?.categoryId && x.categoryId !== categoryId), b] }));
    showToast('Budget gespeichert');
    onClose();
  };
  const remove = () => {
    update((d) => ({ ...d, budgets: d.budgets.filter((x) => x.categoryId !== initial?.categoryId) }));
    onClose();
  };

  return (
    <Sheet title={initial ? 'Budget bearbeiten' : 'Neues Budget'} onClose={onClose}>
      <form className="stack" onSubmit={(e) => (e.preventDefault(), save())}>
        <div className="field">
          <label>Monatliches Limit</label>
          <AmountInput value={limit} onChange={setLimit} autoFocus />
        </div>
        {free.length ? (
          <div className="cat-grid">
            {free.map((c) => (
              <button key={c.id} type="button" className={`cat-opt ${categoryId === c.id ? 'on' : ''}`} onClick={() => setCategoryId(c.id)}>
                <span className="em">{c.emoji}</span>
                <span>{c.name}</span>
              </button>
            ))}
          </div>
        ) : (
          <p className="muted small">Für alle Kategorien existiert bereits ein Budget.</p>
        )}
        <button className="btn primary block" disabled={!(value > 0) || !categoryId}>Speichern</button>
        {initial && (
          <button type="button" className="btn danger block" onClick={remove}>
            <Trash2 size={18} /> Budget entfernen
          </button>
        )}
      </form>
    </Sheet>
  );
}

/* ---------------- Kategorie ---------------- */

export function CategoryForm({ initial, type, onClose }: { initial?: Category; type: TxType; onClose: () => void }) {
  const { data, update, showToast } = useStore();
  const [name, setName] = useState(initial?.name ?? '');
  const [emoji, setEmoji] = useState(initial?.emoji ?? '🏷️');
  const [color, setColor] = useState(initial?.color ?? PALETTE[0]);
  const inUse = initial
    ? data.transactions.some((t) => t.categoryId === initial.id) || data.recurring.some((r) => r.categoryId === initial.id)
    : false;

  const save = () => {
    if (!name.trim()) return;
    const c: Category = { id: initial?.id ?? uid(), name: name.trim(), emoji: emoji.trim() || '🏷️', color, type: initial?.type ?? type };
    update((d) => ({ ...d, categories: initial ? d.categories.map((x) => (x.id === c.id ? c : x)) : [...d.categories, c] }));
    showToast('Kategorie gespeichert');
    onClose();
  };
  const remove = () => {
    if (!initial || inUse) return;
    update((d) => ({
      ...d,
      categories: d.categories.filter((x) => x.id !== initial.id),
      budgets: d.budgets.filter((b) => b.categoryId !== initial.id),
    }));
    onClose();
  };

  return (
    <Sheet title={initial ? 'Kategorie bearbeiten' : 'Neue Kategorie'} onClose={onClose}>
      <form className="stack" onSubmit={(e) => (e.preventDefault(), save())}>
        <div className="row">
          <div className="field" style={{ width: 84 }}>
            <label>Emoji</label>
            <input className="input" style={{ textAlign: 'center', fontSize: 22 }} value={emoji} maxLength={4} onChange={(e) => setEmoji(e.target.value)} />
          </div>
          <div className="field grow">
            <label>Name</label>
            <input className="input" value={name} onChange={(e) => setName(e.target.value)} autoFocus />
          </div>
        </div>
        <div className="swatches">
          {PALETTE.map((c) => (
            <button type="button" key={c} aria-label={c} className={`swatch ${color === c ? 'on' : ''}`} style={{ background: c }} onClick={() => setColor(c)} />
          ))}
        </div>
        <button className="btn primary block" disabled={!name.trim()}>Speichern</button>
        {initial && (
          <button type="button" className="btn danger block" onClick={remove} disabled={inUse}>
            <Trash2 size={18} /> {inUse ? 'Wird noch verwendet' : 'Löschen'}
          </button>
        )}
      </form>
    </Sheet>
  );
}
