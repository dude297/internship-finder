import { useEffect, useState, type ReactNode } from 'react'
import { Link } from 'react-router'
import { api } from '../api/client'
import {
  applicationStatuses,
  type ApplicationStatus,
  type Dashboard,
  type InboxItem,
} from '../api/schemas'
import { ErrorMessage } from '../components/ui'
import { localToday } from '../lib/deadlines'
import {
  ageText,
  barHeights,
  trendSummary,
  formatDays,
  formatPercent,
  formatRate,
  greeting,
  shares,
} from '../lib/dashboard'
import { applicationStatusLabels } from '../lib/labels'

// ADR-025: the overview. Restrained on purpose: type and thin dividers, not a wall of cards.
// Dashboard = overview, Inbox = action queue, Applications = workspace.

const groupLabel = 'text-xs font-medium uppercase tracking-wide text-slate-500'
const sectionTitle = 'text-lg font-semibold'

const kindLabels: Record<string, string> = {
  follow_up_overdue: 'Overdue',
  follow_up_due: 'Due',
  interview: 'Interview',
  stale: 'No update',
}

function Section({
  id,
  title,
  children,
  aside,
}: {
  id: string
  title: string
  children: ReactNode
  aside?: ReactNode
}) {
  return (
    <section aria-labelledby={id} className="space-y-3 p-4">
      <div className="flex items-baseline justify-between gap-2">
        <h2 id={id} className={sectionTitle}>
          {title}
        </h2>
        {aside}
      </div>
      {children}
    </section>
  )
}

function ItemList({ items, kinds }: { items: InboxItem[]; kinds?: boolean }) {
  return (
    <ul className="divide-y divide-slate-100">
      {items.slice(0, 6).map((item) => (
        <li key={`${item.id}-${item.kind ?? ''}`} className="py-1.5">
          {kinds && item.kind && (
            <span className="mr-2 rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-700">
              {kindLabels[item.kind] ?? item.kind}
            </span>
          )}
          <Link
            to={`/opportunities/${item.id}`}
            className="font-medium text-blue-800 underline"
          >
            {item.title}
          </Link>{' '}
          <span className="text-slate-600">· {item.organization}</span>
          <p className="text-sm text-slate-700">{item.reason}</p>
        </li>
      ))}
    </ul>
  )
}

function Stat({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex justify-between gap-4 py-0.5 text-sm">
      <dt className="text-slate-600">{label}</dt>
      <dd className="font-medium tabular-nums">{value}</dd>
    </div>
  )
}

function ActionRequired({ d }: { d: Dashboard }) {
  const { applications, closing_soon, pending_requirement_review } = d.actions
  const groups = [
    { title: 'Applications', section: applications, kinds: true },
    { title: 'Closing soon', section: closing_soon, kinds: false },
    {
      title: 'Suggested requirements awaiting your review',
      section: pending_requirement_review,
      kinds: false,
    },
  ]
  return (
    <Section
      id="dash-actions"
      title={`Action required (${d.actions.total})`}
      aside={
        <Link to="/inbox" className="text-sm text-blue-800 underline">
          Open the Inbox
        </Link>
      }
    >
      {d.actions.total === 0 ? (
        <p className="text-slate-600">Nothing needs your attention right now.</p>
      ) : (
        <div className="space-y-4">
          {groups
            .filter((g) => g.section.items.length > 0)
            .map((g) => (
              <div key={g.title}>
                <h3 className={groupLabel}>
                  {g.title} ({g.section.total})
                </h3>
                <ItemList items={g.section.items} kinds={g.kinds} />
              </div>
            ))}
        </div>
      )}
    </Section>
  )
}

function Pipeline({ d }: { d: Dashboard }) {
  const counts = applicationStatuses.map((s) => d.pipeline[s] ?? 0)
  const total = counts.reduce((a, b) => a + b, 0)
  const widths = shares(counts)
  const tone: Record<ApplicationStatus, string> = {
    saved: 'bg-slate-300',
    applying: 'bg-slate-400',
    applied: 'bg-sky-400',
    interview: 'bg-indigo-400',
    offer: 'bg-emerald-400',
    accepted: 'bg-emerald-600',
    rejected: 'bg-rose-300',
    withdrawn: 'bg-slate-200',
  }
  return (
    <Section
      id="dash-pipeline"
      title="Application pipeline"
      aside={
        <Link to="/applications" className="text-sm text-blue-800 underline">
          Open Applications
        </Link>
      }
    >
      {total === 0 ? (
        <p className="text-slate-600">
          No applications tracked yet. Track an opportunity to see it here.
        </p>
      ) : (
        <>
          <p className="text-sm text-slate-600">
            {total} tracked, by current status. Stages aren't a fixed order.
          </p>
          <div
            aria-hidden="true"
            className="hidden h-3 overflow-hidden rounded-md md:flex"
          >
            {applicationStatuses.map(
              (s, i) =>
                counts[i] > 0 && (
                  <div key={s} className={tone[s]} style={{ width: `${widths[i]}%` }} />
                ),
            )}
          </div>
          <ul className="grid grid-cols-2 gap-x-6 gap-y-1 text-sm sm:grid-cols-4">
            {applicationStatuses.map((s, i) => (
              <li key={s} className="flex items-center gap-2">
                <span
                  aria-hidden="true"
                  className={`hidden h-2 w-2 rounded-sm md:inline-block ${tone[s]}`}
                />
                <Link to={`/applications?stage=${s}`} className="underline">
                  {applicationStatusLabels[s]}
                </Link>
                <span className="tabular-nums text-slate-600">{counts[i]}</span>
              </li>
            ))}
          </ul>
        </>
      )}
    </Section>
  )
}

