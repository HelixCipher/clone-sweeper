// Types for Clone Sweeper data
export interface RepoSummary {
  name: string;
  clones: number;
  uniques: number;
  combined: number;
}

export interface RepoDetails {
  name: string;
  description: string;
  language: string;
  stars: number;
  forks: number;
  watchers: number;
  openIssues: number;
  lastPush: string;
  clones14d: number | null;
  uniques14d: number | null;
  downloads14d: number | null;
  downloadsTotal: number | null;
}

export interface HistoryEntry {
  repo: string;
  metric: 'clones' | 'uniques' | 'downloads';
  latestValue: number;
  color: string;
  points: { x: number; y: number }[];
}

export interface DashboardData {
  owner: string;
  totalRepos: number;
  totalClones: number;
  totalUniques: number;
  totalCombined: number;
  downloads14d: number;
  downloadsTotal: number;
  generatedAt: string;
  summaryRepos: RepoSummary[];
  repoDetails: RepoDetails[];
  monthlyHistory: HistoryEntry[];
  yearlyHistory: HistoryEntry[];
  monthRange: string;
  yearRange: string;
}
