import { useEffect, useState } from 'react'
import { getHealth } from './api/client'

type HealthState =
  { kind: 'loading' } | { kind: 'healthy' } | { kind: 'error'; message: string }

export default function App() {
  const [health, setHealth] = useState<HealthState>({ kind: 'loading' })

  useEffect(() => {
    const controller = new AbortController()
    getHealth(controller.signal)
      .then(() => setHealth({ kind: 'healthy' }))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return
        setHealth({
          kind: 'error',
          message: error instanceof Error ? error.message : 'Unknown error',
        })
      })
    return () => controller.abort()
  }, [])

  return (
    <main className="mx-auto max-w-xl p-8 font-sans text-slate-900">
      <h1 className="text-2xl font-semibold">Personal Internship Finder</h1>
      <section className="mt-6 rounded-lg border border-slate-200 p-4">
        <h2 className="text-sm font-medium text-slate-500">Backend status</h2>
        <div role="status" className="mt-1">
          {health.kind === 'loading' && <p>Checking…</p>}
          {health.kind === 'healthy' && <p className="text-green-700">Healthy</p>}
          {health.kind === 'error' && (
            <>
              <p className="text-red-700">Unavailable</p>
              <p className="mt-1 text-sm text-slate-500">{health.message}</p>
            </>
          )}
        </div>
      </section>
    </main>
  )
}
