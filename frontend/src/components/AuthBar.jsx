import { useAuth } from '../auth/AuthContext'

function AuthBar() {
  const { user, providers, login, logout } = useAuth()

  if (user) {
    return (
      <div className="auth-bar">
        {user.avatar_url && (
          <img className="auth-avatar" src={user.avatar_url} alt="" width="28" height="28" />
        )}
        <span className="auth-name">{user.name || user.email}</span>
        <button type="button" className="auth-button" onClick={logout}>
          Sign out
        </button>
      </div>
    )
  }

  if (!providers.length) {
    // No OAuth providers configured on the backend.
    return null
  }

  return (
    <div className="auth-bar">
      {providers.map((p) => (
        <button
          key={p.id}
          type="button"
          className="auth-button auth-button--login"
          onClick={() => login(p.id)}
        >
          Sign in with {p.label}
        </button>
      ))}
    </div>
  )
}

export default AuthBar
