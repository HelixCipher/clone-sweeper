import type { DashboardData, RepoSummary, RepoDetails, HistoryEntry } from './types';
import { getOwnerAndRepo } from './utils';

function getRawBase(): string {
  const { owner, repo } = getOwnerAndRepo();
  return `https://raw.githubusercontent.com/${owner}/${repo}/main`;
}

const RAW_BASE = getRawBase();

async function fetchJson<T>(filename: string): Promise<T> {
  const res = await fetch(`${RAW_BASE}/${filename}`);
  if (!res.ok) throw new Error(`Failed to fetch ${filename}`);
  return res.json();
}

interface StatsJson {
  owner: string;
  totalRepos: number;
  totalClones: number;
  totalUniques: number;
  totalCombined: number;
  downloads14d: number;
  downloadsTotal: number;
  repos: RepoSummary[];
}

interface RepoClonesJson {
  generatedAt: string;
  repos: RepoDetails[];
}

interface HistoryJson {
  monthly: HistoryEntry[];
  yearly: HistoryEntry[];
  monthRange: string;
  yearRange: string;
}

export async function fetchDashboardData(): Promise<DashboardData> {
  const [statsJson, repoClonesJson, historyJson] = await Promise.all([
    fetchJson<StatsJson>('stats.json'),
    fetchJson<RepoClonesJson>('repo_clones.json'),
    fetchJson<HistoryJson>('history.json'),
  ]);

  return {
    owner: statsJson.owner,
    totalRepos: statsJson.totalRepos,
    totalClones: statsJson.totalClones,
    totalUniques: statsJson.totalUniques,
    totalCombined: statsJson.totalCombined,
    downloads14d: statsJson.downloads14d,
    downloadsTotal: statsJson.downloadsTotal,
    generatedAt: repoClonesJson.generatedAt,
    summaryRepos: statsJson.repos,
    repoDetails: repoClonesJson.repos,
    monthlyHistory: historyJson.monthly,
    yearlyHistory: historyJson.yearly,
    monthRange: historyJson.monthRange,
    yearRange: historyJson.yearRange,
  };
}
