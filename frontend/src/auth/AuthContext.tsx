import type { AxiosInstance } from "axios";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { useNavigate } from "react-router-dom";
import { api, setAuthToken, setUnauthorizedHandler } from "../api/client";
import type { LoginRequest, RegisterRequest, TokenResponse, User } from "../api/types";
import { getStoredToken, setStoredToken } from "./storage";

interface AuthContextValue {
  user: User | null;
  /** True until a stored token has been validated (or found absent) against GET /auth/me. */
  isLoading: boolean;
  login: (credentials: LoginRequest) => Promise<void>;
  register: (data: RegisterRequest) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({
  children,
  client = api,
}: {
  children: ReactNode;
  client?: AxiosInstance;
}) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const navigate = useNavigate();

  const logout = useCallback(() => {
    setStoredToken(null);
    setAuthToken(null);
    setUser(null);
  }, []);

  useEffect(() => {
    let cancelled = false;
    const token = getStoredToken();
    if (!token) {
      setIsLoading(false);
      return;
    }
    setAuthToken(token);
    client
      .get<User>("/auth/me")
      .then((res) => {
        if (!cancelled) setUser(res.data);
      })
      .catch(() => {
        if (!cancelled) {
          setStoredToken(null);
          setAuthToken(null);
          setUser(null);
        }
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [client]);

  useEffect(() => {
    const handleUnauthorized = () => {
      logout();
      navigate("/login", { replace: true });
    };
    setUnauthorizedHandler(handleUnauthorized);
    return () => setUnauthorizedHandler(null);
  }, [logout, navigate]);

  const login = useCallback(
    async (credentials: LoginRequest) => {
      const res = await client.post<TokenResponse>("/auth/login", credentials);
      setStoredToken(res.data.access_token);
      setAuthToken(res.data.access_token);
      setUser(res.data.user);
    },
    [client],
  );

  const register = useCallback(
    async (data: RegisterRequest) => {
      await client.post("/auth/register", data);
    },
    [client],
  );

  const value = useMemo<AuthContextValue>(
    () => ({ user, isLoading, login, register, logout }),
    [user, isLoading, login, register, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within an AuthProvider");
  return ctx;
}
