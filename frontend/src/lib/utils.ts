import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function getOwnerAndRepo(): { owner: string; repo: string } {
  const hostname = window.location.hostname;
  const pathname = window.location.pathname;
  const searchParams = new URLSearchParams(window.location.search);

  if (searchParams.get('owner')) {
    return {
      owner: searchParams.get('owner')!,
      repo: searchParams.get('repo') || 'clone-sweeper',
    };
  }

  if (hostname.includes('github.io')) {
    const username = hostname.split('.')[0];
    const pathParts = pathname.split('/').filter(Boolean);
    const repo = pathParts[0] || 'clone-sweeper';
    return { owner: username, repo };
  }

  return { owner: 'HelixCipher', repo: 'clone-sweeper' };
}
