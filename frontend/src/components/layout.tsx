"use client";

import { twMerge } from "tailwind-merge";
import { Backdrop } from "./brand";

/** Page-width content column. */
export function Container({ children, className }: { children: React.ReactNode; className?: string }) {
  return <div className={twMerge("mx-auto w-full max-w-[1680px] px-6 lg:px-10", className)}>{children}</div>;
}

/** Hero band that opens every page: eyebrow, large display title, context and actions. */
export function PageHero({
  eyebrow,
  title,
  description,
  actions,
  children,
}: {
  eyebrow?: React.ReactNode;
  title: React.ReactNode;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  children?: React.ReactNode;
}) {
  return (
    <section className="relative overflow-hidden border-b border-line">
      <Backdrop />
      <Container className="relative pb-10 pt-12 lg:pt-16">
        <div className="flex flex-wrap items-end justify-between gap-8">
          <div className="min-w-0 max-w-4xl">
            {eyebrow && <div className="eyebrow rise">{eyebrow}</div>}
            <h1
              className="rise mt-4 font-display text-4xl font-light uppercase leading-[0.95] tracking-[0.05em] text-ink sm:text-5xl xl:text-6xl"
              style={{ animationDelay: "0.06s" }}
            >
              {title}
            </h1>
            {description && (
              <div className="rise mt-4 max-w-2xl text-[15px] leading-relaxed text-ink-2" style={{ animationDelay: "0.12s" }}>
                {description}
              </div>
            )}
          </div>
          {actions && <div className="flex flex-wrap items-center gap-3">{actions}</div>}
        </div>
        {children && <div className="mt-10">{children}</div>}
      </Container>
    </section>
  );
}

export interface FigureItem {
  label: string;
  value: string;
  unit?: string;
  sub?: string;
}

/** Spec-sheet strip: the few numbers that define the design, set large and light. */
export function Figures({ items }: { items: FigureItem[] }) {
  return (
    <div className="grid grid-cols-2 gap-x-8 gap-y-6 md:grid-cols-4">
      {items.map((f) => (
        <div key={f.label} className="border-t border-line-strong pt-4">
          <div className="eyebrow">{f.label}</div>
          <div className="mt-2 flex items-baseline gap-1.5">
            <span className="text-[40px] font-extralight leading-none tracking-tight text-ink">{f.value}</span>
            {f.unit && <span className="display text-sm text-ink-2">{f.unit}</span>}
          </div>
          {f.sub && <div className="mt-1.5 text-xs text-ink-3">{f.sub}</div>}
        </div>
      ))}
    </div>
  );
}

/** Tab bar that stays under the header while scrolling. */
export function StickyTabs({ children }: { children: React.ReactNode }) {
  return (
    <div className="sticky top-16 z-20 border-b border-line bg-page/85 backdrop-blur-xl [&_nav]:border-b-0">
      <Container>{children}</Container>
    </div>
  );
}
