import { writeFileSync } from 'node:fs'
import { expect, test, type Page } from '@playwright/test'
import { ingestionFixtureFile, owner } from './env.ts'

// ADR-013 Milestone 7 scenario: source discovery and coverage, derived on read from the
// discovery feed. Network-free, through the same INGESTION_FIXTURE_FILE mechanism as
// ingestion.spec.ts. Log in; sync the discovery feed fixture so it creates a feed-only
// opportunity whose ID proves an Ashby board; open the Sources page's coverage section and
// check it reports the opportunity as feed-only and enrichable; add the suggested Ashby board
// and sync its fixture; check the opportunity's canonical description switches to the board's
// text (takeover) and coverage moves it out of feed-only. All synthetic, no real network call.
//
// No other spec writes to the discovery feed's URL in INGESTION_FIXTURE_FILE and no other spec
// syncs the feed source, so this test's feed snapshot (which fully replaces earlier runs' feed
// items and closes them) never affects another spec file. Board and opportunity identifiers are
// unique per run, so this is repeatable on a reused E2E database.

const run = Date.now()
const board = `example-board-${run}`
const ashbyUuid = '1b2c3d4e-0000-4000-8000-000000000001'
const feedId = `ashby:${board}:${ashbyUuid}`
const postingUrl = `https://jobs.ashbyhq.com/${board}/${ashbyUuid}`
const ashbyApiUrl = `https://api.ashbyhq.com/posting-api/job-board/${board}?includeCompensation=false`
const feedUrl =
  'https://zshah101.github.io/Automated-List-Of-Summer-2027-and-Fall-2026-Tech-Internships' +
  '/api/jobs.json'
const feedTitle = `Synthetic Coverage Intern ${run}`
const company = `Example Coverage Org ${run}`
const feedDisplayName = 'Tech Internship Discovery Feed'
const suggestionKey = `ashby:${board}`

function publishFeedOnly() {
  writeFileSync(
    ingestionFixtureFile,
    JSON.stringify({
      [feedUrl]: {
        generated_at: '2040-09-21T06:00:00Z',
        data_as_of: '2040-09-21T06:00:00Z',
        source: 'https://example.org/synthetic-feed',
        count: 1,
        jobs: [
          {
            id: feedId,
            company,
            title: feedTitle,
            url: postingUrl,
            location: 'Example City',
            posted_at: '2040-09-20T00:00:00Z',
            program: 'Internship',
          },
        ],
      },
    }),
    'utf-8',
  )
}

function publishFeedAndBoard() {
  writeFileSync(
    ingestionFixtureFile,
    JSON.stringify({
      [feedUrl]: {
        generated_at: '2040-09-21T06:00:00Z',
        data_as_of: '2040-09-21T06:00:00Z',
        source: 'https://example.org/synthetic-feed',
        count: 1,
        jobs: [
          {
            id: feedId,
            company,
            title: feedTitle,
            url: postingUrl,
            location: 'Example City',
            posted_at: '2040-09-20T00:00:00Z',
            program: 'Internship',
          },
        ],
      },
      [ashbyApiUrl]: {
        apiVersion: '1',
        jobs: [
          {
            id: ashbyUuid,
            title: feedTitle,
            location: 'Example City',
            employmentType: 'Intern',
            isListed: true,
            publishedAt: '2040-09-15T10:00:00Z',
            jobUrl: postingUrl,
            descriptionHtml: '<p>Build synthetic coverage pipelines.</p>',
            descriptionPlain:
              'Build synthetic coverage pipelines. Must be a U.S. citizen.',
          },
        ],
      },
    }),
    'utf-8',
  )
}

async function login(page: Page) {
  await page.goto('/login')
  await page.getByLabel('Username').fill(owner.username)
  await page.getByLabel('Password').fill(owner.password)
  await page.getByRole('button', { name: 'Log in' }).click()
  await expect(page).not.toHaveURL(/\/login$/)
}

test('source coverage: discovery suggests an Ashby board, and adding it enriches the feed posting', async ({
  page,
}) => {
  await login(page)

  // Sync the discovery feed: creates one feed-only opportunity whose ID proves an Ashby board.
  publishFeedOnly()
  await page.getByRole('navigation', { name: 'Main' }).getByRole('link', { name: 'Sources', exact: true }).click()
  await page.getByRole('button', { name: `Sync ${feedDisplayName} now` }).click()
  await expect(page.getByText(`${feedDisplayName}: sync finished.`)).toBeVisible()

  // Source Coverage reports it as feed-only and enrichable, with a suggestion for the board.
  const coverage = page.getByRole('heading', { name: 'Source Coverage' }).locator('..')
  await expect(coverage).toContainText('Feed-only')
  const suggestions = page
    .getByRole('heading', { name: 'Suggested Sources' })
    .locator('..')
  const row = suggestions.locator('tr').filter({ hasText: suggestionKey })
  await expect(row).toBeVisible()
  await expect(row).toContainText('1') // matching_opportunities / feed_only_opportunities

  // Select it and add it: creating a source from a suggestion never syncs it.
  await suggestions.getByLabel(`Select ${suggestionKey}`).check()
  await suggestions.getByRole('button', { name: 'Add selected sources' }).click()
  await expect(page.getByText(/^Added 1, skipped 0\./)).toBeVisible()

  // The new source appears in the Sources list, named after the feed's company label
  // (suggested_display_name), and defaults to Internships only / enabled.
  const card = page.getByRole('listitem').filter({ hasText: board })
  await expect(card).toBeVisible()
  await expect(card).toContainText(company)

  // Sync it: the board's text takes over the opportunity (ADR-013 §4.3), since an ATS record
  // outranks the feed.
  publishFeedAndBoard()
  await page.getByRole('button', { name: `Sync ${company} now` }).click()
  await expect(page.getByText(`${company}: sync finished.`)).toBeVisible()

  await page.getByRole('navigation', { name: 'Main' }).getByRole('link', { name: 'Opportunities', exact: true }).click()
  await page.getByLabel('Search title or organization').fill(String(run))
  await page.getByRole('button', { name: 'Search' }).click()
  await page.getByRole('link', { name: feedTitle }).click()
  await expect(page.getByRole('heading', { level: 1 })).toHaveText(feedTitle)

  // The board's description is now shown; eligibility still needs verification; a pending
  // requirement suggestion exists from the board's text (never accepted automatically).
  await expect(page.getByText('Build synthetic coverage pipelines.')).toBeVisible()
  await expect(
    page
      .getByRole('region', { name: 'Eligibility' })
      .getByText('Needs verification', {
        exact: true,
      })
      .first(),
  ).toBeVisible()
  await expect(
    page
      .getByRole('region', { name: 'Requirement Review' })
      .getByRole('button', { name: 'Accept citizenship (US)' }),
  ).toBeVisible()

  // Coverage now counts this opportunity as ATS-backed instead of feed-only.
  await page.getByRole('navigation', { name: 'Main' }).getByRole('link', { name: 'Sources', exact: true }).click()
  await expect(
    page.getByRole('heading', { name: 'Source Coverage' }).locator('..'),
  ).toContainText('Direct ATS-backed')
})
