import { Link } from 'react-router'
import { Mark } from '../components/Mark'

// Public page: static copy and synthetic examples only. No network calls, no live numbers.

const SOURCES = [
  'Greenhouse',
  'Lever',
  'Ashby',
  'SmartRecruiters',
  'Workable',
  'Pinpoint',
  'Programs',
]
const CHECKS = ['Eligibility', 'Fit', 'Freshness', 'Requirements']

const CAPABILITIES = [
  {
    n: '01',
    title: 'Discover',
    body: 'Pulls postings straight from company career boards and a curated registry of research and fellowship programs, not from reposted aggregator pages.',
  },
  {
    n: '02',
    title: 'Verify',
    body: 'Every posting shows where it came from and when it was last confirmed. Requirements pulled from the text are reviewed by you before they count.',
  },
  {
    n: '03',
    title: 'Match',
    body: 'Eligibility is checked first: age, enrollment status and dates. Fit then ranks what is eligible, with the reasons listed. Rules, not a model guessing.',
  },
  {
    n: '04',
    title: 'Decide',
    body: 'Open a posting and see what matched, what is missing, and what is unclear before you spend an evening on an application.',
  },
  {
    n: '05',
    title: 'Track',
    body: 'Move each opportunity from saved to applied to offer. An action inbox surfaces closing deadlines and postings that need a second look.',
  },
]

function Schematic() {
  const sy = (i: number) => 58 + i * 44
  const cy = (i: number) => 106 + i * 56
  const flow = [
    ...SOURCES.map((_, i) => `M140,${sy(i)}H190V190H240`),
    ...CHECKS.map((_, i) => `M380,190H425V${cy(i)}H470`),
    ...CHECKS.map((_, i) => `M620,${cy(i)}H660V190H700`),
  ]
  return (
    <svg
      viewBox="0 0 840 350"
      role="img"
      aria-label="Diagram: seven source types feed the opportunity engine, which runs eligibility, fit, freshness and requirement checks and delivers results to the action inbox."
      className="hidden h-auto w-full md:block"
    >
      <g
        className="font-mono"
        fontSize="11"
        fill="var(--color-lab-muted)"
        letterSpacing="1.2"
      >
        <text x="0" y="20">
          SOURCES
        </text>
        <text x="240" y="20">
          ENGINE
        </text>
        <text x="470" y="20">
          CHECKS
        </text>
        <text x="700" y="20">
          OUTPUT
        </text>
      </g>
      <g fill="none" stroke="var(--color-lab-border)" strokeWidth="1.5">
        {flow.map((d) => (
          <path key={d} d={d} />
        ))}
      </g>
      <g
        fill="none"
        stroke="var(--color-lab-accent)"
        strokeWidth="2"
        strokeLinecap="round"
      >
        {flow.map((d) => (
          <path key={d} d={d} className="lab-signal" />
        ))}
      </g>
      <g fontSize="13" className="font-mono" fill="var(--color-lab-text)">
        {SOURCES.map((s, i) => (
          <g key={s}>
            <rect
              x="0.75"
              y={sy(i) - 16}
              width="138.5"
              height="32"
              rx="3"
              fill="var(--color-lab-surface)"
              stroke="var(--color-lab-border)"
            />
            <text x="12" y={sy(i) + 4.5}>
              {s}
            </text>
          </g>
        ))}
        <rect
          x="240.75"
          y="120.75"
          width="138.5"
          height="138.5"
          rx="4"
          fill="var(--color-lab-elevated)"
          stroke="var(--color-lab-accent)"
          strokeWidth="1.5"
        />
        <text x="310" y="180" textAnchor="middle">
          Opportunity
        </text>
        <text x="310" y="200" textAnchor="middle">
          Engine
        </text>
        <text
          x="310"
          y="228"
          textAnchor="middle"
          fontSize="11"
          fill="var(--color-lab-muted)"
        >
          normalize · dedupe
        </text>
        {CHECKS.map((c, i) => (
          <g key={c}>
            <rect
              x="470.75"
              y={cy(i) - 17}
              width="148.5"
              height="34"
              rx="3"
              fill="var(--color-lab-surface)"
              stroke="var(--color-lab-border)"
            />
            <text x="484" y={cy(i) + 4.5}>
              {c}
            </text>
          </g>
        ))}
        <rect
          x="700.75"
          y="140.75"
          width="138.5"
          height="98.5"
          rx="4"
          fill="var(--color-lab-elevated)"
          stroke="var(--color-lab-border)"
        />
        <text x="770" y="184" textAnchor="middle">
          Action
        </text>
        <text x="770" y="204" textAnchor="middle">
          Inbox
        </text>
      </g>
    </svg>
  )
}

