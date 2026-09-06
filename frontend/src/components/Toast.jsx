function Toast({ message, type, onClose }) {
  return (
    <div className={`toast toast--${type}`}>
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
