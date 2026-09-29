import clsx from "clsx";
import { useId } from "react";

/** Wordmark: a precise mark (a tachometer arc) with widely spaced lettering. */
export function Wordmark({ className, subtitle = true }: { className?: string; subtitle?: boolean }) {
  return (
    <span className={clsx("inline-flex items-center gap-3", className)}>
      <svg viewBox="0 0 32 32" className="size-7" aria-hidden>
        <circle cx="16" cy="16" r="14.5" fill="none" stroke="currentColor" strokeWidth="1" opacity="0.35" />
        <path d="M6.2 21.5 A11 11 0 1 1 25.8 21.5" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
        <path d="M16 16 L23.2 9.4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
        <circle cx="16" cy="16" r="1.8" fill="currentColor" />
      </svg>
      <span className="flex flex-col leading-none">
        <span className="font-display text-[17px] font-semibold uppercase tracking-[0.38em]">AutoEng</span>
        {subtitle && <span className="mt-1 font-display text-[9px] font-medium uppercase tracking-[0.5em] text-ink-3">Studio</span>}
      </span>
    </span>
  );
}

/**
 * Original line-art of a generic two-door sports coupe (not modelled on any real car).
 * Draws itself once, then a soft light sweep passes over it.
 */
export function CoupeLineArt({ className, animate = true }: { className?: string; animate?: boolean }) {
  const id = useId().replace(/:/g, "");
  const draw = animate ? "draw-path" : undefined;
  const body =
    "M58 300 C52 276 66 258 118 248 L352 222 C414 212 468 182 540 160 C604 140 700 133 786 141 " +
    "C866 150 934 178 1004 199 L1088 213 C1122 220 1130 252 1120 292 L1044 300 A88 88 0 0 0 868 300 " +
    "L334 300 A88 88 0 0 0 158 300 Z";
  const glass = "M478 206 C536 176 606 160 704 157 L812 162 C852 168 876 182 892 198 L760 204 Z";
  return (
    <svg viewBox="0 0 1180 400" className={className} role="img" aria-label="Line drawing of a sports coupe">
      <defs>
        <linearGradient id={`metal-${id}`} x1="0" x2="1" y1="0" y2="0">
          <stop offset="0" stopColor="currentColor" stopOpacity="0.25" />
          <stop offset="0.45" stopColor="currentColor" stopOpacity="0.95" />
          <stop offset="1" stopColor="currentColor" stopOpacity="0.3" />
        </linearGradient>
        <linearGradient id={`sweep-${id}`} x1="0" x2="1">
          <stop offset="0" stopColor="white" stopOpacity="0" />
          <stop offset="0.5" stopColor="white" stopOpacity="0.9" />
          <stop offset="1" stopColor="white" stopOpacity="0" />
        </linearGradient>
        <mask id={`mask-${id}`}>
          <path d={body} fill="none" stroke="white" strokeWidth="3" />
          <path d={glass} fill="none" stroke="white" strokeWidth="2" />
        </mask>
      </defs>
      <g fill="none" stroke={`url(#metal-${id})`} strokeLinecap="round" strokeLinejoin="round">
        <path d={body} strokeWidth="1.6" pathLength={1} className={draw} />
        <path d={glass} strokeWidth="1.2" pathLength={1} className={draw} />
        {/* Shoulder line, door cut, sill */}
        <path d="M150 252 C420 236 760 222 1082 220" strokeWidth="1" opacity="0.7" pathLength={1} className={draw} />
        <path d="M560 208 C566 240 572 268 574 296" strokeWidth="0.9" opacity="0.5" pathLength={1} className={draw} />
        <path d="M352 286 L840 286" strokeWidth="0.9" opacity="0.45" pathLength={1} className={draw} />
        {/* Lights */}
        <path d="M84 258 L150 250" strokeWidth="2.2" opacity="0.9" pathLength={1} className={draw} />
        <path d="M1066 222 L1112 226" strokeWidth="2.2" opacity="0.9" pathLength={1} className={draw} />
        {/* Wheels */}
        {[246, 956].map((cx) => (
          <g key={cx}>
            <circle cx={cx} cy={300} r={70} strokeWidth="1.4" pathLength={1} className={draw} />
            <circle cx={cx} cy={300} r={48} strokeWidth="0.9" opacity="0.6" pathLength={1} className={draw} />
            <circle cx={cx} cy={300} r={9} strokeWidth="1" opacity="0.7" />
            {Array.from({ length: 10 }).map((_, i) => {
              const a = (i / 10) * Math.PI * 2;
              return (
                <line
                  key={i}
                  x1={cx + Math.cos(a) * 12}
                  y1={300 + Math.sin(a) * 12}
                  x2={cx + Math.cos(a) * 46}
                  y2={300 + Math.sin(a) * 46}
                  strokeWidth="0.8"
                  opacity="0.45"
                />
              );
            })}
          </g>
        ))}
        {/* Ground shadow line */}
        <path d="M120 372 L1080 372" strokeWidth="1" opacity="0.18" />
      </g>
      {animate && (
        <g mask={`url(#mask-${id})`}>
          <rect x="0" y="0" width="260" height="400" fill={`url(#sweep-${id})`} className="light-sweep" />
        </g>
      )}
    </svg>
  );
}

/** Subtle technical backdrop: fine grid fading into the page, with a soft top glow. */
export function Backdrop({ className }: { className?: string }) {
  return (
    <div aria-hidden className={clsx("pointer-events-none absolute inset-0 overflow-hidden", className)}>
      <div
        className="absolute inset-0 opacity-[0.35]"
        style={{
          backgroundImage:
            "linear-gradient(var(--border) 1px, transparent 1px), linear-gradient(90deg, var(--border) 1px, transparent 1px)",
          backgroundSize: "56px 56px",
          maskImage: "radial-gradient(ellipse 70% 60% at 50% 40%, black 30%, transparent 80%)",
        }}
      />
      <div
        className="absolute -top-1/3 left-1/2 h-[80%] w-[90%] -translate-x-1/2 rounded-full blur-3xl"
        style={{ background: "radial-gradient(closest-side, var(--hero-glow), transparent)" }}
      />
    </div>
  );
}

/** Original line-art of an inline-four engine with a turbocharger. */
export function EngineLineArt({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 320 200" className={className} role="img" aria-label="Line drawing of an engine">
      <g fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round">
        <path d="M40 150 L40 90 L60 70 L230 70 L250 90 L250 150 Z" strokeWidth="1.2" opacity="0.9" />
        <path d="M60 70 L60 52 L230 52 L230 70" strokeWidth="1" opacity="0.7" />
        {[82, 124, 166, 208].map((x) => (
          <g key={x}>
            <rect x={x - 14} y={84} width="28" height="44" rx="2" strokeWidth="0.9" opacity="0.6" />
            <line x1={x} y1={128} x2={x} y2={150} strokeWidth="0.9" opacity="0.5" />
          </g>
        ))}
        <path d="M40 150 C70 172 220 172 250 150" strokeWidth="1" opacity="0.6" />
        <circle cx="276" cy="92" r="22" strokeWidth="1.2" />
        <circle cx="276" cy="92" r="9" strokeWidth="0.9" opacity="0.7" />
        <path d="M250 100 L262 104" strokeWidth="1" />
        <path d="M276 70 C276 40 240 34 210 40" strokeWidth="1" opacity="0.7" />
      </g>
    </svg>
  );
}