function HighFit({ d }: { d: Dashboard }) {
  return (
    <Section id="dash-highfit" title="New high-fit">
      {d.high_fit_new.items.length === 0 ? (
        <p className="text-slate-600">Nothing new and high-fit in the last 7 days.</p>
      ) : (
        <ul className="divide-y divide-slate-100">
          {d.high_fit_new.items.map((o) => (
            <li key={o.id} className="py-1.5">
              <Link
                to={`/opportunities/${o.id}`}
                className="font-medium text-blue-800 underline"
              >
                {o.title}
              </Link>{' '}
              <span className="text-slate-600">· {o.organization}</span>
              <p className="text-sm text-slate-700">
                Fit {o.fit_score} ·{' '}
                {o.eligibility_status === 'eligible' ? 'Eligible' : 'Needs verification'}
              </p>
            </li>
          ))}
        </ul>
      )}
      {d.high_fit_new.total > d.high_fit_new.items.length && (
        <Link
          to="/opportunities?discovered_within=7&sort=recommended"
          className="text-sm text-blue-800 underline"
        >
          All new this week ({d.high_fit_new.total})
        </Link>
      )}
    </Section>
  )
}

const timelineLabels = {
  deadline: 'Deadline',
  follow_up: 'Follow-up',
  interview: 'Interview',
  verify_by: 'Verify dates',
} as const

function Upcoming({ d }: { d: Dashboard }) {
  return (
    <Section id="dash-upcoming" title="Upcoming">
      {d.upcoming.length === 0 ? (
        <p className="text-slate-600">Nothing scheduled in the next two weeks.</p>
      ) : (
        <ul className="divide-y divide-slate-100">
          {d.upcoming.map((t, i) => (
            <li key={`${t.kind}-${t.id}-${i}`} className="py-1.5 text-sm">
              <span className="mr-2 inline-block w-24 text-slate-600">
                {t.at ? new Date(t.at).toLocaleString() : t.date}
              </span>
              <span className="mr-2 rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-700">
                {timelineLabels[t.kind]}
              </span>
              <Link to={`/opportunities/${t.id}`} className="text-blue-800 underline">
                {t.title}
              </Link>{' '}
              <span className="text-slate-600">· {t.organization}</span>
            </li>
          ))}
        </ul>
      )}
    </Section>
  )
}

