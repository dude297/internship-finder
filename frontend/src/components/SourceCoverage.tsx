import { useEffect, useState, type ReactNode } from 'react'
import { api, ApiError } from '../api/client'
import type { Source, SourceDiscoveryResponse } from '../api/schemas'
import { sourceKindLabels } from '../lib/labels'
import { buttonClass } from '../lib/styles'
import { ErrorMessage, SuccessMessage } from './ui'

const MAX_ADD = 25
// Recommended cap on enabled direct (Greenhouse/Lever/Ashby/...) sources; see
// docs/operations.md "Operational source cap". Re-measure a scheduled run before raising it.
const DIRECT_SOURCE_CAP = 50

function countDirectSources(sources: Source[]): number {
  return sources.filter(
    (s) =>
      s.enabled &&
      !s.builtin &&
      s.kind !== 'community_feed' &&
      s.kind !== 'curated_registry',
  ).length
}

function message(caught: unknown, fallback: string): string {
  return caught instanceof ApiError ? caught.message : fallback
}

function providerLabel(provider: string): string {
  const known = sourceKindLabels as Record<string, string>
  return known[provider] ?? provider.charAt(0).toUpperCase() + provider.slice(1)
}

/** Source Coverage (ADR-013 §2, §3, §9): metrics and board suggestions derived on read from
 * the discovery feed. Adding a suggestion only creates a disabled-by-default source; it never
 * syncs it. */
