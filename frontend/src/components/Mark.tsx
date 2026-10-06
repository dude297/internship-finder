/** Bracketed "IF" mark. Inherits colour from the surrounding text. */
export function Mark({ className = 'h-6 w-6' }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true" className={className}>
      <path
        d="M7 4.5H4.5v15H7M17 4.5h2.5v15H17M9.5 8v8M12.5 16V8H16M12.5 12H15"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="square"
      />
    </svg>
  )
}
