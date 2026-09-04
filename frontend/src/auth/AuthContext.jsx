import { createContext, useContext, useEffect, useState } from 'react'
import {
  getCurrentUser,
  getToken,
  listAuthProviders,
  loginUrl,
  setToken,
} from '../api'

const AuthContext = createContext(null)

export function AuthProvider({ children, onNotify }) {
  const [user, setUser] = useState(null)
  const [providers, setProviders] = useState([])
  const [ready, setReady] = useState(false)

  useEffect(() => {
    // Capture the token handed back by the OAuth callback redirect.
    const params = new URLSearchParams(window.location.search)
    const token = params.get('token')
    if (token) {
      setToken(token)
      params.delete('token')
      params.delete('auth_error')
      const qs = params.toString()
      window.history.replaceState({}, '', qs ? `?${qs}` : window.location.pathname)
    } else if (params.get('auth_error')) {
      onNotify?.('Sign-in failed. Please try again.', 'error')
      params.delete('auth_error')
      const qs = params.toString()
      window.history.replaceState({}, '', qs ? `?${qs}` : window.location.pathname)
    }

    listAuthProviders()
      .then(setProviders)
      .catch(() => setProviders([]))

    if (getToken()) {
      getCurrentUser()
        .then(setUser)
        .catch(() => {
          setToken(null)
          setUser(null)
        })
        .finally(() => setReady(true))
    } else {
      setReady(true)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const login = (provider) => {
    window.location.href = loginUrl(provider)
  }

  const logout = () => {
    setToken(null)
    setUser(null)
    onNotify?.('Signed out')
  }

  return (
    <AuthContext.Provider value={{ user, providers, ready, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within an AuthProvider')
  return ctx
}
