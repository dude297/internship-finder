import type { FieldIssue } from '../api/client'

/** aria-* attributes linking an input to its Field hint/error. */
export function describedBy(id: string, hint?: string, error?: string) {
  return {
    'aria-invalid': error ? true : undefined,
    'aria-describedby': error ? `${id}-error` : hint ? `${id}-hint` : undefined,
  }
}

/** The backend's validation messages for one request field, joined. */
export function issueFor(issues: FieldIssue[], field: string): string | undefined {
  return (
    issues
      .filter((issue) => issue.field === field)
      .map((issue) => issue.message)
      .join(' ') || undefined
  )
}

export const orNull = (value: string) => value.trim() || null

/** "us, ca" → ["US", "CA"]; blank → null (not provided). */
export function parseCountries(value: string): string[] | null {
  const codes = value
    .split(/[\s,]+/)
    .filter(Boolean)
    .map((code) => code.toUpperCase())
  return codes.length ? codes : null
}
