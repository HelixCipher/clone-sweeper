import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts';
import type { RepoSummary } from '@/lib/types';
import { useState } from 'react';

interface TopReposChartProps {
  repos: RepoSummary[];
}

type MetricKey = 'clones' | 'uniques' | 'combined';

const metrics: { key: MetricKey; label: string; color: string }[] = [
  { key: 'clones', label: 'Clones', color: 'hsl(200, 100%, 55%)' },
  { key: 'uniques', label: 'Uniques', color: 'hsl(160, 70%, 45%)' },
  { key: 'combined', label: 'Combined', color: 'hsl(38, 95%, 60%)' },
];

export function TopReposChart({ repos }: TopReposChartProps) {
  const [activeMetric, setActiveMetric] = useState<MetricKey>('combined');

  const activeColor = metrics.find(m => m.key === activeMetric)!.color;

  const data = [...repos]
    .sort((a, b) => b[activeMetric] - a[activeMetric])
    .slice(0, 10)
    .map(r => ({
      name: r.name.length > 20 ? r.name.slice(0, 18) + '…' : r.name,
      fullName: r.name,
      value: r[activeMetric],
      clones: r.clones,
      uniques: r.uniques,
      combined: r.combined,
    }));

  return (
    <div className="glass-card p-5 animate-slide-up" style={{ animationDelay: '200ms' }}>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-foreground">Top Repositories</h2>
        <div className="flex gap-1 p-1 bg-muted rounded-md">
          {metrics.map(m => (
            <button
              key={m.key}
              onClick={() => setActiveMetric(m.key)}
              className={`px-3 py-1 text-xs font-medium rounded transition-all ${
                activeMetric === m.key
                  ? 'bg-primary text-primary-foreground'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              {m.label}
            </button>
          ))}
        </div>
      </div>

      <ResponsiveContainer width="100%" height={360}>
        <BarChart data={data} layout="vertical" margin={{ left: 10, right: 30, top: 5, bottom: 5 }}>
          <XAxis type="number" stroke="hsl(var(--border))" tick={{ fill: 'hsl(var(--muted-foreground))', fontSize: 11 }} />
          <YAxis
            type="category"
            dataKey="name"
            width={150}
            tick={{ fill: 'hsl(var(--foreground))', fontSize: 11, fontFamily: 'JetBrains Mono' }}
          />
          <Tooltip
            contentStyle={{
              background: 'hsl(var(--card))',
              border: '1px solid hsl(var(--border))',
              borderRadius: '8px',
              fontFamily: 'Inter',
              fontSize: 12,
              color: 'hsl(var(--foreground))',
            }}
            labelStyle={{ color: 'hsl(var(--foreground))', fontWeight: 600 }}
            itemStyle={{ color: 'hsl(var(--muted-foreground))' }}
            formatter={(value: number) => [value.toLocaleString(), activeMetric]}
            labelFormatter={(label) => data.find(d => d.name === label)?.fullName || label}
          />
          <Bar dataKey="value" radius={[0, 4, 4, 0]} maxBarSize={28}>
            {data.map((_, index) => (
              <Cell key={index} fill={activeColor} fillOpacity={1 - index * 0.06} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
