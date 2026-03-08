import type { DashboardData, RepoSummary, RepoDetails, HistoryEntry } from './types';

const RAW_BASE = 'https://raw.githubusercontent.com/HelixCipher/clone-sweeper/main';

async function fetchSvgText(filename: string): Promise<string> {
  const res = await fetch(`${RAW_BASE}/${filename}`);
  if (!res.ok) throw new Error(`Failed to fetch ${filename}`);
  return res.text();
}

function parseNumber(s: string): number {
  const n = parseInt(s.replace(/,/g, ''), 10);
  return isNaN(n) ? 0 : n;
}

function parseSummaryCard(svg: string): {
  owner: string;
  totalRepos: number;
  totalClones: number;
  totalUniques: number;
  totalCombined: number;
  downloads14d: number;
  downloadsTotal: number;
  repos: RepoSummary[];
} {
  // Parse header
  const titleMatch = svg.match(/GitHub repos — (.+?)<\/text>/);
  const owner = titleMatch?.[1] ?? 'Unknown';

  const metaMatch = svg.match(/Repos:\s*(\d+)\s*·\s*Clones:\s*(\d+)\s*·\s*Uniques:\s*(\d+)\s*·\s*Combined:\s*(\d+)\s*·\s*Downloads \(14d\):\s*(\d+)\s*·\s*Downloads \(total\):\s*(\d+)/);
  const totalRepos = metaMatch ? parseNumber(metaMatch[1]) : 0;
  const totalClones = metaMatch ? parseNumber(metaMatch[2]) : 0;
  const totalUniques = metaMatch ? parseNumber(metaMatch[3]) : 0;
  const totalCombined = metaMatch ? parseNumber(metaMatch[4]) : 0;
  const downloads14d = metaMatch ? parseNumber(metaMatch[5]) : 0;
  const downloadsTotal = metaMatch ? parseNumber(metaMatch[6]) : 0;

  // Parse repos - find label + three count values
  const repos: RepoSummary[] = [];
  const labelRegex = /class="label card">(.+?)<\/text>/g;
  const countRegex = /class="count(?:-small)? card">(\d+)<\/text>/g;

  const labels: string[] = [];
  let m: RegExpExecArray | null;
  while ((m = labelRegex.exec(svg)) !== null) labels.push(m[1]);

  const counts: number[] = [];
  while ((m = countRegex.exec(svg)) !== null) counts.push(parseNumber(m[1]));

  for (let i = 0; i < labels.length; i++) {
    const ci = i * 3;
    repos.push({
      name: labels[i],
      clones: counts[ci] ?? 0,
      uniques: counts[ci + 1] ?? 0,
      combined: counts[ci + 2] ?? 0,
    });
  }

  return { owner, totalRepos, totalClones, totalUniques, totalCombined, downloads14d, downloadsTotal, repos };
}

