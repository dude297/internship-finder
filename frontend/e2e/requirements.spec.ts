import { writeFileSync } from 'node:fs'
import { expect, test, type Page } from '@playwright/test'
import { ingestionFixtureFile, owner } from './env.ts'

// ADR-012 Milestone 6 scenario: deterministic requirement extraction, owner review, staleness
// on a posting rewrite, review-state persistence, the "Needs review" list filter, a deadline
// filter/sort, Source Health, and adding an Ashby board. Every posting is synthetic and the
// board name is unique per run, so this is repeatable against a reused E2E database.
//
// The tests share one board, so they run in order (the health test reads the first test's sync).
test.describe.configure({ mode: 'serial' })

const run = Date.now()
const board = `examplerobotics${run}`
const boardUrl = `https://boards-api.greenhouse.io/v1/boards/${board}/jobs?content=true`
const organization = `Example Robotics ${run}`
const title = `Synthetic Requirements Intern ${run}`

const ashbyBoardName = `examplestudio${run}`
const ashbyOrganization = `Example Studio ${run}`
// Exactly the URL the Ashby adapter requests (app/ingestion/adapters/ashby.py).
const ashbyUrl = `https://api.ashbyhq.com/posting-api/job-board/${ashbyBoardName}?includeCompensation=false`

const manualTitle = `Synthetic Deadline Program ${run}`

function greenhouseJob(id: number, description: string) {
  return {
    id,
    title,
    absolute_url: `https://job-boards.greenhouse.io/${board}/jobs/${id}`,
    location: { name: 'Example City' },
    updated_at: '2040-09-15T10:00:00-04:00',
    first_published: '2040-09-01T09:00:00-04:00',
    company_name: 'Example Robotics',
    content: description,
  }
}

const initialDescription =
  '&lt;p&gt;Applicants must be at least 16 years old. Currently enrolled undergraduate ' +
  'students only. U.S. citizenship is preferred. Must have an active security clearance.&lt;/p&gt;'
const rewrittenDescription =
  '&lt;p&gt;Applicants must be at least 16 years old. Currently enrolled undergraduate ' +
  'students only. U.S. citizenship is preferred. Must have an active security clearance. ' +
  'Must be authorized to work in the ' +
  'United States.&lt;/p&gt;'

