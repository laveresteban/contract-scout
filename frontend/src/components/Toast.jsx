import { useEffect } from 'react'

const TOAST_DURATION = 3000

function Toast({ message, type, onClose }) {
  useEffect(() => {
    const timer = setTimeout(onClose, TOAST_DURATION)
    return () => clearTimeout(timer)
  }, [onClose])

  return (
    <div className={`toast toast--${type}`} role="status">
      <span className="toast__message">{message}</span>
      <button type="button" className="toast__close" onClick={onClose} aria-label="Dismiss">
        ×
      </button>
    </div>
  )
}

function ToastContainer({ toasts, onClose }) {
  if (!toasts.length) return null

  return (
    <div className="toast-container" aria-live="polite" aria-atomic="true">
      {toasts.map((toast) => (
        <Toast key={toast.id} message={toast.message} type={toast.type} onClose={() => onClose(toast.id)} />
      ))}
    </div>
  )
}

export default ToastContainer