/** Small-screen replacement for the schematic: the same four stages, stacked. */
function SchematicStack() {
  const stages = [
    ['Sources', SOURCES.join(' · ')],
    ['Opportunity Engine', 'normalize · dedupe'],
    ['Checks', CHECKS.join(' · ')],
    ['Action Inbox', 'closing soon · needs review'],
  ]
  return (
    <ol className="space-y-0 md:hidden" aria-label="How postings flow through the system">
      {stages.map(([name, detail], i) => (
        <li key={name}>
          <div className="rounded-control border border-lab-border bg-lab-surface p-3">
            <p className="font-mono text-xs tracking-wider text-lab-accent uppercase">
              {name}
            </p>
            <p className="mt-1 font-mono text-sm text-lab-text">{detail}</p>
          </div>
          {i < stages.length - 1 && (
            <div aria-hidden="true" className="ml-6 h-4 w-px bg-lab-accent" />
          )}
        </li>
      ))}
    </ol>
  )
}

const chip =
  'inline-block rounded-control border border-lab-border px-2 py-0.5 font-mono text-xs'

/** A synthetic row: nothing here is a real posting. */
function ProductPreview() {
  return (
    <figure
      aria-label="Example opportunity (synthetic data)"
      className="rounded-card border border-lab-border bg-lab-surface shadow-lab"
    >
      <figcaption className="flex items-center justify-between border-b border-lab-border px-4 py-2 font-mono text-xs text-lab-muted">
        <span>opportunities / example</span>
        <span>synthetic data</span>
      </figcaption>
      <div className="grid gap-4 p-4 sm:grid-cols-[1fr_auto] sm:items-start">
        <div>
          <p className="text-lg font-semibold text-lab-text">
            Software Engineering Intern, Summer 2041
          </p>
          <p className="text-sm text-lab-muted">Example Labs · Remote (US)</p>
          <div className="mt-3 flex flex-wrap gap-2">
            <span className={`${chip} text-lab-success`}>Eligible</span>
            <span className={`${chip} text-lab-text`}>Fit 82 · 6 of 7 signals</span>
            <span className={`${chip} text-lab-text`}>Fresh · checked 2 days ago</span>
            <span className={`${chip} text-lab-warning`}>Closing in 6 days</span>
          </div>
          <p className="mt-3 font-mono text-xs text-lab-muted">
            Source: Greenhouse board (direct) · first seen 9 days ago
          </p>
        </div>
        <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 border-t border-lab-border pt-3 text-sm sm:border-t-0 sm:border-l sm:pt-0 sm:pl-4">
          <dt className="font-mono text-xs text-lab-muted">matched</dt>
          <dd className="text-lab-text">Python, SQL, data tools</dd>
          <dt className="font-mono text-xs text-lab-muted">missing</dt>
          <dd className="text-lab-text">Cloud experience</dd>
          <dt className="font-mono text-xs text-lab-muted">review</dt>
          <dd className="text-lab-text">2 requirements to confirm</dd>
        </dl>
      </div>
    </figure>
  )
}