function parseRepoTable(svg: string): { generatedAt: string; repos: RepoDetails[] } {
  const genMatch = svg.match(/Generated:\s*([^\s·]+)/);
  const generatedAt = genMatch?.[1] ?? '';

  const repos: RepoDetails[] = [];

  // Parse rows - each row has a rect followed by td text elements
  // Split by row rects
  const rowRegex = /class="row-(?:even|odd)"[^>]*>[\s\S]*?(?=class="row-(?:even|odd)"|<line|<\/svg)/g;
  
  // Simpler: extract all td values in order
  const tdRegex = /class="td card">(.+?)<\/text>/g;
  const mutedRegex = /class="muted card">-<\/text>/g;
  
  // Get all text content in order
  const allText: string[] = [];
  const lineRegex = /(?:class="td card"|class="muted card")>([^<]+)<\/text>/g;
  let match: RegExpExecArray | null;
  
  while ((match = lineRegex.exec(svg)) !== null) {
    allText.push(match[1].trim());
  }

  // Each repo has: name, desc (1-2 lines merged), language, stars, forks, watchers, issues, lastPush, clones, uniques, dl14d, dlTotal
  // This is complex due to multi-line descriptions. Let's use a different approach.
  // Find each row block between row-even/row-odd markers
  const rowBlocks = svg.split(/class="row-(?:even|odd)"/);
  
  for (let i = 1; i < rowBlocks.length; i++) {
    const block = rowBlocks[i];
    const texts: string[] = [];
    const textRegex = /class="(?:td|muted) card">([^<]+)<\/text>/g;
    let tm: RegExpExecArray | null;
    while ((tm = textRegex.exec(block)) !== null) {
      texts.push(tm[1].trim());
    }
    
    if (texts.length < 10) continue;

    // Determine if description is multi-line
    // Fields: name, [desc lines...], language, stars, forks, watchers, issues, lastPush, clones, uniques, dl14d, dlTotal
    // We know the last 8 fields. So desc = everything between name and language
    const name = texts[0];
    const tail = texts.slice(-8); // lastPush, clones, uniques, dl14d, dlTotal  ... wait, 8 from end
    // Actually: stars, forks, watchers, issues, lastPush, clones, uniques, dl14d, dlTotal = 9 from end
    // Plus language = 10 from end
    const descParts = texts.slice(1, texts.length - 10);
    const description = descParts.length > 0 ? descParts.join(' ') : '-';
    const language = texts[texts.length - 10] || '-';

    repos.push({
      name,
      description,
      language,
      stars: parseNumber(texts[texts.length - 9]),
      forks: parseNumber(texts[texts.length - 8]),
      watchers: parseNumber(texts[texts.length - 7]),
      openIssues: parseNumber(texts[texts.length - 6]),
      lastPush: texts[texts.length - 5],
      clones14d: texts[texts.length - 4] === 'N/A' ? null : parseNumber(texts[texts.length - 4]),
      uniques14d: texts[texts.length - 3] === 'N/A' ? null : parseNumber(texts[texts.length - 3]),
      downloads14d: texts[texts.length - 2] === 'N/A' ? null : parseNumber(texts[texts.length - 2]),
      downloadsTotal: texts[texts.length - 1] === 'N/A' ? null : parseNumber(texts[texts.length - 1]),
    });
  }

  return { generatedAt, repos };
}

function parseHistory(svg: string): {
  monthly: HistoryEntry[];
  yearly: HistoryEntry[];
  monthRange: string;
  yearRange: string;
} {
  // Split into monthly and yearly sections
  const sections = svg.split('<!-- Bottom: Yearly chart -->');
  const monthlySection = sections[0] || '';
  const yearlySection = sections[1] || '';

  function parseSection(section: string): HistoryEntry[] {
    const entries: HistoryEntry[] = [];
    // Find each polyline + text pair
    const lineRegex = /<polyline[^>]*style="stroke:([^"]+)"[^>]*>[\s\S]*?<text[^>]*style="fill:[^"]*"[^>]*>\s*([\s\S]*?)<\/text>/g;
    let m: RegExpExecArray | null;
    while ((m = lineRegex.exec(section)) !== null) {
      const color = m[1];
      const label = m[2].trim();
      const repoMatch = label.match(/^(.+?)\s*—\s*(clones|uniques|downloads)\s*\(latest\s*(\d+)\)/);
      if (repoMatch) {
        entries.push({
          repo: repoMatch[1],
          metric: repoMatch[2] as 'clones' | 'uniques' | 'downloads',
          latestValue: parseNumber(repoMatch[3]),
          color,
          points: [],
        });
      }
    }
    return entries;
  }

  const monthRangeMatch = monthlySection.match(/months:\s*\d+\s*\(([^)]+)\)/);
  const yearRangeMatch = yearlySection.match(/years:\s*\d+\s*\(([^)]+)\)/);

  return {
    monthly: parseSection(monthlySection),
    yearly: parseSection(yearlySection),
    monthRange: monthRangeMatch?.[1] ?? '',
    yearRange: yearRangeMatch?.[1] ?? '',
  };
}

export async function fetchDashboardData(): Promise<DashboardData> {
  const [statsSvg, tableSvg, historySvg] = await Promise.all([
    fetchSvgText('stats.svg'),
    fetchSvgText('REPO_CLONES.svg'),
    fetchSvgText('history.svg'),
  ]);

  const summary = parseSummaryCard(statsSvg);
  const table = parseRepoTable(tableSvg);
  const history = parseHistory(historySvg);

  return {
    owner: summary.owner,
    totalRepos: summary.totalRepos,
    totalClones: summary.totalClones,
    totalUniques: summary.totalUniques,
    totalCombined: summary.totalCombined,
    downloads14d: summary.downloads14d,
    downloadsTotal: summary.downloadsTotal,
    generatedAt: table.generatedAt,
    summaryRepos: summary.repos,
    repoDetails: table.repos,
    monthlyHistory: history.monthly,
    yearlyHistory: history.yearly,
    monthRange: history.monthRange,
    yearRange: history.yearRange,
  };
}
