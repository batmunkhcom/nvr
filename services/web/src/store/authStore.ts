import { create } from "zustand";

interface User {
  id: string;
  username: string;
  role: string;
  email?: string;
}

interface AuthStore {
  user: User | null;
  accessToken: string | null;
  isAuthenticated: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
}

function decodeTokenPayload(token: string): User | null {
  try {
    const parts = token.split(".");
    if (parts.length !== 3) return null;
    const payload = JSON.parse(atob(parts[1]));
    if (payload.sub && payload.username && payload.role) {
      return { id: payload.sub, username: payload.username, role: payload.role };
    }
    return null;
  } catch {
    return null;
  }
}

function getInitialState() {
  const token = localStorage.getItem("access_token");
  if (token) {
    const user = decodeTokenPayload(token);
    if (user) {
      return { user, accessToken: token, isAuthenticated: true };
    }
  }
  return { user: null, accessToken: null, isAuthenticated: false };
}

export const useAuthStore = create<AuthStore>((set) => ({
  ...getInitialState(),

  login: async (username: string, password: string) => {
    const res = await fetch("/api/v1/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    if (!res.ok) {
      const errBody = await res.json().catch(() => ({}));
      throw new Error(errBody?.error?.message || `Login failed (${res.status})`);
    }
    const json = await res.json();
    const { access_token, refresh_token, user } = json;
    localStorage.setItem("access_token", access_token);
    localStorage.setItem("refresh_token", refresh_token);
    set({ user, accessToken: access_token, isAuthenticated: true });
  },

  logout: () => {
    localStorage.removeItem("access_token");
    localStorage.removeItem("refresh_token");
    set({ user: null, accessToken: null, isAuthenticated: false });
  },
}));
