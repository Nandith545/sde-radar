import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import * as api from "../api";

interface AuthContextValue {
  user: api.User | null;
  loading: boolean;
  login: (email: string, password: string, remember?: boolean) => Promise<void>;
  register: (payload: { email: string; password: string; full_name: string; target_city: string; target_titles: string }) => Promise<void>;
  logout: () => void;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<api.User | null>(null);
  const [loading, setLoading] = useState(true);

  const refreshUser = useCallback(async () => {
    if (!api.getToken()) {
      setUser(null);
      return;
    }
    try {
      const me = await api.fetchMe();
      setUser(me);
    } catch {
      api.clearToken();
      setUser(null);
    }
  }, []);

  useEffect(() => {
    refreshUser().finally(() => setLoading(false));
  }, [refreshUser]);

  const login = async (email: string, password: string, remember = true) => {
    const { access_token } = await api.login(email, password);
    api.setToken(access_token, remember);
    await refreshUser();
  };

  const doRegister = async (payload: { email: string; password: string; full_name: string; target_city: string; target_titles: string }) => {
    const { access_token } = await api.register(payload);
    api.setToken(access_token);
    await refreshUser();
  };

  const logout = () => {
    api.clearToken();
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, loading, login, register: doRegister, logout, refreshUser }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
