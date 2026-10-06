import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import { api } from '../api/client'
import type { Inbox, InboxItem } from '../api/schemas'
import { ErrorMessage } from '../components/ui'
import {
  formatDay,
  formatDayRelative,
  humanizeDates,
  inboxKindLabels,
} from '../lib/labels'

// ADR-020: what needs attention today. Read-only; every item links to where you act on it.
const sections: {
  key: Exclude<keyof Inbox, 'today'>
  title: string
  empty: string
  to: (item: InboxItem) => string
  all?: { label: string; to: string; exact?: boolean; always?: boolean }
}[] = [
  {
    key: 'applications',
    title: 'Applications needing attention',
    empty: 'No follow-ups due, interviews coming up, or stalled applications.',
    to: (i) => `/opportunities/${i.id}`,
  },
  {
    key: 'closing_soon',
    title: 'Closing soon',
    empty: 'No verified application deadlines in the next 14 days.',
    to: (i) => `/opportunities/${i.id}`,
    all: { label: 'All deadlines', to: '/opportunities?deadline_within=14' },
  },
  {
    key: 'new_high_fit',
    title: 'New high-fit opportunities',
    empty: 'Nothing new and high-fit in the last 7 days.',
    to: (i) => `/opportunities/${i.id}`,
    all: {
      label: 'All new this week',
      exact: false,
      to: '/opportunities?discovered_within=7&sort=recommended',
    },
  },
  {
    key: 'pending_requirement_review',
    title: 'Requirements to review',
    empty: 'No suggested requirements are waiting for review.',
    to: (i) => `/opportunities/${i.id}`,
    all: { label: 'Review requirement suggestions', to: '/requirements', always: true },
  },
  {
    key: 'program_verify_by',
    title: 'Program dates to re-check',
    empty: 'No program dates need re-checking.',
    to: (i) => `/opportunities/${i.id}`,
    all: {
      label: 'All needing date verification',
      exact: false,
      to: '/opportunities?needs_date_verification=true',
    },
  },
  {
    key: 'source_warnings',
    title: 'Source warnings',
    empty: 'All sources look healthy.',
    to: () => '/sources',
  },
]

export function InboxPage() {
  const [inbox, setInbox] = useState<Inbox | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api
      .getInbox()
      .then(setInbox)
      .catch((caught: unknown) =>
        setError(caught instanceof Error ? caught.message : 'Could not load your inbox.'),
      )
  }, [])

  if (error) return <ErrorMessage>{error}</ErrorMessage>
  if (!inbox)
    return (
      <p role="status" aria-live="polite">
        Loading…
      </p>
    )

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Inbox</h1>
      <p className="text-slate-600">
        What needs your attention as of {formatDay(inbox.today)}.
      </p>
      {sections.map((section) => {
        const { total, items } = inbox[section.key]
        return (
          <section
            key={section.key}
            aria-labelledby={`inbox-${section.key}`}
            className={`rounded-card border ${
              items.length
                ? 'space-y-2 p-4'
                : 'flex flex-wrap items-baseline gap-x-3 px-4 py-2'
            }`}
          >
            <h2
              id={`inbox-${section.key}`}
              className={items.length ? 'text-lg font-semibold' : 'font-semibold'}
            >
              {section.title} ({total})
            </h2>
            {items.length === 0 ? (
              <p className="text-sm text-slate-600" title={section.empty}>
                Nothing here
              </p>
            ) : (
              <ul className="divide-y">
                {items.map((item) => (
                  <li key={item.id} className="py-2">
                    <Link
                      to={section.to(item)}
                      className="font-medium text-blue-800 underline"
                    >
                      {item.title}
                    </Link>{' '}
                    <span className="text-slate-600">· {item.organization}</span>
                    {(item.kind || item.date) && (
                      <p className="text-sm text-slate-700">
                        {[
                          item.kind && (inboxKindLabels[item.kind] ?? item.kind),
                          item.date && formatDayRelative(item.date, inbox.today),
                        ]
                          .filter(Boolean)
                          .join(' · ')}
                      </p>
                    )}
                    <p className="text-sm text-slate-600">
                      {humanizeDates(item.reason, inbox.today)}
                    </p>
                  </li>
                ))}
              </ul>
            )}
            {section.all && total > 0 && (section.all.always || total > items.length) && (
              <p>
                <Link to={section.all.to} className="text-blue-800 underline">
                  {section.all.label}
                  {section.all.exact !== false && !section.all.always && ` (${total})`}
                </Link>
              </p>
            )}
          </section>
        )
      })}
    </div>
  )
}
