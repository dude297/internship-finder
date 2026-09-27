import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { Run, Source } from '../api/schemas'
import { AddSourceForm } from '../components/AddSourceForm'
import { RunSummary } from '../components/RunSummary'
import { ErrorMessage, SuccessMessage } from '../components/ui'
import { formatDateTime, sourceKindLabels } from '../lib/labels'
import { buttonClass, secondaryButtonClass } from '../lib/styles'

function message(caught: unknown, fallback: string): string {
  return caught instanceof Error ? caught.message : fallback
}

export function SourcesPage() {
  const [sources, setSources] = useState<Source[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  // The source currently syncing or saving ('all' for Sync all); one action at a time.
  const [busy, setBusy] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    api
      .listSources()
      .then((s) => active && setSources(s))
      .catch((caught: unknown) => active && setError(message(caught, 'Could not load.')))
    return () => {
      active = false
    }
  }, [])

  function withRun(run: Run) {
    setSources(
      (current) =>
        current?.map((s) => (s.id === run.source_id ? { ...s, latest_run: run } : s)) ??
        null,
    )
  }

  async function act(key: string, action: () => Promise<void>, fallback: string) {
    setBusy(key)
    setError(null)
    setNotice(null)
    try {
      await action()
    } catch (caught) {
      setError(message(caught, fallback))
    } finally {
      setBusy(null)
    }
  }

  const syncOne = (source: Source) =>
    act(
      source.id,
      async () => {
        const run = await api.syncSource(source.id)
        withRun(run)
        setNotice(`${source.display_name}: sync finished.`)
      },
      'The sync request failed.',
    )

  const syncAll = () =>
    act(
      'all',
      async () => {
        const runs = await api.syncAllSources()
        runs.forEach(withRun)
        setNotice(`Synced ${runs.length} source${runs.length === 1 ? '' : 's'}.`)
      },
      'The sync request failed.',
    )

  const toggle = (source: Source) =>
    act(
      source.id,
      async () => {
        const updated = await api.updateSource(source.id, {
          display_name: source.display_name,
          enabled: !source.enabled,
        })
        setSources(
          (current) => current?.map((s) => (s.id === updated.id ? updated : s)) ?? null,
        )
      },
      'Could not update the source.',
    )

  if (!sources && !error) return <p role="status">Loading sources…</p>

  return (
    <section className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="text-2xl font-semibold">Sources</h1>
          <p className="text-sm text-slate-600">
            Syncing runs on this computer when you ask. Nothing syncs on a schedule.
          </p>
        </div>
        <button
          type="button"
          className={buttonClass}
          onClick={syncAll}
          disabled={busy !== null || !sources?.some((s) => s.enabled)}
        >
          {busy === 'all' ? 'Syncing…' : 'Sync all'}
        </button>
      </div>
      {error && <ErrorMessage>{error}</ErrorMessage>}
      {notice && <SuccessMessage>{notice}</SuccessMessage>}
      <ul className="space-y-3">
        {sources?.map((source) => (
          <li key={source.id} className="space-y-3 rounded border border-slate-200 p-4">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div>
                <h2 className="font-medium">{source.display_name}</h2>
                <p className="text-sm text-slate-600">
                  {sourceKindLabels[source.kind]}
                  {!source.builtin && ` · ${source.identifier}`}
                  {source.region === 'eu' && ' (EU)'}
                  {!source.enabled && ' · Disabled'}
                </p>
                <p className="text-xs text-slate-500">
                  Last attempted:{' '}
                  {source.last_attempted_at
                    ? formatDateTime(source.last_attempted_at)
                    : 'never'}
                  {' · '}Last successful:{' '}
                  {source.last_success_at
                    ? formatDateTime(source.last_success_at)
                    : 'never'}
                </p>
              </div>
              <div className="flex gap-2">
                <button
                  type="button"
                  className={secondaryButtonClass}
                  onClick={() => toggle(source)}
                  disabled={busy !== null}
                >
                  {source.enabled ? 'Disable' : 'Enable'}
                </button>
                <button
                  type="button"
                  className={secondaryButtonClass}
                  onClick={() => syncOne(source)}
                  disabled={busy !== null || !source.enabled}
                  aria-label={`Sync ${source.display_name} now`}
                >
                  {busy === source.id ? 'Syncing…' : 'Sync now'}
                </button>
              </div>
            </div>
            {source.latest_run ? (
              <RunSummary run={source.latest_run} />
            ) : (
              <p className="text-sm text-slate-600">Not synced yet.</p>
            )}
          </li>
        ))}
      </ul>
      <AddSourceForm
        onAdded={(source) => {
          setSources((current) => [...(current ?? []), source])
          setNotice(`Added ${source.display_name}. Sync it to import its postings.`)
        }}
      />
      <p className="text-xs text-slate-500">
        Imported postings start with unreviewed requirements. Source details such as
        sponsorship or skill tags are kept for reference but never decide eligibility.
      </p>
    </section>
  )
}
