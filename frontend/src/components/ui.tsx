import type { ReactNode } from 'react'

export function Field({
  id,
  label,
  hint,
  error,
  children,
}: {
  id: string
  label: string
  hint?: string
  error?: string
  children: ReactNode
}) {
  return (
    <div>
      <label htmlFor={id} className="block text-sm font-medium">
        {label}
      </label>
      {children}
      {hint && (
        <p id={`${id}-hint`} className="mt-1 text-xs text-slate-500">
          {hint}
        </p>
      )}
      {error && (
        <p id={`${id}-error`} className="mt-1 text-sm text-red-700">
          {error}
        </p>
      )}
    </div>
  )
}

export function ErrorMessage({ children }: { children: ReactNode }) {
  return (
    <p role="alert" className="rounded border border-red-200 bg-red-50 p-3 text-red-800">
      {children}
    </p>
  )
}

export function SuccessMessage({ children }: { children: ReactNode }) {
  return (
    <p
      role="status"
      className="rounded border border-green-200 bg-green-50 p-3 text-green-800"
    >
      {children}
    </p>
  )
}
