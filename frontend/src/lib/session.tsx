"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api, ApiError, getToken, setToken } from "./api";
import type { Material, Meta } from "./types";

interface User {
  id: string;
  email: string;
  name: string;
}

interface Health {
  status: string;
  version: string;
  compute: { mode: string; gpu_available: boolean; gpu_device: string | null };
  research_available: boolean;
  auth_disabled: boolean;
}

interface Session {
  ready: boolean;
  user: User | null;
  health: Health | null;
  meta: Meta | null;
  materials: Material[];
  error: string | null;
  signIn: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, name: string) => Promise<void>;
  signOut: () => Promise<void>;
  reloadMaterials: () => Promise<void>;
}

const Ctx = createContext<Session | null>(null);

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const [ready, setReady] = useState(false);
  const [user, setUser] = useState<User | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [materials, setMaterials] = useState<Material[]>([]);
  const [error, setError] = useState<string | null>(null);

  const reloadMaterials = useCallback(async () => {
    setMaterials(await api<Material[]>("/api/v1/materials"));
  }, []);

  const loadUser = useCallback(async () => {
    try {
      const me = await api<User>("/api/v1/auth/me");
      setUser(me);
      await reloadMaterials();
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) {
        setToken(null);
        setUser(null);
      } else throw e;
    }
  }, [reloadMaterials]);

  useEffect(() => {
    (async () => {
      try {
        const [h, m] = await Promise.all([api<Health>("/api/health"), api<Meta>("/api/v1/meta")]);
        setHealth(h);
        setMeta(m);
        if (h.auth_disabled || getToken()) await loadUser();
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        setReady(true);
      }
    })();
  }, [loadUser]);

  const signIn = async (email: string, password: string) => {
    const r = await api<{ token: string; user: User }>("/api/v1/auth/login", { method: "POST", json: { email, password } });
    setToken(r.token);
    await loadUser();
  };
  const register = async (email: string, password: string, name: string) => {
    const r = await api<{ token: string; user: User }>("/api/v1/auth/register", {
      method: "POST",
      json: { email, password, name },
    });
    setToken(r.token);
    await loadUser();
  };
  const signOut = async () => {
    try {
      await api("/api/v1/auth/logout", { method: "POST" });
    } catch {
      /* already signed out */
    }
    setToken(null);
    setUser(null);
  };

  return (
    <Ctx.Provider value={{ ready, user, health, meta, materials, error, signIn, register, signOut, reloadMaterials }}>
      {children}
    </Ctx.Provider>
  );
}

export function useSession(): Session {
  const s = useContext(Ctx);
  if (!s) throw new Error("useSession must be used inside SessionProvider");
  return s;
}
