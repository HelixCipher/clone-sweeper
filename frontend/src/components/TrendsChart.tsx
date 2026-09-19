import { useMemo, useState } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend,
} from 'recharts';
import type { HistoryEntry } from '@/lib/types';

interface TrendsChartProps {
  monthly: HistoryEntry[];
  yearly: HistoryEntry[];
  monthRange: string;
  yearRange: string;
}

export function TrendsChart({ monthly, yearly, monthRange, yearRange }: TrendsChartProps) {
  const [view, setView] = useState<'monthly' | 'yearly'>('monthly');
  const [metricFilter, setMetricFilter] = useState<'all' | 'clones' | 'uniques' | 'downloads'>('clones');

  const entries = view === 'monthly' ? monthly : yearly;

  // Group by repo, group by metric
  const chartData = useMemo(() => {
    const filtered = entries.filter(e => {
      if (metricFilter === 'all') return true;
      return e.metric === metricFilter;
    });

    // Group by repo
    const repoMap = new Map<string, { clones: number; uniques: number; downloads: number }>();
    filtered.forEach(e => {
      const existing = repoMap.get(e.repo) || { clones: 0, uniques: 0, downloads: 0 };
      if (e.metric === 'clones') existing.clones = e.latestValue;
      if (e.metric === 'uniques') existing.uniques = e.latestValue;
      if (e.metric === 'downloads') existing.downloads = e.latestValue;
      repoMap.set(e.repo, existing);
    });

    return Array.from(repoMap.entries())
      .map(([repo, vals]) => ({
        name: repo.length > 18 ? repo.slice(0, 16) + '…' : repo,
        fullName: repo,
        clones: vals.clones,
        uniques: vals.uniques,
        downloads: vals.downloads,
      }))
      .sort((a, b) => (b.clones + b.uniques + b.downloads) - (a.clones + a.uniques + a.downloads));
  }, [entries, metricFilter]);

  const range = view === 'monthly' ? monthRange : yearRange;

  return (
    <div className="glass-card p-5 animate-slide-up" style={{ animationDelay: '400ms' }}>
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between mb-4 gap-3">
        <div>
          <h2 className="text-lg font-semibold text-foreground">Clone Trends</h2>
          {range && (
            <p className="text-xs text-muted-foreground font-mono mt-0.5">{range}</p>
          )}
        </div>
        <div className="flex gap-2">
          <div className="flex gap-1 p-1 bg-muted rounded-md">
            {(['monthly', 'yearly'] as const).map(v => (
              <button
                key={v}
                onClick={() => setView(v)}
                className={`px-3 py-1 text-xs font-medium rounded transition-all ${
                  view === v
                    ? 'bg-primary text-primary-foreground'
                    : 'text-muted-foreground hover:text-foreground'
                }`}
              >
                {v === 'monthly' ? 'Monthly' : 'Yearly'}
              </button>
            ))}
          </div>
          <div className="flex gap-1 p-1 bg-muted rounded-md">
            {(['clones', 'uniques', 'downloads', 'all'] as const).map(m => (
              <button
                key={m}
                onClick={() => setMetricFilter(m)}
                className={`px-3 py-1 text-xs font-medium rounded capitalize transition-all ${
                  metricFilter === m
                    ? 'bg-primary text-primary-foreground'
                    : 'text-muted-foreground hover:text-foreground'
                }`}
              >
                {m}
              </button>
            ))}
          </div>
        </div>
      </div>

      {chartData.length === 0 ? (
        <div className="h-[300px] flex items-center justify-center text-muted-foreground text-sm">
          No trend data available yet
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={340}>
          <BarChart data={chartData} margin={{ left: 10, right: 20, top: 5, bottom: 5 }}>
            <XAxis
              dataKey="name"
              stroke="hsl(var(--border))"
              tick={{ fill: 'hsl(var(--muted-foreground))', fontSize: 10, fontFamily: 'JetBrains Mono' }}
              angle={-35}
              textAnchor="end"
              height={70}
            />
            <YAxis
              stroke="hsl(var(--border))"
              tick={{ fill: 'hsl(var(--muted-foreground))', fontSize: 11 }}
            />
            <Tooltip
              contentStyle={{
                background: 'hsl(var(--card))',
                border: '1px solid hsl(var(--border))',
                borderRadius: '8px',
                fontSize: 12,
                color: 'hsl(var(--foreground))',
              }}
              labelStyle={{ color: 'hsl(var(--foreground))', fontWeight: 600 }}
              labelFormatter={(label) => chartData.find(d => d.name === label)?.fullName || label}
            />
            <Legend
              wrapperStyle={{ fontSize: 12, fontFamily: 'Inter' }}
            />
            {(metricFilter === 'all' || metricFilter === 'clones') && (
              <Bar dataKey="clones" fill="hsl(var(--chart-blue))" radius={[4, 4, 0, 0]} maxBarSize={40} />
            )}
            {(metricFilter === 'all' || metricFilter === 'uniques') && (
              <Bar dataKey="uniques" fill="hsl(var(--chart-green))" radius={[4, 4, 0, 0]} maxBarSize={40} />
            )}
            {(metricFilter === 'all' || metricFilter === 'downloads') && (
              <Bar dataKey="downloads" fill="hsl(var(--chart-amber))" radius={[4, 4, 0, 0]} maxBarSize={40} />
            )}
          </BarChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
