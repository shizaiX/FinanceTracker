import { useRef, useState } from 'react';
import { ChevronLeft, ChevronRight, Download, FileSpreadsheet, Plus, Sparkles, Trash2, Upload } from 'lucide-react';
import { normalize, useStore } from '../store';
import type { Category, TxType } from '../types';
import { downloadFile, todayISO } from '../utils';
import { EMPTY_DATA } from '../defaults';
import { demoData } from '../demo';
import { Seg, Sheet, Switch } from '../components/ui';
import { CategoryForm } from '../components/forms';

const CURRENCIES = ['EUR', 'CHF', 'USD', 'GBP', 'PLN', 'SEK', 'TRY'];

export default function Settings({ back }: { back: () => void }) {
  const { data, update, showToast, updateWithUndo, cat } = useStore();
  const [catType, setCatType] = useState<TxType>('expense');
  const [catForm, setCatForm] = useState<{ initial?: Category } | null>(null);
  const [confirm, setConfirm] = useState<'reset' | 'demo' | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const set = (patch: Partial<typeof data.settings>) => update((d) => ({ ...d, settings: { ...d.settings, ...patch } }));

  const exportJSON = () => {
    downloadFile(`finanzen-backup-${todayISO()}.json`, JSON.stringify(data, null, 2), 'application/json');
    showToast('Backup exportiert');
  };

  const exportCSV = () => {
    const esc = (s: string) => `"${s.replace(/"/g, '""')}"`;
    const lines = ['Datum;Typ;Kategorie;Notiz;Betrag'];
    for (const t of [...data.transactions].sort((a, b) => a.date.localeCompare(b.date))) {
      lines.push([t.date, t.type === 'income' ? 'Einnahme' : 'Ausgabe', esc(cat(t.categoryId).name), esc(t.note), (t.type === 'income' ? t.amount : -t.amount).toFixed(2).replace('.', ',')].join(';'));
    }
    downloadFile(`finanzen-buchungen-${todayISO()}.csv`, '﻿' + lines.join('\n'), 'text/csv;charset=utf-8');
    showToast('CSV exportiert');
  };

  const importJSON = async (file: File) => {
    try {
      const next = normalize(JSON.parse(await file.text()));
      updateWithUndo('Backup importiert', () => next);
    } catch {
      showToast('Datei konnte nicht gelesen werden');
    }
  };

  return (
    <div className="page">
      <div className="topbar">
        <div className="row">
          <button className="icon-btn" onClick={back} aria-label="Zurück"><ChevronLeft size={20} /></button>
          <h1>Einstellungen</h1>
        </div>
      </div>

      <div className="section-title"><h2>Darstellung</h2></div>
      <div className="card stack">
        <div className="field">
          <label>Design</label>
          <Seg options={[{ id: 'system', label: 'System' }, { id: 'dark', label: 'Dunkel' }, { id: 'light', label: 'Hell' }]} value={data.settings.theme} onChange={(theme) => set({ theme })} />
        </div>
        <div className="field">
          <label>Währung</label>
          <select className="input" value={data.settings.currency} onChange={(e) => set({ currency: e.target.value })}>
            {CURRENCIES.map((c) => <option key={c}>{c}</option>)}
          </select>
        </div>
        <div className="between">
          <div>
            <div style={{ fontWeight: 600 }}>Beträge verbergen</div>
            <div className="small faint">Diskret in der Öffentlichkeit</div>
          </div>
          <Switch on={data.settings.hideAmounts} onChange={(hideAmounts) => set({ hideAmounts })} label="Beträge verbergen" />
        </div>
      </div>

      <div className="section-title">
        <h2>Kategorien</h2>
        <button className="link row" style={{ gap: 4 }} onClick={() => setCatForm({})}><Plus size={16} /> Neu</button>
      </div>
      <Seg options={[{ id: 'expense', label: 'Ausgaben' }, { id: 'income', label: 'Einnahmen' }]} value={catType} onChange={setCatType} />
      <div className="card flush" style={{ marginTop: 10 }}>
        {data.categories.filter((c) => c.type === catType).map((c) => (
          <button key={c.id} className="list-item" onClick={() => setCatForm({ initial: c })}>
            <div className="avatar" style={{ background: `${c.color}22`, width: 36, height: 36, fontSize: 18 }}>{c.emoji}</div>
            <div className="grow li-title">{c.name}</div>
            <span style={{ width: 10, height: 10, borderRadius: 4, background: c.color }} />
            <ChevronRight size={16} className="faint" />
          </button>
        ))}
      </div>

      <div className="section-title"><h2>Daten</h2></div>
      <div className="card flush">
        <button className="list-item" onClick={exportJSON}><Download size={20} /><div className="grow"><div className="li-title">Backup exportieren</div><div className="li-sub">Alle Daten als JSON-Datei</div></div></button>
        <button className="list-item" onClick={() => fileRef.current?.click()}><Upload size={20} /><div className="grow"><div className="li-title">Backup importieren</div><div className="li-sub">Ersetzt die aktuellen Daten</div></div></button>
        <button className="list-item" onClick={exportCSV}><FileSpreadsheet size={20} /><div className="grow"><div className="li-title">Buchungen als CSV</div><div className="li-sub">Für Excel / Numbers</div></div></button>
        <button className="list-item" onClick={() => setConfirm('demo')}><Sparkles size={20} /><div className="grow"><div className="li-title">Beispieldaten laden</div><div className="li-sub">Zum Ausprobieren aller Funktionen</div></div></button>
        <button className="list-item" onClick={() => setConfirm('reset')} style={{ color: 'var(--red)' }}><Trash2 size={20} /><div className="grow"><div className="li-title">Alle Daten löschen</div></div></button>
      </div>
      <input ref={fileRef} type="file" accept="application/json,.json" hidden onChange={(e) => { const f = e.target.files?.[0]; if (f) importJSON(f); e.target.value = ''; }} />

      <p className="tiny faint" style={{ textAlign: 'center', marginTop: 24, lineHeight: 1.6 }}>
        Deine Daten bleiben ausschließlich auf diesem Gerät (lokaler Browser-Speicher).<br />
        Tipp: Über „Zum Startbildschirm hinzufügen" wird die Seite wie eine App genutzt.<br />
        {data.transactions.length} Buchungen · {data.recurring.length} Fixposten · {data.goals.length} Sparziele
      </p>

      {catForm && <CategoryForm initial={catForm.initial} type={catType} onClose={() => setCatForm(null)} />}
      {confirm && (
        <Sheet title={confirm === 'reset' ? 'Alle Daten löschen?' : 'Beispieldaten laden?'} onClose={() => setConfirm(null)}>
          <div className="stack">
            <p className="muted">
              {confirm === 'reset'
                ? 'Alle Buchungen, Fixposten, Sparziele und Budgets werden entfernt. Exportiere vorher ein Backup, falls du sie behalten willst.'
                : 'Deine aktuellen Daten werden durch Beispieldaten ersetzt. Du kannst das direkt danach rückgängig machen.'}
            </p>
            <button
              className={`btn block ${confirm === 'reset' ? 'danger' : 'primary'}`}
              onClick={() => {
                if (confirm === 'reset') updateWithUndo('Alle Daten gelöscht', (d) => ({ ...EMPTY_DATA, settings: d.settings }));
                else updateWithUndo('Beispieldaten geladen', (d) => ({ ...demoData(), settings: d.settings }));
                setConfirm(null);
              }}
            >
              {confirm === 'reset' ? 'Endgültig löschen' : 'Beispieldaten laden'}
            </button>
            <button className="btn block" onClick={() => setConfirm(null)}>Abbrechen</button>
          </div>
        </Sheet>
      )}
    </div>
  );
}
