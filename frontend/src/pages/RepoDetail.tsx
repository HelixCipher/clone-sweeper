import { useParams, Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { fetchDashboardData } from '@/lib/parser';
import { ThemeToggle } from '@/components/ThemeToggle';
import { Activity, ArrowLeft, GitBranch, Star, GitFork, Eye, AlertCircle, Download, Copy, Users, Clock, ExternalLink } from 'lucide-react';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend,
} from 'recharts';

const RepoDetail = () => {
  const { repoName } = useParams<{ repoName: string }>();

  const { data, isLoading, error } = useQuery({
    queryKey: ['dashboard'],
    queryFn: fetchDashboardData,
    staleTime: 5 * 60 * 1000,
  });

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="flex flex-col items-center gap-3">
          <Activity className="w-8 h-8 text-primary animate-pulse" />
          <p className="text-sm text-muted-foreground font-mono">Loading repo data…</p>
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="glass-card p-8 text-center max-w-md">
          <p className="text-destructive font-medium mb-2">Failed to load data</p>
          <p className="text-sm text-muted-foreground">
            {error instanceof Error ? error.message : 'Could not fetch data.'}
          </p>
        </div>
      </div>
    );
  }

  const details = data.repoDetails.find(r => r.name === repoName);
  const summary = data.summaryRepos.find(r => r.name === repoName);

  const monthlyEntries = data.monthlyHistory.filter(e => e.repo === repoName);
  const yearlyEntries = data.yearlyHistory.filter(e => e.repo === repoName);

  if (!details && !summary) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="glass-card p-8 text-center max-w-md">
          <p className="text-foreground font-medium mb-2">Repository not found</p>
          <p className="text-sm text-muted-foreground mb-4">
            No data found for "{repoName}"
          </p>
          <Link to="/" className="text-primary hover:underline text-sm font-medium">
            ← Back to dashboard
          </Link>
        </div>
      </div>
    );
  }

  const statCards = [
    { label: 'Stars', value: details?.stars, icon: Star },
    { label: 'Forks', value: details?.forks, icon: GitFork },
    { label: 'Watchers', value: details?.watchers, icon: Eye },
    { label: 'Open Issues', value: details?.openIssues, icon: AlertCircle },
    { label: 'Clones (14d)', value: details?.clones14d ?? summary?.clones, icon: Copy },
    { label: 'Uniques (14d)', value: details?.uniques14d ?? summary?.uniques, icon: Users },
    { label: 'Downloads (14d)', value: details?.downloads14d, icon: Download },
    { label: 'Downloads (Total)', value: details?.downloadsTotal, icon: Download },
  ].filter(s => s.value !== null && s.value !== undefined);

  // Build chart data from history entries
  const historyChartData = (() => {
    const metrics: Record<string, { clones: number; uniques: number }> = {};
    const addEntries = (entries: typeof monthlyEntries, prefix: string) => {
      entries.forEach(e => {
        if (e.metric === 'downloads') return;
        const key = prefix;
        if (!metrics[key]) metrics[key] = { clones: 0, uniques: 0 };
        if (e.metric === 'clones') metrics[key].clones = e.latestValue;
        if (e.metric === 'uniques') metrics[key].uniques = e.latestValue;
      });
    };
    addEntries(monthlyEntries, 'Monthly');
    addEntries(yearlyEntries, 'Yearly');
    return Object.entries(metrics).map(([period, vals]) => ({ period, ...vals }));
  })();

  // Combined value
  const combined = summary?.combined ?? ((details?.clones14d ?? 0) + (details?.uniques14d ?? 0));

  return (
    <div className="min-h-screen px-4 py-6 md:px-8 md:py-8 max-w-[1400px] mx-auto">
      {/* Header */}
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
                <span className="text-gradient">{repoName}</span>
              </h1>
              {details?.description && details.description !== '-' && (
                <p className="text-sm text-muted-foreground mt-1 max-w-xl">
                  {details.description}
                </p>
              )}
            </div>
          </div>
          <div className="flex items-center gap-2">
            <ThemeToggle />
            <a
              href={`https://github.com/HelixCipher/${repoName}`}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium bg-secondary text-secondary-foreground rounded-md hover:bg-secondary/80 transition-colors"
            >
              <ExternalLink className="w-3.5 h-3.5" />
              View on GitHub
            </a>
          </div>
        </div>
      </header>

      <div className="space-y-6">
        {/* Meta row */}
        <div className="flex flex-wrap items-center gap-3 animate-fade-in">
          {details?.language && details.language !== '-' && (
            <span className="inline-flex items-center gap-1.5 px-3 py-1 text-xs font-medium bg-secondary text-secondary-foreground rounded-full">
              <GitBranch className="w-3 h-3" />
              {details.language}
            </span>
          )}
          {details?.lastPush && (
            <span className="inline-flex items-center gap-1.5 px-3 py-1 text-xs font-mono text-muted-foreground bg-muted rounded-full">
              <Clock className="w-3 h-3" />
              Last push: {new Date(details.lastPush).toLocaleDateString()}
            </span>
          )}
          {combined > 0 && (
            <span className="inline-flex items-center gap-1.5 px-3 py-1 text-xs font-mono text-muted-foreground bg-muted rounded-full">
              <Activity className="w-3 h-3" />
              Combined: {combined.toLocaleString()}
            </span>
          )}
        </div>

        {/* Stat cards */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {statCards.map(({ label, value, icon: Icon }, i) => (
            <div
              key={label}
              className="glass-card p-4 animate-slide-up"
              style={{ animationDelay: `${i * 60}ms` }}
            >
              <div className="flex items-center gap-2 mb-2">
                <Icon className="w-4 h-4 text-primary" />
                <span className="text-xs text-muted-foreground">{label}</span>
              </div>
              <p className="text-2xl font-bold font-mono text-foreground">
                {(value ?? 0).toLocaleString()}
              </p>
            </div>
          ))}
        </div>

        {/* History chart */}
        {historyChartData.length > 0 && (
          <div className="glass-card p-5 animate-slide-up" style={{ animationDelay: '300ms' }}>
            <h2 className="text-lg font-semibold text-foreground mb-4">Clone History</h2>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={historyChartData} margin={{ left: 10, right: 20, top: 5, bottom: 5 }}>
                <XAxis
                  dataKey="period"
                  stroke="hsl(var(--border))"
                  tick={{ fill: 'hsl(var(--muted-foreground))', fontSize: 12 }}
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
                <Legend wrapperStyle={{ fontSize: 12, fontFamily: 'Inter' }} />
                <Bar dataKey="clones" fill="hsl(var(--chart-blue))" radius={[4, 4, 0, 0]} maxBarSize={60} />
                <Bar dataKey="uniques" fill="hsl(var(--chart-green))" radius={[4, 4, 0, 0]} maxBarSize={60} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}

        {/* All history entries table */}
        {(monthlyEntries.length > 0 || yearlyEntries.length > 0) && (
          <div className="glass-card p-5 animate-slide-up" style={{ animationDelay: '400ms' }}>
            <h2 className="text-lg font-semibold text-foreground mb-4">History Entries</h2>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border">
                    <th className="px-4 py-3 text-xs font-medium text-muted-foreground text-left">Period</th>
                    <th className="px-4 py-3 text-xs font-medium text-muted-foreground text-left">Metric</th>
                    <th className="px-4 py-3 text-xs font-medium text-muted-foreground text-right">Latest Value</th>
                  </tr>
                </thead>
                <tbody>
                  {[...monthlyEntries.map(e => ({ ...e, period: 'Monthly' })),
                    ...yearlyEntries.map(e => ({ ...e, period: 'Yearly' }))
                  ].map((entry, i) => (
                    <tr key={i} className="border-b border-border/30 hover:bg-muted/50 transition-colors">
                      <td className="px-4 py-3 font-mono text-xs text-foreground">{entry.period}</td>
                      <td className="px-4 py-3 font-mono text-xs text-secondary-foreground capitalize">{entry.metric}</td>
                      <td className="px-4 py-3 font-mono text-xs text-foreground text-right">{entry.latestValue.toLocaleString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>

      <footer className="mt-8 pb-4 text-center text-xs text-muted-foreground font-mono">
        Data sourced from GitHub Traffic API via Clone Sweeper
      </footer>
    </div>
  );
};

export default RepoDetail;
