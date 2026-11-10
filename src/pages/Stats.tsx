import { useMemo, useState, type ReactNode } from 'react';
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Line, LineChart, Pie, PieChart, ReferenceLine,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import { useStore } from '../store';
import {
  addMonths, currentMonth, daysInMonth, lastMonths, monthLabel, parseISO, summarize, type MonthKey,
} from '../utils';
import { Empty, MonthNav } from '../components/ui';

type ChartId = 'categories' | 'cashflow' | 'balance' | 'daily' | 'rate' | 'trend' | 'weekday';
const CHARTS: { id: ChartId; label: string }[] = [
  { id: 'categories', label: 'Kategorien' },
  { id: 'cashflow', label: 'Ein- & Ausgaben' },
  { id: 'daily', label: 'Monatsverlauf' },
  { id: 'balance', label: 'Vermögen' },
  { id: 'rate', label: 'Sparquote' },
  { id: 'trend', label: 'Kategorie-Trend' },
  { id: 'weekday', label: 'Wochentage' },
];
const RANGES = [3, 6, 12, 24];

// Polarität: Einnahmen grün, Ausgaben rot – aus dem Theme
const C_IN = 'var(--green)';
const C_OUT = 'var(--red)';
const C_ACC = 'var(--accent)';
const C_PREV = 'var(--text-3)';

const axis = { stroke: 'var(--text-3)', fontSize: 11, tickLine: false, axisLine: false } as const;

