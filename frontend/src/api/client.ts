import { z } from 'zod'

// ponytail: localhost fallback only in dev; production builds must set VITE_API_BASE_URL.
const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ??
  (import.meta.env.DEV ? 'http://localhost:8000' : undefined)

export const healthResponseSchema = z.object({ status: z.literal('ok') })
export type HealthResponse = z.infer<typeof healthResponseSchema>

export async function getHealth(signal?: AbortSignal): Promise<HealthResponse> {
  if (!API_BASE_URL) throw new Error('VITE_API_BASE_URL is not configured')

  const response = await fetch(`${API_BASE_URL}/api/health`, { signal })
  if (!response.ok) throw new Error(`Health check failed (HTTP ${response.status})`)

  const body: unknown = await response.json().catch(() => undefined)
  const parsed = healthResponseSchema.safeParse(body)
  if (!parsed.success) throw new Error('Backend returned an unexpected health response')
  return parsed.data
}