function NewSupply({ h }: { h: Dashboard['discovery'] }) {
  const heights = barHeights(h.weekly_new.map((w) => w.count))
  const barW = 14
  return (
    <div className="space-y-2 border-t border-slate-100 pt-2">
      <p className={groupLabel}>New supply</p>
      <dl>
        <Stat label="New today (open)" value={h.new_today} />
        <Stat label="New this week (open)" value={h.new_this_week} />
        <Stat label="Independent of the feed" value={h.new_this_week_independent} />
        <Stat label="Closing soon" value={h.closing_soon} />
      </dl>
      {h.new_this_week_by_provider.length > 0 && (
        <table className="w-full text-sm">
          <caption className="text-left text-xs text-slate-500">
            New this week by source type (an opportunity with several sources counts in
            each)
          </caption>
          <tbody>
            {h.new_this_week_by_provider.map((p) => (
              <tr key={p.provider}>
                <td className="text-slate-600">{p.provider.replace(/_/g, ' ')}</td>
                <td className="text-right font-medium tabular-nums">{p.count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <div>
        <svg
          role="img"
          aria-label={trendSummary(h.weekly_new)}
          viewBox={`0 0 ${h.weekly_new.length * (barW + 4)} 40`}
          className="h-10 w-full max-w-xs text-blue-700"
        >
          {h.weekly_new.map((w, i) => {
            const height = Math.max(heights[i] * 0.4, w.count > 0 ? 1 : 0)
            return (
              <rect
                key={w.week_start}
                x={i * (barW + 4)}
                y={40 - height}
                width={barW}
                height={height}
                fill="currentColor"
              >
                <title>{`Week of ${w.week_start}: ${w.count}`}</title>
              </rect>
            )
          })}
        </svg>
        <p className="text-xs text-slate-500">
          New opportunities per week over the last {h.weekly_new.length} weeks, counted
          when first seen (including ones that have since closed). Hidden opportunities
          are excluded.
        </p>
      </div>
    </div>
  )
}

function DiscoveryHealth({ d }: { d: Dashboard }) {
  const h = d.discovery
  return (
    <Section
      id="dash-discovery"
      title="Discovery health"
      aside={
        <Link to="/sources" className="text-sm text-blue-800 underline">
          Sources
        </Link>
      }
    >
      <dl>
        <Stat label="Open opportunities" value={h.open_opportunities} />
        <Stat label="With a direct source" value={h.direct_sources} />
        <Stat
          label="Independent of the feed"
          value={formatPercent(h.independent_percent)}
        />
        <Stat label="With a description" value={formatPercent(h.description_percent)} />
        <Stat label="Feed-only" value={h.feed_only} />
        <Stat
          label="Last successful sync"
          value={ageText(h.latest_successful_sync_at, new Date()) ?? 'Never'}
        />
        <Stat label="Sources needing attention" value={h.sources_needing_attention} />
      </dl>
      <NewSupply h={h} />
    </Section>
  )
}

function RequirementHealth({ d }: { d: Dashboard }) {
  const r = d.requirements
  return (
    <Section
      id="dash-requirements"
      title="Requirement health"
      aside={
        <Link to="/requirements" className="text-sm text-blue-800 underline">
          Review requirements
        </Link>
      }
    >
      <p className="text-sm text-slate-600">
        Suggestions the extractor made from posting text. Only the ones you accept count.
      </p>
      <dl>
        <Stat label="Awaiting your review" value={r.awaiting_review} />
        <Stat label="Accepted" value={r.accepted} />
        <Stat label="Rejected" value={r.rejected} />
      </dl>
    </Section>
  )
}

function Funnel({ d }: { d: Dashboard }) {
  const f = d.funnel
  const steps: [string, number][] = [
    ['Applied', f.applied],
    ['Interviewed', f.interviewed],
    ['Offered', f.offered],
    ['Accepted', f.accepted],
  ]
  return (
    <Section id="dash-funnel" title="Outcomes">
      <ol className="flex flex-wrap gap-x-8 gap-y-2">
        {steps.map(([label, n]) => (
          <li key={label}>
            <span className="block text-2xl font-semibold tabular-nums">{n}</span>
            <span className="text-sm text-slate-600">{label}</span>
          </li>
        ))}
      </ol>
      <dl className="grid gap-x-8 sm:grid-cols-2">
        <Stat
          label="Applied to interview"
          value={formatRate(f.applied_to_interview_rate)}
        />
        <Stat label="Interview to offer" value={formatRate(f.interview_to_offer_rate)} />
        <Stat label="Offer to accepted" value={formatRate(f.offer_to_accepted_rate)} />
        <Stat
          label="Median days to interview"
          value={formatDays(f.median_days_to_interview)}
        />
        <Stat
          label="Median days to rejection"
          value={formatDays(f.median_days_to_rejection)}
        />
        <Stat label="Median days to offer" value={formatDays(f.median_days_to_offer)} />
        <Stat label="Rejected before interview" value={f.rejected_before_interview} />
        <Stat label="Withdrawn before interview" value={f.withdrawn_before_interview} />
      </dl>
    </Section>
  )
}

export function DashboardPage() {
  const [data, setData] = useState<Dashboard | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api
      .getDashboard(localToday())
      .then(setData)
      .catch((caught: unknown) =>
        setError(
          caught instanceof Error ? caught.message : 'Could not load the dashboard.',
        ),
      )
  }, [])

  if (error) return <ErrorMessage>{error}</ErrorMessage>
  if (!data)
    return (
      <p role="status" aria-live="polite">
        Loading…
      </p>
    )

  const health = data.discovery
  const attention =
    health.sync_reason === 'stale' || health.sync_reason === 'never_synced'
  const systemNote =
    health.sources_needing_attention > 0 || attention
      ? `${health.sources_needing_attention} source${health.sources_needing_attention === 1 ? '' : 's'} need attention${attention ? '; the scheduled sync may be paused' : ''}.`
      : 'Sources are syncing normally.'

  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-2xl font-semibold">{greeting(new Date().getHours())}</h1>
        <p className="text-slate-600">
          {systemNote} This is your overview. Your{' '}
          <Link to="/inbox" className="underline">
            action queue
          </Link>{' '}
          and{' '}
          <Link to="/applications" className="underline">
            application workspace
          </Link>{' '}
          are one click away.
        </p>
      </header>
      <div className="divide-y divide-slate-200 rounded-lg border border-slate-200">
        <ActionRequired d={data} />
        <Pipeline d={data} />
        <div className="grid divide-y divide-slate-200 md:grid-cols-2 md:divide-x md:divide-y-0">
          <HighFit d={data} />
          <Upcoming d={data} />
        </div>
        <div className="grid divide-y divide-slate-200 md:grid-cols-2 md:divide-x md:divide-y-0">
          <DiscoveryHealth d={data} />
          <RequirementHealth d={data} />
        </div>
        <Funnel d={data} />
      </div>
    </div>
  )
}
