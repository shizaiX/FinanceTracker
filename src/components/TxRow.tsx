import { Repeat } from 'lucide-react';
import { useStore } from '../store';
import type { Transaction } from '../types';
import { Avatar } from './ui';

export function TxRow({ tx, onClick, showDate }: { tx: Transaction; onClick?: () => void; showDate?: string }) {
  const { cat, money } = useStore();
  const c = cat(tx.categoryId);
  return (
    <button className="list-item" onClick={onClick}>
      <Avatar cat={c} />
      <div className="grow">
        <div className="li-title ellipsis">{tx.note || c.name}</div>
        <div className="li-sub ellipsis">{tx.note ? c.name : ''}{showDate ? `${tx.note ? ' · ' : ''}${showDate}` : ''}</div>
      </div>
      <div className={`li-amt num ${tx.type === 'income' ? 'pos' : ''}`}>
        {tx.type === 'income' ? '+' : '−'}
        {money(tx.amount)}
      </div>
    </button>
  );
}

export function FixedRow({ name, amount, type, categoryId, sub, onClick, muted }: {
  name: string; amount: number; type: 'income' | 'expense'; categoryId: string; sub: string; onClick?: () => void; muted?: boolean;
}) {
  const { cat, money } = useStore();
  const c = cat(categoryId);
  return (
    <button className="list-item" onClick={onClick} style={muted ? { opacity: 0.5 } : undefined}>
      <Avatar cat={c} />
      <div className="grow">
        <div className="li-title ellipsis">{name}</div>
        <div className="li-sub ellipsis row" style={{ gap: 4 }}>
          <Repeat size={12} /> {sub}
        </div>
      </div>
      <div className={`li-amt num ${type === 'income' ? 'pos' : ''}`}>
        {type === 'income' ? '+' : '−'}
        {money(amount)}
      </div>
    </button>
  );
}
