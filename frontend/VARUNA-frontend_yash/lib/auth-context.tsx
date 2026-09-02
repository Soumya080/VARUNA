'use client'

/**
 * STEP 7: the frontend half of the login path. Session state (a real
 * signed JWT from `POST /v1/auth/login`, plus the role/username the
 * backend returned with it) is stored in `localStorage` only for this
 * browser's own convenience across reloads — the backend never trusts
 * anything read back out of it; every subsequent request still carries
 * the raw token and is re-verified server-side (`apps/api/security.py`).
 * Nothing here can grant a permission the backend would not have granted
 * from the same token directly.
 */
import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { login as apiLogin, setAuthToken } from './api'

interface Session {
  token: string
  username: string
  role: string
  expiresAt: number // ms epoch, client-side hint only — not a trust boundary
}

interface AuthContextValue {
  session: Session | null
  isAuthenticated: boolean
  isExpired: boolean
  login: (username: string, password: string) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

const STORAGE_KEY = 'varuna_auth_session'

function loadStoredSession(): Session | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as Session
    if (!parsed.token || !parsed.expiresAt) return null
    return parsed
  } catch {
    return null
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null)
  const [hydrated, setHydrated] = useState(false)

  useEffect(() => {
    const stored = loadStoredSession()
    if (stored) {
      setSession(stored)
      setAuthToken(stored.token)
    }
    setHydrated(true)
  }, [])

  async function login(username: string, password: string) {
    const result = await apiLogin(username, password)
    const next: Session = {
      token: result.access_token,
      username,
      role: result.role,
      expiresAt: Date.now() + result.expires_in_seconds * 1000,
    }
    setSession(next)
    setAuthToken(next.token)
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
    } catch {
      // private browsing / storage disabled — session still works for this tab
    }
  }

  function logout() {
    setSession(null)
    setAuthToken(null)
    try {
      localStorage.removeItem(STORAGE_KEY)
    } catch {
      // ignore
    }
  }

  const isExpired = session ? Date.now() >= session.expiresAt : false

  return (
    <AuthContext.Provider
      value={{
        session: hydrated ? session : null,
        isAuthenticated: hydrated && session !== null && !isExpired,
        isExpired,
        login,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
