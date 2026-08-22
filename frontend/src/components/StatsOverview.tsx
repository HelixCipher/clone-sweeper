import { GitBranch, Download, Users, Copy, Activity } from 'lucide-react';

interface StatsOverviewProps {
  totalRepos: number;
  totalClones: number;
  totalUniques: number;
  totalCombined: number;
  downloads14d: number;
  downloadsTotal: number;
  generatedAt: string;
}

const stats = [
  { key: 'repos', label: 'Repositories', icon: GitBranch },
  { key: 'clones', label: 'Total Clones', icon: Copy },
  { key: 'uniques', label: 'Unique Cloners', icon: Users },
  { key: 'combined', label: 'Combined', icon: Activity },
  { key: 'dl14d', label: 'Downloads (14d)', icon: Download },
  { key: 'dlTotal', label: 'Downloads (All)', icon: Download },
] as const;

export function StatsOverview({
  totalRepos, totalClones, totalUniques, totalCombined, downloads14d, downloadsTotal, generatedAt,
}: StatsOverviewProps) {
  const values: Record<string, number> = {
    repos: totalRepos,
    clones: totalClones,
    uniques: totalUniques,
    combined: totalCombined,
    dl14d: downloads14d,
    dlTotal: downloadsTotal,
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-foreground">Overview</h2>
        {generatedAt && (
          <span className="text-xs font-mono text-muted-foreground">
            Updated: {new Date(generatedAt).toLocaleDateString()}
          </span>
        )}
      </div>
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        {stats.map(({ key, label, icon: Icon }, i) => (
          <div
            key={key}
            className="glass-card p-4 animate-slide-up"
            style={{ animationDelay: `${i * 60}ms` }}
          >
            <div className="flex items-center gap-2 mb-2">
              <Icon className="w-4 h-4 text-primary" />
              <span className="text-xs text-muted-foreground">{label}</span>
            </div>
            <p className="text-2xl font-bold font-mono text-foreground">
              {values[key].toLocaleString()}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}
