import { Link } from 'react-router'
import { fitComponentKeys, type ScoreBreakdown } from '../api/schemas'
import { fitComponentLabels } from '../lib/labels'
import { FitBadge } from './FitBadge'

function Chips({ label, items, tone }: { label: string; items: string[]; tone: string }) {
  if (!items.length) return null
  return (
    <p className="text-sm">
      <span className="text-slate-500">{label}: </span>
      {items.map((item) => (
        <span key={item} className={`mr-1 inline-block rounded px-1.5 py-0.5 ${tone}`}>
          {item}
        </span>
      ))}
    </p>
  )
}

/** The six fit components as the backend explained them. Nothing here computes a score. */
export function WhyThisMatch({ breakdown }: { breakdown: ScoreBreakdown | null }) {
  return (
    <section aria-labelledby="fit-heading" className="space-y-3 rounded border p-4">
      <div className="flex flex-wrap items-center gap-3">
        <h2 id="fit-heading" className="text-lg font-semibold">
          Why this match?
        </h2>
        {breakdown && <FitBadge score={breakdown.score} coverage={breakdown.coverage} />}
      </div>
      {!breakdown ? (
        <p className="text-slate-600">
          No fit score yet. Save your{' '}
          <Link to="/profile/match" className="text-blue-800 underline">
            Match Profile
          </Link>{' '}
          to score opportunities.
        </p>
      ) : (
        <>
          <p className="text-sm text-slate-600">
            Fit ranks opportunities within the same eligibility status; it never changes
            eligibility.
            {breakdown.coverage < 100 && (
              <>
                {' '}
                Only {breakdown.coverage}% of the score could be measured: missing parts
                count as 0, not as a match.{' '}
                <Link to="/profile/match" className="text-blue-800 underline">
                  Complete your Match Profile
                </Link>
              </>
            )}
          </p>
          <ul className="space-y-2">
            {fitComponentKeys.map((key) => {
              const component = breakdown.components[key]
              if (!component) return null
              const [found, notFound] =
                key === 'quality' ? ['Has', 'Missing'] : ['Matched', 'Not found']
              return (
                <li key={key} className="rounded border border-slate-100 p-3">
                  <p className="flex flex-wrap items-baseline justify-between gap-2">
                    <span className="font-medium">{fitComponentLabels[key]}</span>
                    <span className="text-sm text-slate-600">
                      {component.missing
                        ? `Not measured · weight ${component.weight}%`
                        : `${component.score}/100 · weight ${component.weight}%`}
                    </span>
                  </p>
                  <p className="text-sm text-slate-700">{component.reason}</p>
                  {component.missing && (
                    <p className="text-xs text-amber-800">
                      {component.missing_input === 'opportunity'
                        ? "The posting doesn't include this information."
                        : 'Missing from your Match Profile.'}
                    </p>
                  )}
                  <Chips
                    label={found}
                    items={component.matched}
                    tone="bg-green-50 text-green-900"
                  />
                  <Chips
                    label={notFound}
                    items={component.unmatched}
                    tone="bg-slate-100 text-slate-700"
                  />
                </li>
              )
            })}
          </ul>
          <p className="text-xs text-slate-500">Scoring {breakdown.scoring_version}</p>
        </>
      )}
    </section>
  )
}
