import { useState, useMemo } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { fetchDashboardData } from '@/lib/parser';
import { ThemeToggle } from '@/components/ThemeToggle';
import { Activity, ArrowLeft, GitCompare } from 'lucide-react';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend,
} from 'recharts';

const Compare = () => {
  const [repoA, setRepoA] = useState('');
  const [repoB, setRepoB] = useState('');

  const { data, isLoading, error } = useQuery({
    queryKey: ['dashboard'],
    queryFn: fetchDashboardData,
    staleTime: 5 * 60 * 1000,
  });

  const repoNames = useMemo(() => data?.repoDetails.map(r => r.name) ?? [], [data]);

  const getRepoStats = (name: string) => {
    if (!data || !name) return null;
    const details = data.repoDetails.find(r => r.name === name);
    const summary = data.summaryRepos.find(r => r.name === name);
    return { details, summary };
  };

  const comparisonData = useMemo(() => {
    const a = getRepoStats(repoA);
    const b = getRepoStats(repoB);
    if (!a?.details && !a?.summary) return [];
    if (!b?.details && !b?.summary) return [];

    const metrics = [
      { metric: 'Stars', [repoA]: a.details?.stars ?? 0, [repoB]: b.details?.stars ?? 0 },
      { metric: 'Forks', [repoA]: a.details?.forks ?? 0, [repoB]: b.details?.forks ?? 0 },
      { metric: 'Watchers', [repoA]: a.details?.watchers ?? 0, [repoB]: b.details?.watchers ?? 0 },
      { metric: 'Open Issues', [repoA]: a.details?.openIssues ?? 0, [repoB]: b.details?.openIssues ?? 0 },
      { metric: 'Clones (14d)', [repoA]: a.details?.clones14d ?? a.summary?.clones ?? 0, [repoB]: b.details?.clones14d ?? b.summary?.clones ?? 0 },
      { metric: 'Uniques (14d)', [repoA]: a.details?.uniques14d ?? a.summary?.uniques ?? 0, [repoB]: b.details?.uniques14d ?? b.summary?.uniques ?? 0 },
    ];
    return metrics;
  }, [repoA, repoB, data]);

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="flex flex-col items-center gap-3">
          <Activity className="w-8 h-8 text-primary animate-pulse" />
          <p className="text-sm text-muted-foreground font-mono">Loading data…</p>
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="glass-card p-8 text-center max-w-md">
          <p className="text-destructive font-medium mb-2">Failed to load data</p>
        </div>
      </div>
    );
  }

  const statsA = getRepoStats(repoA);
  const statsB = getRepoStats(repoB);

  const StatCard = ({ label, valueA, valueB }: { label: string; valueA: number; valueB: number }) => {
    const diff = valueA - valueB;
    return (
      <div className="glass-card p-4">
        <p className="text-xs text-muted-foreground mb-2">{label}</p>
        <div className="flex items-end justify-between gap-4">
          <div>
            <p className="text-lg font-bold font-mono text-foreground">{valueA.toLocaleString()}</p>
            <p className="text-[10px] text-muted-foreground truncate max-w-[120px]">{repoA || '—'}</p>
          </div>
          <div className="text-right">
            <p className="text-lg font-bold font-mono text-foreground">{valueB.toLocaleString()}</p>
            <p className="text-[10px] text-muted-foreground truncate max-w-[120px]">{repoB || '—'}</p>
          </div>
        </div>
        {repoA && repoB && (
          <p className={`text-xs font-mono mt-2 ${diff > 0 ? 'text-accent' : diff < 0 ? 'text-destructive' : 'text-muted-foreground'}`}>
            {diff > 0 ? '+' : ''}{diff.toLocaleString()} {diff > 0 ? '▲' : diff < 0 ? '▼' : '—'}
          </p>
        )}
      </div>
    );
  };

  return (
    <div className="min-h-screen px-4 py-6 md:px-8 md:py-8 max-w-[1400px] mx-auto">
      <header className="mb-8 animate-fade-in">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Link
              to="/"
              className="inline-flex items-center justify-center w-9 h-9 rounded-md bg-secondary text-secondary-foreground hover:bg-secondary/80 transition-colors"
              aria-label="Back to dashboard"
            >
              <ArrowLeft className="w-4 h-4" />
            </Link>
            <div>
              <h1 className="text-2xl md:text-3xl font-bold">
                <span className="text-gradient">Compare Repos</span>
              </h1>
              <p className="text-sm text-muted-foreground mt-1 font-mono">
                Side-by-side metric comparison
              </p>
            </div>
          </div>
          <ThemeToggle />
        </div>
      </header>

      {/* Selectors */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-8 animate-fade-in">
        <div className="glass-card p-4">
          <label className="text-xs font-medium text-muted-foreground mb-2 block">Repository A</label>
          <select
            value={repoA}
            onChange={e => setRepoA(e.target.value)}
            className="w-full bg-muted border border-border rounded-md px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
          >
            <option value="">Select a repository…</option>
            {repoNames.filter(n => n !== repoB).map(n => (
              <option key={n} value={n}>{n}</option>
            ))}
          </select>
        </div>
        <div className="glass-card p-4">
          <label className="text-xs font-medium text-muted-foreground mb-2 block">Repository B</label>
          <select
            value={repoB}
            onChange={e => setRepoB(e.target.value)}
            className="w-full bg-muted border border-border rounded-md px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
          >
            <option value="">Select a repository…</option>
            {repoNames.filter(n => n !== repoA).map(n => (
              <option key={n} value={n}>{n}</option>
            ))}
          </select>
        </div>
      </div>

      {repoA && repoB && comparisonData.length > 0 ? (
        <div className="space-y-6">
          {/* Stat cards grid */}
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3 animate-slide-up">
            {comparisonData.map(row => (
              <StatCard
                key={row.metric}
                label={row.metric as string}
                valueA={row[repoA] as number}
                valueB={row[repoB] as number}
              />
            ))}
          </div>

          {/* Comparison chart */}
          <div className="glass-card p-5 animate-slide-up" style={{ animationDelay: '200ms' }}>
            <h2 className="text-lg font-semibold text-foreground mb-4">Metric Comparison</h2>
            <ResponsiveContainer width="100%" height={350}>
              <BarChart data={comparisonData} margin={{ left: 10, right: 20, top: 5, bottom: 5 }}>
                <XAxis
                  dataKey="metric"
                  stroke="hsl(var(--border))"
                  tick={{ fill: 'hsl(var(--muted-foreground))', fontSize: 11 }}
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
                />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Bar dataKey={repoA} fill="hsl(var(--chart-blue))" radius={[4, 4, 0, 0]} maxBarSize={50} />
                <Bar dataKey={repoB} fill="hsl(var(--chart-green))" radius={[4, 4, 0, 0]} maxBarSize={50} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      ) : (
        <div className="flex flex-col items-center justify-center py-20 text-muted-foreground animate-fade-in">
          <GitCompare className="w-12 h-12 mb-4 opacity-40" />
          <p className="text-sm font-mono">Select two repositories to compare</p>
        </div>
      )}

      <footer className="mt-8 pb-4 text-center text-xs text-muted-foreground font-mono">
        Data sourced from GitHub Traffic API via Clone Sweeper
      </footer>
    </div>
  );
};

export default Compare;
