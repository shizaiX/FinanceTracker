import { useEffect, type ReactNode } from 'react';
import { ChevronLeft, ChevronRight, X } from 'lucide-react';
import { addMonths, currentMonth, monthLabel, type MonthKey } from '../utils';
import type { Category, TxType } from '../types';
import { useStore } from '../store';

export function Sheet({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    document.addEventListener('keydown', onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', onKey);
      document.body.style.overflow = prev;
    };
  }, [onClose]);
  return (
    <div className="backdrop" onClick={onClose}>
      <div className="sheet" role="dialog" aria-modal="true" aria-label={title} onClick={(e) => e.stopPropagation()}>
        <div className="grabber" />
        <div className="sheet-head">
          <h3>{title}</h3>
          <button className="icon-btn" onClick={onClose} aria-label="Schließen">
            <X size={18} />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

export function MonthNav({ value, onChange, allowFuture = false }: { value: MonthKey; onChange: (m: MonthKey) => void; allowFuture?: boolean }) {
  const isCurrent = value >= currentMonth();
  return (
    <div className="month-nav">
      <button onClick={() => onChange(addMonths(value, -1))} aria-label="Vorheriger Monat">
        <ChevronLeft size={20} />
      </button>
      <span onClick={() => onChange(currentMonth())}>{monthLabel(value)}</span>
      <button onClick={() => onChange(addMonths(value, 1))} disabled={!allowFuture && isCurrent} aria-label="Nächster Monat">
        <ChevronRight size={20} />
      </button>
    </div>
  );
}

export function Bar({ value, max, color }: { value: number; max: number; color?: string }) {
  const pct = max > 0 ? Math.min(100, (value / max) * 100) : 0;
  return (
    <div className="bar">
      <i style={{ width: `${pct}%`, background: color ?? 'var(--accent)' }} />
    </div>
  );
}

export function Ring({ pct, color, size = 64, label }: { pct: number; color: string; size?: number; label?: ReactNode }) {
  const r = (size - 8) / 2;
  const c = 2 * Math.PI * r;
  const p = Math.max(0, Math.min(1, pct));
  return (
    <div className="ring-wrap" style={{ width: size, height: size }}>
      <svg width={size} height={size} style={{ transform: 'rotate(-90deg)' }}>
        <circle cx={size / 2} cy={size / 2} r={r} stroke="var(--card-2)" strokeWidth={7} fill="none" />
        <circle
          cx={size / 2} cy={size / 2} r={r} stroke={color} strokeWidth={7} fill="none" strokeLinecap="round"
          strokeDasharray={c} strokeDashoffset={c * (1 - p)} style={{ transition: 'stroke-dashoffset .6s ease' }}
        />
      </svg>
      <div className="ring-label">{label ?? `${Math.round(p * 100)}%`}</div>
    </div>
  );
}

export function Avatar({ cat, size = 42 }: { cat: Pick<Category, 'emoji' | 'color'>; size?: number }) {
  return (
    <div className="avatar" style={{ background: `${cat.color}22`, width: size, height: size, fontSize: size * 0.48 }}>
      {cat.emoji}
    </div>
  );
}

export function CategoryPicker({ type, value, onChange }: { type: TxType; value: string; onChange: (id: string) => void }) {
  const { data } = useStore();
  const cats = data.categories.filter((c) => c.type === type);
  return (
    <div className="cat-grid">
      {cats.map((c) => (
        <button key={c.id} type="button" className={`cat-opt ${value === c.id ? 'on' : ''}`} onClick={() => onChange(c.id)}>
          <span className="em">{c.emoji}</span>
          <span>{c.name}</span>
        </button>
      ))}
    </div>
  );
}

export function TypeToggle({ value, onChange }: { value: TxType; onChange: (t: TxType) => void }) {
  return (
    <div className="seg type">
      <button type="button" className={value === 'expense' ? 'on exp' : ''} onClick={() => onChange('expense')}>
        Ausgabe
      </button>
      <button type="button" className={value === 'income' ? 'on inc' : ''} onClick={() => onChange('income')}>
        Einnahme
      </button>
    </div>
  );
}

export function Seg<T extends string>({ options, value, onChange }: { options: { id: T; label: string }[]; value: T; onChange: (v: T) => void }) {
  return (
    <div className="seg">
      {options.map((o) => (
        <button key={o.id} type="button" className={value === o.id ? 'on' : ''} onClick={() => onChange(o.id)}>
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function AmountInput({ value, onChange, autoFocus }: { value: string; onChange: (v: string) => void; autoFocus?: boolean }) {
  const { data } = useStore();
  return (
    <div className="amount-wrap">
      <input
        className="amount-input num"
        inputMode="decimal"
        placeholder="0,00"
        value={value}
        autoFocus={autoFocus}
        onChange={(e) => onChange(e.target.value.replace(/[^\d.,]/g, ''))}
      />
      <div className="cur">{data.settings.currency}</div>
    </div>
  );
}

export function Empty({ icon, text, action }: { icon: string; text: string; action?: ReactNode }) {
  return (
    <div className="empty">
      <div className="e-icon">{icon}</div>
      <p>{text}</p>
      {action}
    </div>
  );
}

export function Switch({ on, onChange, label }: { on: boolean; onChange: (v: boolean) => void; label: string }) {
  return <button type="button" role="switch" aria-checked={on} aria-label={label} className={`switch ${on ? 'on' : ''}`} onClick={() => onChange(!on)} />;
}

export function Toast() {
  const { toast, dismissToast } = useStore();
  if (!toast) return null;
  return (
    <div className="toast" key={toast.id} role="status">
      <span>{toast.text}</span>
      {toast.undo && (
        <button
          onClick={() => {
            toast.undo!();
            dismissToast();
          }}
        >
          Rückgängig
        </button>
      )}
    </div>
  );
}