function publishGreenhouse(description: string) {
  writeFileSync(
    ingestionFixtureFile,
    JSON.stringify({
      [boardUrl]: { jobs: [greenhouseJob(1, description)], meta: { total: 1 } },
      [boardUrl.replace('?content=true', '')]: {
        jobs: [greenhouseJob(1, description)],
        meta: { total: 1 },
      },
      [ashbyUrl]: {
        jobs: [
          {
            id: `ashby-job-${run}`,
            title: `Synthetic Ashby Intern ${run}`,
            location: 'Example City',
            employmentType: 'Intern',
            isListed: true,
            publishedAt: '2040-09-15T10:00:00Z',
            jobUrl: `https://jobs.ashbyhq.com/${ashbyBoardName}/ashby-job-${run}`,
            descriptionHtml: '<p>Build synthetic things.</p>',
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

async function openOpportunity(page: Page, heading: string, show = 'open') {
  await page.getByRole('link', { name: 'Opportunities', exact: true }).click()
  await page.getByLabel('Show').selectOption(show)
  await page.getByLabel('Search title or organization').fill(String(run))
  await page.getByRole('button', { name: 'Search' }).click()
  await page.getByRole('link', { name: heading }).click()
  await expect(page.getByRole('heading', { level: 1 })).toHaveText(heading)
}

test('requirement intelligence: extraction, review, staleness, and persistence', async ({
  page,
}) => {
  const eligibility = page.getByRole('region', { name: 'Eligibility' })
  const review = page.getByRole('region', { name: 'Requirement Review' })

  await login(page)

  // A profile so the opportunity is evaluated.
  await page.getByRole('link', { name: 'Profile', exact: true }).click()
  await page.getByLabel('Current level').selectOption('high_school')
  await page.getByLabel('Status as of').fill('2040-09-01')
  await page.getByLabel('Expected graduation').fill('2041-06-10')
  await page.getByLabel('Expected college enrollment').fill('2041-08-25')
  await page.getByLabel('Expected future level').selectOption('undergraduate')
  await page.getByLabel('Date of birth (optional)').fill('2023-06-20')
  await page.getByRole('button', { name: 'Save profile' }).click()
  await expect(page.getByRole('status')).toContainText('Profile saved.')

  // Add a Greenhouse board by its public link and sync the first version of the posting.
  await page.getByRole('link', { name: 'Sources', exact: true }).click()
  await page.getByLabel('Organization name').fill(organization)
  await page
    .getByLabel('Job board link or name')
    .fill(`https://job-boards.greenhouse.io/${board}`)
  await page.getByRole('button', { name: 'Add source' }).click()
  await expect(page.getByText(`Added ${organization}.`, { exact: false })).toBeVisible()
  publishGreenhouse(initialDescription)
  await page.getByRole('button', { name: `Sync ${organization} now` }).click()
  await expect(page.getByText(`${organization}: sync finished.`)).toBeVisible()

  await openOpportunity(page, title)
  await expect(
    eligibility.getByText('Needs verification', { exact: true }).first(),
  ).toBeVisible()

  // Pending suggestions: age and education, never citizenship ("preferred" is a hedge word).
  await expect(review.getByText('No pending suggestions.')).not.toBeVisible()
  await expect(
    review.getByRole('button', { name: /Accept minimum age 16/ }),
  ).toBeVisible()
  await expect(
    review.getByRole('button', { name: /Accept education \(undergraduate\)/ }),
  ).toBeVisible()
  await expect(review.getByRole('button', { name: /citizenship/i })).not.toBeVisible()

  await review.getByRole('button', { name: /Accept minimum age 16/ }).click()
  await review.getByRole('button', { name: /Edit education \(undergraduate\)/ }).click()
  await review.getByLabel(/Incoming students accepted/).check()
  // A suggestion the owner disagrees with: rejected in the same single batch.
  await review.getByRole('button', { name: /^Reject other.*security clearance/i }).click()
  await review.getByRole('radio', { name: /All hard requirements reviewed/ }).check()
  await review.getByRole('button', { name: /Apply changes/ }).click()

  await expect(
    review.getByText(/^Assessment: All hard requirements reviewed/),
  ).toBeVisible()
  await expect(eligibility.getByText('Eligible', { exact: true }).first()).toBeVisible()

  // Review state and eligibility survive a logout/login.
  await page.getByRole('button', { name: 'Log out' }).click()
  await login(page)
  await openOpportunity(page, title)
  // The owner's edit (incoming accepted) persisted and is what the Accepted list shows.
  const acceptedSuggestions = review.getByRole('region', { name: 'Accepted' })
  await expect(
    acceptedSuggestions.getByText('undergraduate (incoming students accepted)', {
      exact: true,
    }),
  ).toBeVisible()
  await expect(
    acceptedSuggestions.getByText('at least 16 years old', { exact: true }),
  ).toBeVisible()
  await expect(eligibility.getByText('Eligible', { exact: true }).first()).toBeVisible()

  // The posting changes materially (adds a work-authorization sentence); syncing reopens
  // review without discarding the accepted requirements.
  publishGreenhouse(rewrittenDescription)
  await page.getByRole('link', { name: 'Sources', exact: true }).click()
  await page.getByRole('button', { name: `Sync ${organization} now` }).click()
  await expect(page.getByText(`${organization}: sync finished.`)).toBeVisible()

  await openOpportunity(page, title)
  await expect(
    review.getByText(
      'Posting changed since requirement review. Review requirements again.',
    ),
  ).toBeVisible()
  await expect(review.getByText(/^Assessment: Some requirements recorded/)).toBeVisible()
  await expect(review.getByText('at least 16 years old', { exact: true })).toBeVisible() // kept, in Accepted
  await expect(
    review.getByRole('button', { name: /Accept work authorization/ }),
  ).toBeVisible()
  // The rejected suggestion is still in the rewritten posting but is never re-proposed.
  const pendingSuggestions = review.getByRole('region', { name: 'Pending suggestions' })
  await expect(pendingSuggestions.getByText(/security clearance/i)).toHaveCount(0)
  await expect(
    review
      .getByRole('region', { name: 'Rejected' })
      .getByText(/security clearance/i)
      .first(),
  ).toBeVisible()

  // The "Needs review" list filter finds it.
  await page.getByRole('link', { name: 'Opportunities', exact: true }).click()
  await page.getByLabel('Requirement suggestions').selectOption('needs_review')
  await page.getByLabel('Search title or organization').fill(String(run))
  await page.getByRole('button', { name: 'Search' }).click()
  await expect(page.getByRole('link', { name: title })).toBeVisible()
})

test('deadline filter and sort', async ({ page }) => {
  await login(page)

  // A manual opportunity whose deadline is 3 local days out, created through the same-origin
  // API with the browser's session and CSRF token.
  const soon = new Date()
  soon.setDate(soon.getDate() + 3)
  const deadline = [
    soon.getFullYear(),
    String(soon.getMonth() + 1).padStart(2, '0'),
    String(soon.getDate()).padStart(2, '0'),
  ].join('-')
  const session = await (await page.request.get('/api/auth/session')).json()
  const response = await page.request.post('/api/opportunities', {
    headers: { 'X-CSRF-Token': session.csrf_token },
    data: {
      title: manualTitle,
      organization: `Example Deadline Org ${run}`,
      opportunity_type: 'internship',
      application_deadline: deadline,
      requirements_assessment_status: 'unassessed',
      requirements: [],
    },
  })
  expect(response.status()).toBe(201)

  await page.getByRole('link', { name: 'Opportunities', exact: true }).click()
  await page.getByLabel('Search title or organization').fill(String(run))
  await page.getByLabel('Deadline').selectOption('7')
  await page.getByRole('button', { name: 'Search' }).click()
  await expect(page.getByRole('link', { name: manualTitle })).toBeVisible()
  await expect(page.getByRole('listitem').filter({ hasText: manualTitle })).toContainText(
    'Closing soon',
  )

  await page.getByLabel('Sort').selectOption('deadline')
  await expect(page.getByRole('link', { name: manualTitle })).toBeVisible()
})

test('source health and an Ashby board', async ({ page }) => {
  await login(page)
  await page.getByRole('link', { name: 'Sources', exact: true }).click()

  await expect(
    page.getByRole('listitem').filter({ hasText: organization }).getByText('Healthy'),
  ).toBeVisible()

  await page.getByLabel('Provider').selectOption('ashby')
  await expect(page.getByLabel(/Lever region/)).not.toBeVisible()
  await page.getByLabel('Organization name').fill(ashbyOrganization)
  await page
    .getByLabel('Job board link or name')
    .fill(`https://jobs.ashbyhq.com/${ashbyBoardName}`)
  await page.getByRole('button', { name: 'Add source' }).click()
  await expect(
    page.getByText(`Added ${ashbyOrganization}.`, { exact: false }),
  ).toBeVisible()

  await page.getByRole('button', { name: `Sync ${ashbyOrganization} now` }).click()
  await expect(page.getByText(`${ashbyOrganization}: sync finished.`)).toBeVisible()
  const card = page.getByRole('listitem').filter({ hasText: ashbyBoardName })
  await expect(card).toContainText('Created: 1')

  await page.getByRole('link', { name: 'Opportunities', exact: true }).click()
  await page.getByLabel('Search title or organization').fill(String(run))
  await page.getByRole('button', { name: 'Search' }).click()
  await expect(
    page.getByRole('link', { name: `Synthetic Ashby Intern ${run}` }),
  ).toBeVisible()
})
