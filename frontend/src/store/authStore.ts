import { create } from 'zustand';
import { login as apiLogin, setToken, clearToken, getToken } from '../api/client';

interface AuthUser {
  email: string;
  role: 'user' | 'admin';
}

interface AuthStore {
  user: AuthUser | null;
  token: string | null;
  isAuthenticated: boolean;
  isAdmin: boolean;
  isLoading: boolean;
  error: string | null;

  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, role: string) => Promise<void>;
  logout: () => void;
  restoreSession: () => void;
  clearError: () => void;
}

function decodeJWT(token: string): { sub: string; role: string } | null {
  try {
    const payload = token.split('.')[1];
    const decoded = JSON.parse(atob(payload));
    return { sub: decoded.sub, role: decoded.role || 'user' };
  } catch {
    return null;
  }
}

export const useAuthStore = create<AuthStore>((set) => ({
  user: null,
  token: null,
  isAuthenticated: false,
  isAdmin: false,
  isLoading: false,
  error: null,

  login: async (email: string, password: string) => {
    set({ isLoading: true, error: null });
    try {
      const data = await apiLogin(email, password);
      const user: AuthUser = { email: data.email, role: data.role };
      localStorage.setItem('ss_user', JSON.stringify(user));
      set({
        user,
        token: data.access_token,
        isAuthenticated: true,
        isAdmin: user.role === 'admin',
        isLoading: false,
      });
    } catch (err: any) {
      set({ error: err.message || 'Login failed', isLoading: false });
      throw err;
    }
  },

  register: async (email: string, password: string, role: string) => {
    set({ isLoading: true, error: null });
    try {
      const res = await fetch('/api/auth/register', {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json',
          'ngrok-skip-browser-warning': '69420'
        },
        body: JSON.stringify({ email, password, role }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({ detail: 'Registration failed' }));
        throw new Error(body.detail || 'Registration failed');
      }
      const data = await res.json();
      setToken(data.access_token);
      const user: AuthUser = { email: data.email, role: data.role };
      localStorage.setItem('ss_user', JSON.stringify(user));
      set({
        user,
        token: data.access_token,
        isAuthenticated: true,
        isAdmin: user.role === 'admin',
        isLoading: false,
      });
    } catch (err: any) {
      set({ error: err.message || 'Registration failed', isLoading: false });
      throw err;
    }
  },

  logout: () => {
    clearToken();
    localStorage.removeItem('ss_user');
    set({
      user: null,
      token: null,
      isAuthenticated: false,
      isAdmin: false,
      error: null,
    });
  },

  restoreSession: () => {
    const token = getToken();
    const userStr = localStorage.getItem('ss_user');
    if (token && userStr) {
      try {
        const user: AuthUser = JSON.parse(userStr);
        // Verify token isn't expired
        const decoded = decodeJWT(token);
        if (decoded) {
          set({
            user,
            token,
            isAuthenticated: true,
            isAdmin: user.role === 'admin',
          });
          return;
        }
      } catch { /* fall through to clear */ }
    }
    // Clear stale data
    clearToken();
    localStorage.removeItem('ss_user');
  },

  clearError: () => set({ error: null }),
}));
