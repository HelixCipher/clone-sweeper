import { useState, useEffect } from 'react';

const SplashScreen = ({ onComplete }: { onComplete: () => void }) => {
  const [phase, setPhase] = useState<'enter' | 'hold' | 'exit'>('enter');
  const [dots, setDots] = useState<{ x: number; y: number; delay: number; size: number }[]>([]);

  useEffect(() => {
    const generated = Array.from({ length: 18 }, () => {
      const angle = Math.random() * Math.PI * 2;
      const r = 20 + Math.random() * 70;
      return {
        x: 50 + r * Math.cos(angle),
        y: 50 + r * Math.sin(angle),
        delay: 0.5 + Math.random() * 1.5,
        size: 2 + Math.random() * 3,
      };
    });
    setDots(generated);
  }, []);

  useEffect(() => {
    const holdTimer = setTimeout(() => setPhase('hold'), 100);
    const exitTimer = setTimeout(() => setPhase('exit'), 2800);
    const doneTimer = setTimeout(onComplete, 3300);
    return () => {
      clearTimeout(holdTimer);
      clearTimeout(exitTimer);
      clearTimeout(doneTimer);
    };
  }, [onComplete]);

  // Use the same blue as --primary dark: 200 100% 55%
  const blue = '200 100% 55%';
  const blueDim = '200 80% 30%';

  return (
    <div
      className={`fixed inset-0 z-50 flex items-center justify-center bg-[hsl(220,20%,4%)] ${
        phase === 'exit' ? 'animate-splash-exit' : ''
      }`}
    >
      <div className="relative flex flex-col items-center gap-8">
        <div className="relative w-52 h-52 md:w-64 md:h-64">
          {/* Outer ring */}
          <div
            className="absolute inset-0 rounded-full border-2 animate-fade-up"
            style={{ borderColor: `hsl(${blueDim} / 0.6)`, animationDelay: '0.1s', opacity: 0 }}
          />
          {/* Middle ring */}
          <div
            className="absolute inset-[20%] rounded-full border animate-fade-up"
            style={{ borderColor: `hsl(${blueDim} / 0.4)`, animationDelay: '0.2s', opacity: 0 }}
          />
          {/* Inner ring */}
          <div
            className="absolute inset-[40%] rounded-full border animate-fade-up"
            style={{ borderColor: `hsl(${blueDim} / 0.3)`, animationDelay: '0.3s', opacity: 0 }}
          />
          {/* Crosshairs */}
          <div
            className="absolute top-0 bottom-0 left-1/2 w-px animate-fade-up"
            style={{ background: `hsl(${blueDim} / 0.3)`, animationDelay: '0.15s', opacity: 0 }}
          />
          <div
            className="absolute left-0 right-0 top-1/2 h-px animate-fade-up"
            style={{ background: `hsl(${blueDim} / 0.3)`, animationDelay: '0.15s', opacity: 0 }}
          />
          {/* Center dot */}
          <div
            className="absolute top-1/2 left-1/2 w-2 h-2 -translate-x-1/2 -translate-y-1/2 rounded-full animate-fade-up"
            style={{
              background: `hsl(${blue})`,
              boxShadow: `0 0 8px hsl(${blue} / 0.8)`,
              animationDelay: '0.4s',
              opacity: 0,
            }}
          />

          {/* Sweep line */}
          <div
            className="absolute inset-0 animate-radar-sweep"
            style={{ animationDelay: '0.5s', opacity: 0 }}
          >
            <div
              className="absolute top-1/2 left-1/2 w-1/2 h-0.5 origin-left"
              style={{
                background: `linear-gradient(to right, hsl(${blue}), transparent)`,
                transform: 'translateY(-50%)',
              }}
            />
            <div
              className="absolute top-1/2 left-1/2 w-1/2 h-1/2 origin-top-left"
              style={{
                background: `conic-gradient(from -30deg, hsl(${blue} / 0.15), transparent 40deg)`,
                borderRadius: '0 100% 0 0',
                transform: 'translateY(-50%) rotate(-15deg)',
              }}
            />
          </div>

          {/* Data dots */}
          {dots.map((dot, i) => (
            <div
              key={i}
              className="absolute rounded-full animate-radar-dot"
              style={{
                left: `${dot.x}%`,
                top: `${dot.y}%`,
                width: dot.size,
                height: dot.size,
                background: `hsl(${blue})`,
                boxShadow: `0 0 ${dot.size * 2}px hsl(${blue} / 0.6)`,
                animationDelay: `${dot.delay}s`,
                opacity: 0,
              }}
            />
          ))}

          {/* Radar glow */}
          <div
            className="absolute inset-0 rounded-full"
            style={{
              background: `radial-gradient(circle, hsl(${blueDim} / 0.1) 0%, transparent 70%)`,
            }}
          />
        </div>

        {/* Title */}
        <div className="flex flex-col items-center gap-3">
          <h1
            className="text-4xl md:text-5xl font-bold tracking-tight animate-fade-up"
            style={{
              fontFamily: "'JetBrains Mono', monospace",
              animationDelay: '0.8s',
              opacity: 0,
              color: `hsl(${blue})`,
              textShadow: `0 0 20px hsl(${blue} / 0.5)`,
            }}
          >
            Clone Sweeper
          </h1>
          <p
            className="text-xs md:text-sm font-mono animate-fade-up tracking-[0.3em] uppercase"
            style={{
              animationDelay: '1.1s',
              opacity: 0,
              color: `hsl(${blueDim})`,
            }}
          >
            GitHub Clone Analytics
          </p>

          {/* Scanning bar */}
          <div
            className="w-48 h-0.5 rounded-full overflow-hidden mt-3 animate-fade-up"
            style={{
              background: `hsl(${blueDim} / 0.3)`,
              animationDelay: '1.3s',
              opacity: 0,
            }}
          >
            <div
              className="h-full rounded-full animate-radar-scan-bar"
              style={{
                background: `hsl(${blue})`,
                boxShadow: `0 0 8px hsl(${blue} / 0.6)`,
              }}
            />
          </div>
        </div>
      </div>
    </div>
  );
};

export default SplashScreen;
