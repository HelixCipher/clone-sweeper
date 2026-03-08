import { useQuery } from '@tanstack/react-query';
import { fetchDashboardData } from '@/lib/parser';
import { StatsOverview } from '@/components/StatsOverview';
import { TopReposChart } from '@/components/TopReposChart';
import { RepoTable } from '@/components/RepoTable';
import { TrendsChart } from '@/components/TrendsChart';
import { ThemeToggle } from '@/components/ThemeToggle';
import { Activity, ExternalLink, GitCompare } from 'lucide-react';
import { Link } from 'react-router-dom';

const Index = () => {
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
          <p className="text-sm text-muted-foreground font-mono">Loading clone data…</p>
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
            {error instanceof Error ? error.message : 'Could not fetch SVG data from GitHub.'}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen px-4 py-6 md:px-8 md:py-8 max-w-[1400px] mx-auto">
      {/* Header */}
      <header className="mb-8 animate-fade-in">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl md:text-3xl font-bold">
              <span className="text-gradient">Clone Sweeper</span>
            </h1>
            <p className="text-sm text-muted-foreground mt-1 font-mono">
              {data.owner} · GitHub repository analytics
            </p>
          </div>
          <div className="flex items-center gap-2">
            <ThemeToggle />
            <Link
              to="/compare"
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium bg-secondary text-secondary-foreground rounded-md hover:bg-secondary/80 transition-colors"
            >
              <GitCompare className="w-3.5 h-3.5" />
              Compare
            </Link>
            <a
              href="https://github.com/HelixCipher/clone-sweeper"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium bg-secondary text-secondary-foreground rounded-md hover:bg-secondary/80 transition-colors"
            >
              <ExternalLink className="w-3.5 h-3.5" />
              Source
            </a>
          </div>
        </div>
      </header>

      <div className="space-y-6">
        <StatsOverview
          totalRepos={data.totalRepos}
          totalClones={data.totalClones}
          totalUniques={data.totalUniques}
          totalCombined={data.totalCombined}
          downloads14d={data.downloads14d}
          downloadsTotal={data.downloadsTotal}
          generatedAt={data.generatedAt}
        />

        <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
          <TopReposChart repos={data.summaryRepos} />
          <TrendsChart
            monthly={data.monthlyHistory}
            yearly={data.yearlyHistory}
            monthRange={data.monthRange}
            yearRange={data.yearRange}
          />
        </div>

        <RepoTable repos={data.repoDetails} />
      </div>

      <footer className="mt-8 pb-4 text-center text-xs text-muted-foreground font-mono">
        Data sourced from GitHub Traffic API via Clone Sweeper
      </footer>
    </div>
  );
};

export default Index;