export function SourceCoverage({
  sources,
  onSourcesChanged,
  syncCount,
  children,
}: {
  sources: Source[]
  // Rendered between the coverage summary and the suggestions (the page's source health).
  children?: ReactNode
  onSourcesChanged: () => void
  // Bumped by the page after every sync, so coverage and suggestions reflect the new data.
  syncCount: number
}) {
  const [data, setData] = useState<SourceDiscoveryResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [adding, setAdding] = useState(false)
  const [addError, setAddError] = useState<string | null>(null)
  const [addSummary, setAddSummary] = useState<string | null>(null)

  function loadDiscovery() {
    return api
      .getSourceDiscovery()
      .then((response) => {
        setData(response)
        setError(null)
      })
      .catch((caught: unknown) => setError(message(caught, 'Could not load.')))
  }

  useEffect(() => {
    loadDiscovery()
    // On mount and after each sync; addSelected() reloads explicitly after a successful add.
  }, [syncCount])

  if (!data && !error) return <p role="status">Loading source coverage…</p>
  if (error)
    return (
      <>
        <ErrorMessage>{error}</ErrorMessage>
        {children}
      </>
    )
  if (!data) return null

  const { coverage, providers, suggestions } = data
  // Most feed-only postings first: those are what a direct source would replace.
  const ordered = [...suggestions].sort(
    (a, b) =>
      Number(a.already_configured) - Number(b.already_configured) ||
      b.feed_only_opportunities - a.feed_only_opportunities ||
      b.matching_opportunities - a.matching_opportunities,
  )
  const unconfigured = ordered.filter((s) => !s.already_configured)
  const directCount = countDirectSources(sources)
  const percent = (value: number | null) => (value === null ? 'n/a' : `${value}%`)
  const n = (value: number) => value.toLocaleString('en-US')
  const selectAllTarget = unconfigured.slice(0, MAX_ADD)
  const allSelected =
    selectAllTarget.length > 0 && selectAllTarget.every((s) => selected.has(s.key))

  function toggleOne(key: string) {
    setSelected((current) => {
      const next = new Set(current)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  function toggleSelectAll() {
    setSelected(allSelected ? new Set() : new Set(selectAllTarget.map((s) => s.key)))
  }

  async function addSelected() {
    setAdding(true)
    setAddError(null)
    setAddSummary(null)
    try {
      const sources = suggestions
        .filter((s) => selected.has(s.key))
        .map((s) => ({ kind: s.kind, identifier: s.identifier, region: s.region }))
      const result = await api.addDiscoverySources(sources)
      setAddSummary(
        `Added ${result.created.length}, skipped ${result.skipped.length}. ` +
          'Use Sync on the new sources (or Sync all) to fetch them.',
      )
      setSelected(new Set())
      await loadDiscovery()
      onSourcesChanged()
    } catch (caught) {
      setAddError(message(caught, 'Could not add the selected sources.'))
    } finally {
      setAdding(false)
    }
  }

  const tiles: [string, string][] = [
    ['Active opportunities', String(coverage.active_opportunities)],
    [
      'With descriptions',
      coverage.description_coverage_percent === null
        ? String(coverage.with_description)
        : `${coverage.with_description} (${coverage.description_coverage_percent}%)`,
    ],
    ['Without descriptions', String(coverage.without_description)],
    ['Direct ATS-backed', String(coverage.ats_backed)],
    ['Feed-only', String(coverage.feed_only)],
    ['Potentially enrichable', String(coverage.enrichable)],
    ['Unsupported provider count', String(coverage.unsupported)],
  ]

  const independentTiles: [string, string][] = [
    ['Direct ATS', String(coverage.direct_ats)],
    ['Direct ATS, verified fresh', String(coverage.direct_fresh)],
    ['First-party career pages', String(coverage.first_party)],
    ['Curated registry', String(coverage.curated_registry)],
    ['Manual only', String(coverage.manual_only)],
  ]

  const summary: { label: string; value: string; note: string }[] = [
    {
      label: 'Independent discovery',
      value: percent(coverage.independent_percent),
      note: `${n(coverage.independent)} of ${n(coverage.active_opportunities)} survive without the community feed`,
    },
    {
      label: 'Description coverage',
      value: percent(coverage.description_coverage_percent),
      note: `${n(coverage.with_description)} of ${n(coverage.active_opportunities)} have a description`,
    },
    {
      label: 'Feed-only postings',
      value: n(coverage.feed_only),
      note: `${n(coverage.enrichable)} could be covered by a supported board`,
    },
    {
      label: 'Direct sources enabled',
      value: `${directCount} / ${DIRECT_SOURCE_CAP}`,
      note:
        directCount >= DIRECT_SOURCE_CAP
          ? 'At the cap: re-measure a scheduled run before adding more'
          : `${DIRECT_SOURCE_CAP - directCount} below the recommended cap`,
    },
  ]

  return (
    <>
      <section className="space-y-4">
        <div className="space-y-3">
          <h2 className="text-lg font-semibold">Source Coverage</h2>
          <dl className="grid grid-cols-1 gap-3 min-[480px]:grid-cols-2 lg:grid-cols-4">
            {summary.map((item) => (
              <div key={item.label} className="rounded-card border border-slate-300 p-3">
                <dt className="text-sm font-medium text-slate-700">{item.label}</dt>
                <dd className="font-mono text-2xl font-semibold">{item.value}</dd>
                <dd className="mt-1 text-xs text-slate-600">{item.note}</dd>
              </div>
            ))}
          </dl>
          <details className="space-y-3">
            <summary className="cursor-pointer text-sm font-medium">
              All coverage numbers and provider breakdown
            </summary>
            <dl className="grid grid-cols-2 gap-3 sm:grid-cols-5">
              {independentTiles.map(([label, value]) => (
                <div key={label} className="rounded border border-slate-200 p-3">
                  <dt className="text-xs text-slate-500">{label}</dt>
                  <dd className="text-lg font-semibold">{value}</dd>
                </div>
              ))}
            </dl>
            <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              {tiles.map(([label, value]) => (
                <div key={label} className="rounded border border-slate-200 p-3">
                  <dt className="text-xs text-slate-500">{label}</dt>
                  <dd className="text-lg font-semibold">{value}</dd>
                </div>
              ))}
            </dl>
            {providers.length > 0 && (
              <div
                className="overflow-x-auto"
                role="region"
                aria-label="Coverage by ATS (scrollable)"
                tabIndex={0}
              >
                <table className="w-full text-left text-sm">
                  <caption className="sr-only">Provider breakdown</caption>
                  <thead>
                    <tr>
                      <th scope="col" className="py-1">
                        Provider
                      </th>
                      <th scope="col" className="py-1">
                        Supported
                      </th>
                      <th scope="col" className="py-1">
                        Feed-only opportunities
                      </th>
                      <th scope="col" className="py-1">
                        Enrichable
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {providers.map((p) => (
                      <tr key={p.provider} className="border-t border-slate-100">
                        <td className="py-1">{providerLabel(p.provider)}</td>
                        <td className="py-1">{p.supported ? 'Yes' : 'No'}</td>
                        <td className="py-1">{p.opportunities}</td>
                        <td className="py-1">{p.enrichable}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </details>
        </div>
      </section>

      {children}

      <section className="space-y-3">
        <>
          <h2 className="text-lg font-semibold">Suggested Sources</h2>
          <p className="text-sm text-slate-600">
            Boards the discovery feed already links to, most feed-only postings first.
            Activate from the top: each one replaces feed-only postings with direct ones.
          </p>
        </>
        <>
          {addError && <ErrorMessage>{addError}</ErrorMessage>}
          {addSummary && <SuccessMessage>{addSummary}</SuccessMessage>}
          {suggestions.length === 0 ? (
            <p className="text-sm text-slate-600">
              No supported sources found in the discovery feed. Sync the feed first, or
              add a board by link below.
            </p>
          ) : (
            <>
              {unconfigured.length === 0 && (
                <p className="text-sm text-slate-600">
                  Every suggested board is already configured. Browse Verified Direct
                  Sources for more.
                </p>
              )}
              <div
                className="overflow-x-auto"
                role="region"
                aria-label="Suggested boards (scrollable)"
                tabIndex={0}
              >
                <table className="w-full text-left text-sm">
                  <caption className="sr-only">Suggested sources</caption>
                  <thead>
                    <tr>
                      <th scope="col" className="py-1">
                        <input
                          type="checkbox"
                          aria-label="Select all unconfigured suggestions"
                          checked={allSelected}
                          disabled={selectAllTarget.length === 0}
                          onChange={toggleSelectAll}
                        />
                      </th>
                      <th scope="col" className="py-1">
                        Provider
                      </th>
                      <th scope="col" className="py-1">
                        Organization
                      </th>
                      <th scope="col" className="py-1">
                        Board/site
                      </th>
                      <th scope="col" className="py-1">
                        Feed opportunities matched
                      </th>
                      <th scope="col" className="py-1">
                        Feed-only
                      </th>
                      <th scope="col" className="py-1">
                        Already configured
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {ordered.map((s) => (
                      <tr key={s.key} className="border-t border-slate-100">
                        <td className="py-1">
                          <input
                            type="checkbox"
                            checked={!s.already_configured && selected.has(s.key)}
                            disabled={s.already_configured}
                            onChange={() => toggleOne(s.key)}
                            aria-label={`Select ${s.key}`}
                          />
                        </td>
                        <td className="py-1">
                          {sourceKindLabels[s.kind]}
                          {s.kind === 'lever' && s.region === 'eu' && (
                            <span className="ml-1 rounded bg-slate-100 px-1 text-xs">
                              EU
                            </span>
                          )}
                        </td>
                        <td className="py-1" title={s.sample_titles.join(', ')}>
                          {s.suggested_display_name}
                          {s.display_name_ambiguous && (
                            <span className="ml-1 text-xs text-slate-500">
                              (ambiguous name)
                            </span>
                          )}
                          {s.sample_titles.length > 0 && (
                            <p className="text-xs text-slate-500">
                              {s.sample_titles.join(', ')}
                            </p>
                          )}
                        </td>
                        <td className="py-1 font-mono">{s.key}</td>
                        <td className="py-1">{s.matching_opportunities}</td>
                        <td className="py-1">{s.feed_only_opportunities}</td>
                        <td className="py-1">
                          {s.already_configured ? 'Configured' : ''}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="flex flex-wrap items-center gap-3">
                <button
                  type="button"
                  className={buttonClass}
                  onClick={addSelected}
                  disabled={adding || selected.size === 0 || selected.size > MAX_ADD}
                >
                  {adding ? 'Adding…' : 'Add selected sources'}
                </button>
                <p className="text-sm text-slate-600">
                  {selected.size} selected (max {MAX_ADD})
                </p>
              </div>
            </>
          )}
        </>
      </section>
    </>
  )
}
