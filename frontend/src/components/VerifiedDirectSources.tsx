import { useEffect, useState } from 'react'
import { api, ApiError } from '../api/client'
import type { CatalogEntry } from '../api/schemas'
import { formatDate, sourceKindLabels } from '../lib/labels'
import { buttonClass } from '../lib/styles'
import { ErrorMessage, SuccessMessage } from './ui'

const MAX_ADD = 25

function message(caught: unknown, fallback: string): string {
  return caught instanceof ApiError ? caught.message : fallback
}

/** Verified Direct Sources (M8.1): a curated catalog of company boards. Adding only creates a
 * disabled-by-default source; it never syncs it. */
export function VerifiedDirectSources({
  onSourcesChanged,
  reloadKey,
}: {
  onSourcesChanged: () => void
  // Bumped by the page when sources change elsewhere, so already-configured stays current.
  reloadKey: number
}) {
  const [entries, setEntries] = useState<CatalogEntry[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [tag, setTag] = useState('')
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [adding, setAdding] = useState(false)
  const [addError, setAddError] = useState<string | null>(null)
  const [addSummary, setAddSummary] = useState<string | null>(null)

  function load() {
    return api
      .getSourceCatalog()
      .then((r) => {
        setEntries(r.entries)
        setError(null)
      })
      .catch((caught: unknown) => setError(message(caught, 'Could not load.')))
  }

  useEffect(() => {
    load()
  }, [reloadKey])

  if (!entries && !error) return <p role="status">Loading verified direct sources…</p>
  if (error) return <ErrorMessage>{error}</ErrorMessage>
  if (!entries) return null

  const tags = [...new Set(entries.flatMap((e) => e.tags))].sort()
  const visible = entries.filter((e) => !tag || e.tags.includes(tag))

  function toggleOne(key: string) {
    setSelected((current) => {
      const next = new Set(current)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  async function addSelected() {
    setAdding(true)
    setAddError(null)
    setAddSummary(null)
    try {
      const sources = (entries ?? [])
        .filter((e) => selected.has(e.key))
        .map((e) => ({ kind: e.kind, identifier: e.identifier, region: e.region }))
      const result = await api.addCatalogSources(sources)
      setAddSummary(
        `Added ${result.created.length}, skipped ${result.skipped.length}. ` +
          'Use Sync on the new sources (or Sync all) to fetch them.',
      )
      setSelected(new Set())
      onSourcesChanged() // reloads sources and (via reloadKey) this catalog
    } catch (caught) {
      setAddError(message(caught, 'Could not add the selected sources.'))
    } finally {
      setAdding(false)
    }
  }

  return (
    <section className="space-y-3">
      <h2 className="text-lg font-semibold">Verified Direct Sources</h2>
      <p className="text-sm text-slate-600">
        Company job boards checked by hand. Adding one creates the source; sync it to
        import its postings.
      </p>
      {addError && <ErrorMessage>{addError}</ErrorMessage>}
      {addSummary && <SuccessMessage>{addSummary}</SuccessMessage>}
      {entries.length === 0 ? (
        <p className="text-sm text-slate-600">No verified direct sources available.</p>
      ) : (
        <>
          <div>
            <label htmlFor="catalog-tag" className="block text-sm font-medium">
              Filter by tag
            </label>
            <select
              id="catalog-tag"
              value={tag}
              onChange={(e) => setTag(e.target.value)}
              className="rounded border border-slate-300 px-2 py-1"
            >
              <option value="">All tags</option>
              {tags.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </div>
          <table className="w-full text-left text-sm">
            <caption className="sr-only">Verified direct sources</caption>
            <thead>
              <tr>
                <th scope="col" className="py-1">
                  <span className="sr-only">Select</span>
                </th>
                <th scope="col" className="py-1">
                  Organization
                </th>
                <th scope="col" className="py-1">
                  Provider
                </th>
                <th scope="col" className="py-1">
                  Tags
                </th>
                <th scope="col" className="py-1">
                  Verified
                </th>
                <th scope="col" className="py-1">
                  Links
                </th>
                <th scope="col" className="py-1">
                  Already configured
                </th>
              </tr>
            </thead>
            <tbody>
              {visible.map((e) => (
                <tr key={e.key} className="border-t border-slate-100">
                  <td className="py-1">
                    <input
                      type="checkbox"
                      checked={!e.already_configured && selected.has(e.key)}
                      disabled={e.already_configured}
                      onChange={() => toggleOne(e.key)}
                      aria-label={`Select ${e.key}`}
                    />
                  </td>
                  <td className="py-1" title={e.evidence}>
                    {e.organization}
                    <p className="text-xs text-slate-500">{e.evidence}</p>
                  </td>
                  <td className="py-1">
                    {sourceKindLabels[e.kind]}
                    {e.region === 'eu' && (
                      <span className="ml-1 rounded bg-slate-100 px-1 text-xs">EU</span>
                    )}
                  </td>
                  <td className="py-1">{e.tags.join(', ')}</td>
                  <td className="py-1">{formatDate(e.verified_at)}</td>
                  <td className="py-1">
                    <a
                      href={e.careers_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-blue-800 underline"
                    >
                      Careers page
                    </a>
                  </td>
                  <td className="py-1">{e.already_configured ? 'Configured' : ''}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              className={buttonClass}
              onClick={addSelected}
              disabled={adding || selected.size === 0 || selected.size > MAX_ADD}
            >
              {adding ? 'Adding…' : `Add selected (${selected.size})`}
            </button>
            <p className="text-sm text-slate-600">max {MAX_ADD} at a time</p>
          </div>
        </>
      )}
    </section>
  )
}
