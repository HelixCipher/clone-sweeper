import { Moon, Sun } from 'lucide-react';
import { useTheme } from 'next-themes';

export function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  const isDark = theme === 'dark';

  return (
    <button
      onClick={() => setTheme(isDark ? 'light' : 'dark')}
      className={`relative inline-flex items-center h-7 w-12 rounded-full transition-all duration-300 ${
        isDark
          ? 'bg-[hsl(200,80%,15%)] shadow-[0_0_10px_hsl(200,100%,55%,0.3)]'
          : 'bg-gray-300 shadow-[0_0_10px_hsl(220,20%,10%,0.2)]'
      }`}
      aria-label="Toggle theme"
    >
      <span
        className={`inline-flex items-center justify-center w-5 h-5 rounded-full transition-all duration-300 transform ${
          isDark
            ? 'translate-x-6 bg-[hsl(200,100%,55%)] shadow-[0_0_8px_hsl(200,100%,55%,0.6)]'
            : 'translate-x-1 bg-[hsl(220,20%,15%)] shadow-[0_0_8px_hsl(220,20%,10%,0.4)]'
        }`}
      >
        {isDark ? (
          <Moon className="w-3 h-3 text-[hsl(220,20%,6%)]" />
        ) : (
          <Sun className="w-3 h-3 text-white" />
        )}
      </span>
    </button>
  );
}