export function LandingPage() {
  return (
    <div className="min-h-screen bg-lab-bg font-sans text-lab-text">
      <header className="border-b border-lab-border">
        <div className="mx-auto flex max-w-6xl items-center gap-3 px-gutter py-3">
          <Mark className="h-7 w-7 text-lab-accent" />
          <span className="font-semibold">Internship Finder</span>
          <Link
            to="/login"
            className="ml-auto inline-flex min-h-10 items-center rounded-control border border-lab-border px-4 text-sm font-medium hover:bg-lab-elevated"
          >
            Sign in
          </Link>
        </div>
      </header>

      <main>
        <section className="mx-auto max-w-6xl px-gutter pt-12 pb-10 md:pt-20">
          <div className="lab-rise max-w-3xl">
            <p className="font-mono text-xs tracking-widest text-lab-accent uppercase">
              Internships · research programs · fellowships
            </p>
            <h1 className="mt-4 text-4xl leading-tight font-semibold tracking-tight md:text-6xl">
              Find the internships that actually fit you.
            </h1>
            <p className="mt-5 max-w-2xl text-lg text-lab-muted">
              Postings collected directly from company career pages, checked for
              eligibility before anything else, ranked with reasons you can read, and
              tracked through to your decision. The scoring is deterministic rules you can
              inspect, not a chatbot.
            </p>
            <div className="mt-8 flex flex-wrap items-center gap-4">
              <Link
                to="/login"
                className="inline-flex min-h-11 items-center rounded-control bg-lab-accent-strong px-6 font-medium text-white hover:bg-lab-accent-hover"
              >
                Sign in
              </Link>
              <a
                href="#capabilities"
                className="inline-flex min-h-11 items-center text-sm text-lab-muted underline underline-offset-4 hover:text-lab-text"
              >
                How it works
              </a>
            </div>
          </div>
          <div className="mt-12 rounded-card border border-lab-border bg-lab-surface p-4 md:p-6">
            <Schematic />
            <SchematicStack />
          </div>
          <dl className="mt-6 grid gap-px overflow-hidden rounded-card border border-lab-border bg-lab-border sm:grid-cols-3">
            {[
              ['7', 'source types, read directly'],
              ['4', 'independent checks per posting'],
              ['0', 'applications sent for you'],
            ].map(([value, label]) => (
              <div key={label} className="bg-lab-surface p-4">
                <dt className="font-mono text-3xl text-lab-text">{value}</dt>
                <dd className="mt-1 text-sm text-lab-muted">{label}</dd>
              </div>
            ))}
          </dl>
        </section>

        <section
          id="capabilities"
          aria-labelledby="capabilities-heading"
          className="border-t border-lab-border bg-lab-surface"
        >
          <div className="mx-auto max-w-6xl px-gutter py-14">
            <h2 id="capabilities-heading" className="text-2xl font-semibold md:text-3xl">
              From a company career page to a decision
            </h2>
            <ol className="mt-8 grid gap-px overflow-hidden rounded-card border border-lab-border bg-lab-border md:grid-cols-2 lg:grid-cols-3">
              {CAPABILITIES.map((c) => (
                <li key={c.n} className="bg-lab-bg p-5">
                  <p className="font-mono text-sm text-lab-accent">{c.n}</p>
                  <h3 className="mt-2 text-lg font-semibold">{c.title}</h3>
                  <p className="mt-2 text-sm leading-relaxed text-lab-muted">{c.body}</p>
                </li>
              ))}
              <li aria-hidden="true" className="hidden bg-lab-bg md:block" />
            </ol>
          </div>
        </section>

        <section
          aria-labelledby="preview-heading"
          className="mx-auto max-w-6xl px-gutter py-14"
        >
          <h2 id="preview-heading" className="text-2xl font-semibold md:text-3xl">
            What you see for each posting
          </h2>
          <p className="mt-2 max-w-2xl text-lab-muted">
            Eligibility, fit, freshness, deadline and provenance sit on one row, so you
            can tell at a glance what deserves your time.
          </p>
          <div className="mt-8">
            <ProductPreview />
          </div>
        </section>
      </main>

      <footer className="border-t border-lab-border">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-3 px-gutter py-6 text-sm text-lab-muted">
          <Mark className="h-5 w-5" />
          <span>Personal Internship Finder. A private, single-owner workspace.</span>
          <Link
            to="/login"
            className="ml-auto inline-flex min-h-10 items-center underline underline-offset-4 hover:text-lab-text"
          >
            Sign in
          </Link>
        </div>
      </footer>
    </div>
  )
}