export default function Stats() {
  const { data, money, cat } = useStore();
  const [chart, setChart] = useState<ChartId>('categories');
  const [range, setRange] = useState(6);
  const [month, setMonth] = useState<MonthKey>(currentMonth());
  const [trendCat, setTrendCat] = useState('');
  const [catType, setCatType] = useState<'expense' | 'income'>('expense');

  const months = useMemo(() => lastMonths(range), [range]);
  const sums = useMemo(() => months.map((m) => summarize(data, m)), [data, months]);
  const monthSum = useMemo(() => summarize(data, month), [data, month]);

  const compact = (v: number) => money(v, { compact: true });
  const needsMonth = chart === 'categories' || chart === 'daily';

  /* ---------- Kennzahlen über den Zeitraum ---------- */
  const avgIn = sums.reduce((a, s) => a + s.income, 0) / sums.length;
  const avgOut = sums.reduce((a, s) => a + s.expense, 0) / sums.length;
  const totalSaved = sums.reduce((a, s) => a + s.income - s.expense, 0);

  return (
    <div className="page">
      <div className="topbar">
        <h1>Statistik</h1>
      </div>

      <div className="chips" style={{ marginBottom: 12 }}>
        {CHARTS.map((c) => (
          <button key={c.id} className={`chip ${chart === c.id ? 'on' : ''}`} onClick={() => setChart(c.id)}>
            {c.label}
          </button>
        ))}
      </div>

      {needsMonth ? (
        <MonthNav value={month} onChange={setMonth} />
      ) : (
        <div className="seg">
          {RANGES.map((r) => (
            <button key={r} className={range === r ? 'on' : ''} onClick={() => setRange(r)}>
              {r < 12 ? `${r} Mon.` : `${r / 12} J.`}
            </button>
          ))}
        </div>
      )}

      <div style={{ marginTop: 12 }}>
        {chart === 'categories' && <Categories />}
        {chart === 'cashflow' && <Cashflow />}
        {chart === 'daily' && <Daily />}
        {chart === 'balance' && <Balance />}
        {chart === 'rate' && <Rate />}
        {chart === 'trend' && <Trend />}
        {chart === 'weekday' && <Weekday />}
      </div>

      {!needsMonth && (
        <div className="tiles" style={{ marginTop: 12 }}>
          <div className="tile">
            <div className="k">Ø Einnahmen / Monat</div>
            <div className="v num">{money(avgIn)}</div>
          </div>
          <div className="tile">
            <div className="k">Ø Ausgaben / Monat</div>
            <div className="v num">{money(avgOut)}</div>
          </div>
          <div className="tile" style={{ gridColumn: 'span 2' }}>
            <div className="k">Überschuss im Zeitraum ({range} Monate)</div>
            <div className={`v num ${totalSaved < 0 ? 'neg' : 'pos'}`}>{money(totalSaved, { sign: true })}</div>
          </div>
        </div>
      )}
    </div>
  );

  /* ================= Diagramme ================= */

  function Categories() {
    const source = catType === 'expense' ? monthSum.byCategory : monthSum.incomeByCategory;
    const rows = Object.entries(source)
      .map(([id, v]) => ({ id, value: v, c: cat(id) }))
      .filter((r) => r.value > 0)
      .sort((a, b) => b.value - a.value);
    const total = rows.reduce((a, r) => a + r.value, 0);
    return (
      <ChartCard
        title={catType === 'expense' ? 'Ausgaben nach Kategorie' : 'Einnahmen nach Quelle'}
        sub={`${monthLabel(month)} · inkl. Fixposten`}
        right={
          <div className="seg" style={{ width: 112, flexShrink: 0 }}>
            <button className={catType === 'expense' ? 'on' : ''} onClick={() => setCatType('expense')}>Aus</button>
            <button className={catType === 'income' ? 'on' : ''} onClick={() => setCatType('income')}>Ein</button>
          </div>
        }
      >
        {rows.length === 0 ? (
          <Empty icon="🍩" text="Keine Daten für diesen Monat." />
        ) : (
          <>
            <div style={{ position: 'relative', height: 220 }}>
              <ResponsiveContainer>
                <PieChart>
                  <Pie data={rows} dataKey="value" nameKey="id" innerRadius={68} outerRadius={100} paddingAngle={rows.length > 1 ? 2 : 0} cornerRadius={4} stroke="none" isAnimationActive={false}>
                    {rows.map((r) => <Cell key={r.id} fill={r.c.color} />)}
                  </Pie>
                  <Tooltip content={({ active, payload }) => active && payload?.[0] ? (
                    <Tip>{(() => { const r = payload[0].payload as (typeof rows)[number]; return <Row color={r.c.color} label={`${r.c.emoji} ${r.c.name}`} value={`${money(r.value)} · ${Math.round((r.value / total) * 100)} %`} />; })()}</Tip>
                  ) : null} />
                </PieChart>
              </ResponsiveContainer>
              <div style={{ position: 'absolute', inset: 0, display: 'grid', placeItems: 'center', pointerEvents: 'none' }}>
                <div style={{ textAlign: 'center' }}>
                  <div className="tiny faint">Gesamt</div>
                  <div className="num" style={{ fontWeight: 750, fontSize: 18 }}>{money(total)}</div>
                </div>
              </div>
            </div>
            <div className="legend">
              {rows.map((r) => (
                <div key={r.id} className="legend-row">
                  <span className="dot" style={{ background: r.c.color }} />
                  <span className="grow ellipsis">{r.c.emoji} {r.c.name}</span>
                  <span className="faint small num">{Math.round((r.value / total) * 100)} %</span>
                  <span className="num" style={{ fontWeight: 600, minWidth: 90, textAlign: 'right' }}>{money(r.value)}</span>
                </div>
              ))}
            </div>
          </>
        )}
      </ChartCard>
    );
  }

  function Cashflow() {
    const rows = sums.map((s) => ({ m: monthLabel(s.month, 'short'), key: s.month, Einnahmen: s.income, Ausgaben: s.expense }));
    return (
      <ChartCard title="Einnahmen vs. Ausgaben" sub="pro Monat, inkl. Fixposten" legend={[['Einnahmen', C_IN], ['Ausgaben', C_OUT]]}>
        <div style={{ height: 240 }}>
          <ResponsiveContainer>
            <BarChart data={rows} barGap={2} barCategoryGap={range > 12 ? '15%' : '25%'} margin={{ left: 0, right: 8, top: 8 }}>
              <CartesianGrid vertical={false} stroke="var(--border)" />
              <XAxis dataKey="m" {...axis} interval={range > 12 ? 2 : 0} />
              <YAxis {...axis} width={52} tickFormatter={compact} />
              <Tooltip cursor={{ fill: 'var(--card-2)' }} content={({ active, payload }) => active && payload?.length ? (
                <Tip title={monthLabel((payload[0].payload as { key: string }).key)}>
                  <Row color={C_IN} label="Einnahmen" value={money(Number(payload[0].payload.Einnahmen))} />
                  <Row color={C_OUT} label="Ausgaben" value={money(Number(payload[0].payload.Ausgaben))} />
                  <Row label="Differenz" value={money(Number(payload[0].payload.Einnahmen) - Number(payload[0].payload.Ausgaben), { sign: true })} />
                </Tip>
              ) : null} />
              <Bar dataKey="Einnahmen" fill={C_IN} radius={[4, 4, 0, 0]} isAnimationActive={false} />
              <Bar dataKey="Ausgaben" fill={C_OUT} radius={[4, 4, 0, 0]} isAnimationActive={false} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </ChartCard>
    );
  }

  function Daily() {
    const prev = addMonths(month, -1);
    const days = Math.max(daysInMonth(month), daysInMonth(prev));
    const isCurrent = month === currentMonth();
    const today = new Date().getDate();
    const cumulative = (key: MonthKey) => {
      const perDay = new Array(days + 1).fill(0);
      for (const t of data.transactions) if (t.type === 'expense' && t.date.startsWith(key)) perDay[parseISO(t.date).getDate()] += t.amount;
      let acc = 0;
      return perDay.map((v) => (acc += v));
    };
    const cur = cumulative(month);
    const pre = cumulative(prev);
    const rows = Array.from({ length: days }, (_, i) => ({
      d: i + 1,
      Dieser: i + 1 <= daysInMonth(month) && (!isCurrent || i + 1 <= today) ? cur[i + 1] : null,
      Vormonat: i + 1 <= daysInMonth(prev) ? pre[i + 1] : null,
    }));
    return (
      <ChartCard title="Variable Ausgaben kumuliert" sub="Tag für Tag im Vergleich zum Vormonat" legend={[[monthLabel(month, 'short'), C_ACC], [monthLabel(prev, 'short'), C_PREV]]}>
        <div style={{ height: 240 }}>
          <ResponsiveContainer>
            <LineChart data={rows} margin={{ left: 0, right: 8, top: 8 }}>
              <CartesianGrid vertical={false} stroke="var(--border)" />
              <XAxis dataKey="d" {...axis} ticks={[1, 8, 15, 22, 29]} />
              <YAxis {...axis} width={52} tickFormatter={compact} />
              <Tooltip cursor={{ stroke: 'var(--text-3)', strokeDasharray: '3 3' }} content={({ active, payload, label }) => active && payload?.length ? (
                <Tip title={`Tag ${label}`}>
                  {payload.map((p) => p.value != null && <Row key={String(p.dataKey)} color={String(p.color)} label={p.dataKey === 'Dieser' ? monthLabel(month, 'short') : monthLabel(prev, 'short')} value={money(Number(p.value))} />)}
                </Tip>
              ) : null} />
              <Line dataKey="Vormonat" stroke={C_PREV} strokeWidth={2} strokeDasharray="4 4" dot={false} isAnimationActive={false} connectNulls={false} />
              <Line dataKey="Dieser" stroke={C_ACC} strokeWidth={2} dot={false} activeDot={{ r: 5, strokeWidth: 2, stroke: 'var(--card)' }} isAnimationActive={false} connectNulls={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </ChartCard>
    );
  }

  function Balance() {
    // Startpunkt: Summe aller Überschüsse vor dem Zeitraum, damit die Kurve das echte Vermögen zeigt
    let before = 0;
    const firstMonth = months[0];
    const allMonths = new Set<string>([
      ...data.transactions.map((t) => t.date.slice(0, 7)),
      ...data.recurring.map((r) => r.startDate.slice(0, 7)),
    ]);
    const earliest = [...allMonths].sort()[0];
    if (earliest && earliest < firstMonth) {
      for (let m = earliest; m < firstMonth; m = addMonths(m, 1)) {
        const s = summarize(data, m);
        before += s.income - s.expense;
      }
    }
    let acc = before;
    const rows = sums.map((s) => {
      acc += s.income - s.expense;
      return { m: monthLabel(s.month, 'short'), key: s.month, Vermögen: acc, Monat: s.income - s.expense };
    });
    return (
      <ChartCard title="Vermögensentwicklung" sub="Kumulierte Überschüsse (inkl. Sparziele)">
        <div style={{ height: 240 }}>
          <ResponsiveContainer>
            <AreaChart data={rows} margin={{ left: 0, right: 8, top: 8 }}>
              <defs>
                <linearGradient id="gBal" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="var(--accent)" stopOpacity={0.35} />
                  <stop offset="100%" stopColor="var(--accent)" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid vertical={false} stroke="var(--border)" />
              <XAxis dataKey="m" {...axis} interval={range > 12 ? 2 : 0} />
              <YAxis {...axis} width={52} tickFormatter={compact} />
              <ReferenceLine y={0} stroke="var(--text-3)" />
              <Tooltip cursor={{ stroke: 'var(--text-3)', strokeDasharray: '3 3' }} content={({ active, payload }) => active && payload?.length ? (
                <Tip title={monthLabel((payload[0].payload as { key: string }).key)}>
                  <Row color={C_ACC} label="Stand" value={money(Number(payload[0].payload.Vermögen))} />
                  <Row label="Monat" value={money(Number(payload[0].payload.Monat), { sign: true })} />
                </Tip>
              ) : null} />
              <Area dataKey="Vermögen" stroke={C_ACC} strokeWidth={2} fill="url(#gBal)" dot={false} activeDot={{ r: 5, strokeWidth: 2, stroke: 'var(--card)' }} isAnimationActive={false} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </ChartCard>
    );
  }

  function Rate() {
    const rows = sums.map((s) => ({
      m: monthLabel(s.month, 'short'), key: s.month,
      Quote: s.income > 0 ? Math.round(((s.income - s.expense) / s.income) * 1000) / 10 : 0,
    }));
    const valid = rows.filter((_, i) => sums[i].income > 0);
    const avg = valid.length ? valid.reduce((a, r) => a + r.Quote, 0) / valid.length : 0;
    return (
      <ChartCard title="Sparquote" sub={`Anteil des Einkommens, der übrig bleibt · Ø ${avg.toFixed(1).replace('.', ',')} %`}>
        <div style={{ height: 240 }}>
          <ResponsiveContainer>
            <BarChart data={rows} margin={{ left: 0, right: 8, top: 8 }}>
              <CartesianGrid vertical={false} stroke="var(--border)" />
              <XAxis dataKey="m" {...axis} interval={range > 12 ? 2 : 0} />
              <YAxis {...axis} width={40} tickFormatter={(v) => `${v} %`} />
              <ReferenceLine y={0} stroke="var(--text-3)" />
              <ReferenceLine y={20} stroke="var(--text-3)" strokeDasharray="4 4" label={{ value: '20 %-Ziel', position: 'insideTopRight', fill: 'var(--text-3)', fontSize: 11 }} />
              <Tooltip cursor={{ fill: 'var(--card-2)' }} content={({ active, payload }) => active && payload?.length ? (
                <Tip title={monthLabel((payload[0].payload as { key: string }).key)}>
                  <Row label="Sparquote" value={`${String(payload[0].payload.Quote).replace('.', ',')} %`} />
                </Tip>
              ) : null} />
              <Bar dataKey="Quote" radius={[4, 4, 4, 4]} isAnimationActive={false}>
                {rows.map((r) => <Cell key={r.key} fill={r.Quote < 0 ? C_OUT : C_ACC} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </ChartCard>
    );
  }

  function Trend() {
    const expCats = data.categories.filter((c) => c.type === 'expense');
    const totals = expCats
      .map((c) => ({ c, total: sums.reduce((a, s) => a + (s.byCategory[c.id] ?? 0), 0) }))
      .sort((a, b) => b.total - a.total);
    const selected = trendCat || totals[0]?.c.id || '';
    const c = cat(selected);
    const budget = data.budgets.find((b) => b.categoryId === selected);
    const rows = sums.map((s) => ({ m: monthLabel(s.month, 'short'), key: s.month, v: s.byCategory[selected] ?? 0 }));
    const avg = rows.reduce((a, r) => a + r.v, 0) / rows.length;
    return (
      <ChartCard
        title={`${c.emoji} ${c.name}`}
        sub={`Ø ${money(avg)} pro Monat${budget ? ` · Budget ${money(budget.limit)}` : ''}`}
        right={
          <select className="chip" value={selected} onChange={(e) => setTrendCat(e.target.value)} aria-label="Kategorie">
            {totals.map(({ c }) => <option key={c.id} value={c.id}>{c.emoji} {c.name}</option>)}
          </select>
        }
      >
        <div style={{ height: 240 }}>
          <ResponsiveContainer>
            <BarChart data={rows} margin={{ left: 0, right: 8, top: 8 }}>
              <CartesianGrid vertical={false} stroke="var(--border)" />
              <XAxis dataKey="m" {...axis} interval={range > 12 ? 2 : 0} />
              <YAxis {...axis} width={52} tickFormatter={compact} />
              {budget && <ReferenceLine y={budget.limit} stroke="var(--orange)" strokeDasharray="4 4" />}
              <Tooltip cursor={{ fill: 'var(--card-2)' }} content={({ active, payload }) => active && payload?.length ? (
                <Tip title={monthLabel((payload[0].payload as { key: string }).key)}>
                  <Row color={c.color} label={c.name} value={money(Number(payload[0].payload.v))} />
                </Tip>
              ) : null} />
              <Bar dataKey="v" fill={c.color} radius={[4, 4, 0, 0]} isAnimationActive={false} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </ChartCard>
    );
  }

  function Weekday() {
    const names = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So'];
    const sum = new Array(7).fill(0);
    const first = months[0];
    for (const t of data.transactions) {
      if (t.type !== 'expense' || t.date.slice(0, 7) < first) continue;
      const wd = (parseISO(t.date).getDay() + 6) % 7;
      sum[wd] += t.amount;
    }
    const weeks = Math.max(1, (range * 30.4) / 7);
    const rows = names.map((n, i) => ({ n, v: sum[i] / weeks }));
    const max = rows.reduce((a, r) => (r.v > a.v ? r : a), rows[0]);
    return (
      <ChartCard title="Ausgaben nach Wochentag" sub={`Ø variable Ausgaben pro Wochentag${max.v > 0 ? ` · teuerster Tag: ${max.n}` : ''}`}>
        <div style={{ height: 240 }}>
          <ResponsiveContainer>
            <BarChart data={rows} margin={{ left: 0, right: 8, top: 8 }}>
              <CartesianGrid vertical={false} stroke="var(--border)" />
              <XAxis dataKey="n" {...axis} />
              <YAxis {...axis} width={52} tickFormatter={compact} />
              <Tooltip cursor={{ fill: 'var(--card-2)' }} content={({ active, payload }) => active && payload?.length ? (
                <Tip title={String(payload[0].payload.n)}><Row color={C_ACC} label="Ø Ausgaben" value={money(Number(payload[0].payload.v))} /></Tip>
              ) : null} />
              <Bar dataKey="v" radius={[4, 4, 0, 0]} isAnimationActive={false}>
                {rows.map((r) => <Cell key={r.n} fill={C_ACC} fillOpacity={r === max ? 1 : 0.55} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </ChartCard>
    );
  }
}

/* ---------- kleine Bausteine ---------- */

function ChartCard({ title, sub, right, legend, children }: { title: string; sub?: string; right?: ReactNode; legend?: [string, string][]; children: ReactNode }) {
  return (
    <div className="card chart-card">
      <div className="chart-head between" style={{ alignItems: 'flex-start' }}>
        <div className="grow">
          <div style={{ fontWeight: 700 }}>{title}</div>
          {sub && <div className="tiny faint">{sub}</div>}
        </div>
        {right}
      </div>
      {legend && (
        <div className="row small muted" style={{ gap: 14, padding: '0 8px 6px' }}>
          {legend.map(([l, c]) => (
            <span key={l} className="row" style={{ gap: 6 }}>
              <span style={{ width: 10, height: 10, borderRadius: 3, background: c }} /> {l}
            </span>
          ))}
        </div>
      )}
      {children}
    </div>
  );
}

function Tip({ title, children }: { title?: string; children: ReactNode }) {
  return (
    <div className="tt">
      {title && <div style={{ fontWeight: 700, marginBottom: 4 }}>{title}</div>}
      {children}
    </div>
  );
}

function Row({ color, label, value }: { color?: string; label: string; value: string }) {
  return (
    <div className="tt-row">
      <span className="row" style={{ gap: 6 }}>
        {color && <span style={{ width: 8, height: 8, borderRadius: 2, background: color }} />}
        <span className="muted">{label}</span>
      </span>
      <b className="num">{value}</b>
    </div>
  );
}
