import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { api, tokens } from "./api";
import type { Perm, Session, User } from "./types";

interface AuthState { user: User | null; ready: boolean; adopt(s: Session): void; signOut(): Promise<void>; can(p: Perm): boolean }
const Ctx = createContext<AuthState>({ user: null, ready: false, adopt: () => {}, signOut: async () => {}, can: () => false });
export const useAuth = () => useContext(Ctx);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);
  useEffect(() => {
    (async () => {
      if (tokens.has()) { try { setUser(await api.me()); } catch { tokens.clear(); } }
      setReady(true);
    })();
    const out = () => setUser(null);
    window.addEventListener("crm:signed-out", out);
    return () => window.removeEventListener("crm:signed-out", out);
  }, []);
  const value: AuthState = {
    user, ready,
    adopt: (s) => setUser(s.user),
    signOut: async () => { await api.logout(); setUser(null); },
    can: (p) => !!user?.perms.includes(p),
  };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function RequireAuth({ children, perm }: { children: ReactNode; perm?: Perm }) {
  const { user, ready, can } = useAuth();
  const loc = useLocation();
  if (!ready) return <p className="loading">Loading…</p>;
  if (!user) return <Navigate to="/login" state={{ from: loc.pathname }} replace />;
  if (perm && !can(perm)) return <div className="page"><h1>Not for your role</h1><p className="muted">Ask a super admin if you need this.</p></div>;
  return <>{children}</>;
}
