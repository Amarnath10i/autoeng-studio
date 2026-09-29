"use client";

import { ArrowRight } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Backdrop, CoupeLineArt, Wordmark } from "@/components/brand";
import { Button, ErrorNote, Field, Input, useAsync } from "@/components/ui";
import { useSession } from "@/lib/session";

const PILLARS = [
  ["Design", "Components, materials and whole vehicles"],
  ["Simulate", "Physics with stated uncertainty, on your GPU"],
  ["Validate", "Calibrated against real dyno and road data"],
];

export default function LoginPage() {
  const { user, signIn, register } = useSession();
  const router = useRouter();
  const [mode, setMode] = useState<"signin" | "register">("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const { busy, error, run } = useAsync();

  useEffect(() => {
    if (user) router.replace("/");
  }, [user, router]);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    run(() => (mode === "signin" ? signIn(email, password) : register(email, password, name)));
  };

  return (
    <div className="grid min-h-screen lg:grid-cols-[1.35fr_1fr]">
      <section className="relative flex flex-col justify-between overflow-hidden border-r border-line px-8 py-10 lg:px-16 lg:py-14">
        <Backdrop />
        <Wordmark className="relative text-ink" />
        <div className="relative">
          <div className="eyebrow rise">Automotive engineering platform</div>
          <h1 className="rise mt-5 max-w-2xl font-display text-5xl font-light uppercase leading-[0.95] tracking-[0.04em] text-ink sm:text-6xl xl:text-7xl" style={{ animationDelay: "0.1s" }}>
            Engineer
            <br />
            every detail.
          </h1>
          <p className="rise mt-6 max-w-lg text-[15px] leading-relaxed text-ink-2" style={{ animationDelay: "0.2s" }}>
            From a single connecting rod to a complete automobile: design it, simulate it, find what fails first, and prove
            it against real measurements.
          </p>
          <CoupeLineArt className="relative mt-10 w-full max-w-3xl text-ink" />
        </div>
        <div className="relative grid gap-6 sm:grid-cols-3">
          {PILLARS.map(([t, d]) => (
            <div key={t} className="border-t border-line-strong pt-4">
              <div className="display text-sm text-ink">{t}</div>
              <div className="mt-1 text-xs leading-relaxed text-ink-3">{d}</div>
            </div>
          ))}
        </div>
      </section>

      <section className="flex items-center justify-center bg-surface px-8 py-14">
        <form onSubmit={submit} className="w-full max-w-sm space-y-6">
          <div>
            <div className="eyebrow">{mode === "signin" ? "Welcome back" : "Get started"}</div>
            <h2 className="display mt-3 text-3xl font-light tracking-[0.08em]">
              {mode === "signin" ? "Sign in" : "Create account"}
            </h2>
          </div>
          {mode === "register" && (
            <Field label="Name">
              <Input value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" className="h-11" />
            </Field>
          )}
          <Field label="Email">
            <Input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" className="h-11" />
          </Field>
          <Field label="Password" hint={mode === "register" ? "At least 8 characters" : undefined}>
            <Input
              type="password"
              required
              minLength={mode === "register" ? 8 : undefined}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete={mode === "register" ? "new-password" : "current-password"}
              className="h-11"
            />
          </Field>
          <ErrorNote error={error} />
          <Button type="submit" variant="primary" size="lg" loading={busy} className="w-full">
            {mode === "signin" ? "Sign in" : "Create account"} <ArrowRight className="size-4" aria-hidden />
          </Button>
          <div className="hairline" />
          <p className="text-center text-sm text-ink-2">
            {mode === "signin" ? "New here?" : "Already have an account?"}{" "}
            <button
              type="button"
              onClick={() => setMode(mode === "signin" ? "register" : "signin")}
              className="font-display font-medium uppercase tracking-[0.16em] text-ink underline-offset-4 hover:underline"
            >
              {mode === "signin" ? "Create an account" : "Sign in"}
            </button>
          </p>
        </form>
      </section>
    </div>
  );
}
