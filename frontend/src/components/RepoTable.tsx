import { useState, useMemo } from 'react';
import { Link } from 'react-router-dom';
import type { RepoDetails } from '@/lib/types';
import { ArrowUpDown, Search, LayoutGrid, Table as TableIcon, Star, GitFork, Copy, Users, Clock } from 'lucide-react';
import { useIsMobile } from '@/hooks/use-mobile';

interface RepoTableProps {
  repos: RepoDetails[];
}

type SortKey = keyof RepoDetails;

export function RepoTable({ repos }: RepoTableProps) {
  const isMobile = useIsMobile();
  const [search, setSearch] = useState('');
  const [sortKey, setSortKey] = useState<SortKey>('clones14d');
  const [sortAsc, setSortAsc] = useState(false);
  const [viewMode, setViewMode] = useState<'table' | 'cards'>(isMobile ? 'cards' : 'table');

  const columns: { key: SortKey; label: string; align?: 'right' }[] = [
    { key: 'name', label: 'Repository' },
    { key: 'language', label: 'Language' },
    { key: 'stars', label: 'Stars', align: 'right' },
    { key: 'forks', label: 'Forks', align: 'right' },
    { key: 'openIssues', label: 'Issues', align: 'right' },
    { key: 'clones14d', label: 'Clones', align: 'right' },
    { key: 'uniques14d', label: 'Uniques', align: 'right' },
    { key: 'lastPush', label: 'Last Push' },
  ];

  const sortOptions: { key: SortKey; label: string }[] = [
    { key: 'clones14d', label: 'Clones' },
    { key: 'uniques14d', label: 'Uniques' },
    { key: 'stars', label: 'Stars' },
    { key: 'forks', label: 'Forks' },
    { key: 'name', label: 'Name' },
    { key: 'lastPush', label: 'Last Push' },
  ];

  const handleSort = (key: SortKey) => {
    if (sortKey === key) setSortAsc(!sortAsc);
    else { setSortKey(key); setSortAsc(false); }
  };

  const filtered = useMemo(() => {
    let list = repos.filter(r =>
      r.name.toLowerCase().includes(search.toLowerCase()) ||
      r.language.toLowerCase().includes(search.toLowerCase())
    );
    list.sort((a, b) => {
      const av = a[sortKey] ?? -1;
      const bv = b[sortKey] ?? -1;
      if (av < bv) return sortAsc ? -1 : 1;
      if (av > bv) return sortAsc ? 1 : -1;
      return 0;
    });
    return list;
  }, [repos, search, sortKey, sortAsc]);

  const formatValue = (key: SortKey, val: unknown) => {
    if (val === null || val === undefined) return <span className="text-muted-foreground">N/A</span>;
    if (key === 'lastPush' && typeof val === 'string') {
      const d = new Date(val);
      return isNaN(d.getTime()) ? val : d.toLocaleDateString();
    }
    if (typeof val === 'number') return val.toLocaleString();
    return String(val);
  };

  const langColors: Record<string, string> = {
    Python: 'hsl(var(--chart-blue))',
    'Jupyter Notebook': 'hsl(var(--chart-orange))',
    JavaScript: 'hsl(var(--chart-amber))',
    TypeScript: 'hsl(var(--chart-blue))',
    HTML: 'hsl(var(--chart-rose))',
    CSS: 'hsl(var(--chart-purple))',
    Shell: 'hsl(var(--chart-green))',
  };

  return (
    <div className="glass-card animate-slide-up" style={{ animationDelay: '300ms' }}>
      <div className="p-5 pb-3 flex items-center justify-between gap-3 flex-wrap">
        <h2 className="text-lg font-semibold text-foreground">All Repositories</h2>
        <div className="flex items-center gap-2 flex-1 justify-end">
          {viewMode === 'cards' && (
            <select
              value={sortKey}
              onChange={e => { setSortKey(e.target.value as SortKey); setSortAsc(false); }}
              className="px-2 py-1.5 bg-muted border border-border rounded-md text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
            >
              {sortOptions.map(o => (
                <option key={o.key} value={o.key}>Sort: {o.label}</option>
              ))}
            </select>
          )}
          <div className="relative max-w-xs flex-1 min-w-[120px]">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <input
              type="text"
              placeholder="Filter repos..."
              value={search}
              onChange={e => setSearch(e.target.value)}
              className="w-full pl-9 pr-3 py-2 bg-muted border border-border rounded-md text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary"
            />
          </div>
          <button
            onClick={() => setViewMode(viewMode === 'table' ? 'cards' : 'table')}
            className="p-2 rounded-md bg-muted border border-border text-muted-foreground hover:text-foreground transition-colors"
            title={viewMode === 'table' ? 'Switch to card view' : 'Switch to table view'}
          >
            {viewMode === 'table' ? <LayoutGrid className="w-4 h-4" /> : <TableIcon className="w-4 h-4" />}
          </button>
        </div>
      </div>

      {viewMode === 'table' ? (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border">
                {columns.map(col => (
                  <th
                    key={col.key}
                    onClick={() => handleSort(col.key)}
                    className={`px-4 py-3 text-xs font-medium text-muted-foreground cursor-pointer hover:text-foreground transition-colors whitespace-nowrap ${
                      col.align === 'right' ? 'text-right' : 'text-left'
                    }`}
                  >
                    <span className="inline-flex items-center gap-1">
                      {col.label}
                      <ArrowUpDown className={`w-3 h-3 ${sortKey === col.key ? 'text-primary' : ''}`} />
                    </span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtered.map((repo) => (
                <tr
                  key={repo.name}
                  className="border-b border-border/30 hover:bg-muted/50 transition-colors"
                >
                  {columns.map(col => (
                    <td
                      key={col.key}
                      className={`px-4 py-3 font-mono text-xs whitespace-nowrap ${
                        col.align === 'right' ? 'text-right' : 'text-left'
                      } ${col.key === 'name' ? 'font-medium text-foreground' : 'text-secondary-foreground'}`}
                    >
                      {col.key === 'name' ? (
                        <Link
                          to={`/repo/${encodeURIComponent(repo.name)}`}
                          className="text-primary hover:underline"
                        >
                          {repo.name}
                        </Link>
                      ) : col.key === 'language' ? (
                        <span className="inline-flex items-center gap-1.5">
                          <span
                            className="w-2.5 h-2.5 rounded-full"
                            style={{ background: langColors[String(repo.language)] || 'hsl(var(--muted-foreground))' }}
                          />
                          {repo.language || '-'}
                        </span>
                      ) : (
                        formatValue(col.key, repo[col.key])
                      )}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="p-4 grid grid-cols-1 sm:grid-cols-2 gap-3">
          {filtered.map((repo) => (
            <div
              key={repo.name}
              className="rounded-lg border border-border bg-muted/30 p-4 hover:bg-muted/50 transition-colors"
            >
              <div className="flex items-center justify-between gap-2 mb-3">
                <Link
                  to={`/repo/${encodeURIComponent(repo.name)}`}
                  className="text-sm font-semibold text-primary hover:underline truncate"
                >
                  {repo.name}
                </Link>
                {repo.language && (
                  <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground shrink-0">
                    <span
                      className="w-2 h-2 rounded-full"
                      style={{ background: langColors[repo.language] || 'hsl(var(--muted-foreground))' }}
                    />
                    {repo.language}
                  </span>
                )}
              </div>
              <div className="grid grid-cols-2 gap-2 text-xs font-mono">
                <div className="flex items-center gap-1.5 text-secondary-foreground">
                  <Star className="w-3.5 h-3.5 text-muted-foreground" />
                  <span>{(repo.stars ?? 0).toLocaleString()}</span>
                </div>
                <div className="flex items-center gap-1.5 text-secondary-foreground">
                  <GitFork className="w-3.5 h-3.5 text-muted-foreground" />
                  <span>{(repo.forks ?? 0).toLocaleString()}</span>
                </div>
                <div className="flex items-center gap-1.5 text-secondary-foreground">
                  <Copy className="w-3.5 h-3.5 text-muted-foreground" />
                  <span>{(repo.clones14d ?? 0).toLocaleString()}</span>
                </div>
                <div className="flex items-center gap-1.5 text-secondary-foreground">
                  <Users className="w-3.5 h-3.5 text-muted-foreground" />
                  <span>{(repo.uniques14d ?? 0).toLocaleString()}</span>
                </div>
              </div>
              {repo.lastPush && (
                <div className="mt-3 pt-2 border-t border-border/30 flex items-center gap-1.5 text-xs text-muted-foreground">
                  <Clock className="w-3 h-3" />
                  {new Date(repo.lastPush).toLocaleDateString()}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      <div className="p-3 text-center text-xs text-muted-foreground">
        {filtered.length} of {repos.length} repositories
      </div>
    </div>
  );
}
