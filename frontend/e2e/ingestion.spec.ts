import { writeFileSync } from 'node:fs'
import { expect, test, type Page } from '@playwright/test'
import { ingestionFixtureFile, owner } from './env.ts'

// Synthetic ingestion workflow. Source responses come from a local fixture file (see env.ts);
// nothing here calls a real job board. Every company, posting, and date is fictional.

const run = Date.now()
const board = `examplerobotics${run}`
const boardUrl = `https://boards-api.greenhouse.io/v1/boards/${board}/jobs?content=true`
const titleA = `Synthetic Robotics Intern ${run}`
const titleB = `Synthetic Controls Intern ${run}`
// Unique per run: a reused E2E database keeps the sources of earlier runs.
const organization = `Example Robotics ${run}`

function job(id: number, title: string) {
  return {
    id,
    title,
    absolute_url: `https://job-boards.greenhouse.io/${board}/jobs/${id}`,
    location: { name: 'Example City' },
    updated_at: '2040-09-15T10:00:00-04:00',
    first_published: '2040-09-01T09:00:00-04:00',
    company_name: 'Example Robotics',
    content:
      '&lt;p&gt;Build synthetic robots.&lt;/p&gt;&lt;script&gt;alert(1)&lt;/script&gt;',
  }
}

/** Publish a synthetic Greenhouse board snapshot for the backend's next sync. */
function publish(...jobs: ReturnType<typeof job>[]) {
  writeFileSync(
    ingestionFixtureFile,
    JSON.stringify({ [boardUrl]: { jobs, meta: { total: jobs.length } } }),
    'utf-8',
  )
}

async function syncBoard(page: Page) {
  await page.getByRole('link', { name: 'Sources', exact: true }).click()
  await page.getByRole('button', { name: `Sync ${organization} now` }).click()
  await expect(page.getByText(`${organization}: sync finished.`)).toBeVisible()
  return page.getByRole('listitem').filter({ hasText: board })
}

async function openOpportunity(page: Page, title: string, show = 'open') {
  await page.getByRole('link', { name: 'Opportunities', exact: true }).click()
  await page.getByLabel('Show').selectOption(show)
  await page.getByLabel('Search title or organization').fill(String(run))
  await page.getByRole('button', { name: 'Search' }).click()
  await page.getByRole('link', { name: title }).click()
  await expect(page.getByRole('heading', { level: 1 })).toHaveText(title)
}

test('ingestion workflow: sync, dedupe, review, curation, closure, tracking', async ({
  page,
}) => {
  const eligibility = page.getByRole('region', { name: 'Eligibility' })

  await page.goto('/login')
  await page.getByLabel('Username').fill(owner.username)
  await page.getByLabel('Password').fill(owner.password)
  await page.getByRole('button', { name: 'Log in' }).click()
  await expect(page).not.toHaveURL(/\/login$/)

  // A profile, so imported opportunities are evaluated.
  await page.getByRole('link', { name: 'Profile' }).click()
  await page.getByLabel('Current level').selectOption('high_school')
  await page.getByLabel('Status as of').fill('2040-09-01')
  await page.getByLabel('Expected graduation').fill('2041-06-10')
  await page.getByLabel('Expected college enrollment').fill('2041-08-25')
  await page.getByLabel('Expected future level').selectOption('undergraduate')
  await page.getByLabel('Date of birth (optional)').fill('2023-06-20')
  await page.getByRole('button', { name: 'Save profile' }).click()
  await expect(page.getByRole('status')).toContainText('Profile saved.')

  // Add a Greenhouse board by its public link; the built-in feed is already listed.
  await page.getByRole('link', { name: 'Sources', exact: true }).click()
  await expect(page.getByText('Tech Internship Discovery Feed')).toBeVisible()
  await page.getByLabel('Organization name').fill(organization)
  await page
    .getByLabel('Job board link or name')
    .fill(`https://job-boards.greenhouse.io/${board}`)
  await page.getByRole('button', { name: 'Add source' }).click()
  await expect(page.getByText(`Added ${organization}.`, { exact: false })).toBeVisible()

  // First sync imports two postings; the identical second sync changes nothing.
  publish(job(1, titleA), job(2, titleB))
  let card = await syncBoard(page)
  await expect(card).toContainText('Succeeded')
  await expect(card).toContainText('Created: 2')
  card = await syncBoard(page)
  await expect(card).toContainText('Unchanged: 2')
  await expect(card).toContainText('Created: 0')

  await page.getByRole('link', { name: 'Opportunities', exact: true }).click()
  await page.getByLabel('Search title or organization').fill(String(run))
  await page.getByRole('button', { name: 'Search' }).click()
  await expect(page.getByRole('status')).toHaveText('Showing 1–2 of 2')
  await expect(page.getByRole('listitem').filter({ hasText: titleA })).toContainText(
    'Imported',
  )

  // Imported postings start unassessed: needs verification until the owner reviews them.
  await openOpportunity(page, titleA)
  await expect(
    eligibility.getByText('Needs verification', { exact: true }).first(),
  ).toBeVisible()
  await expect(page.getByText('Build synthetic robots.')).toBeVisible() // HTML → text
  await expect(page.getByRole('region', { name: 'Source' })).toContainText(
    'Example Robotics',
  )

  await page.getByRole('link', { name: 'Review requirements' }).click()
  await expect(page.getByText(/later syncs keep your edits/)).toBeVisible()
  await page.getByLabel('Start date').fill('2041-06-20')
  await page.getByRole('button', { name: 'Add requirement' }).click()
  const education = page.getByRole('group', { name: 'Requirement 1' })
  await education.getByLabel('Type').selectOption('education')
  await education.getByLabel('Undergraduate (college)').check()
  await education.getByLabel(/Incoming students accepted/).check()
  await page.getByRole('radio', { name: /All hard requirements reviewed/ }).check()
  await page.getByRole('button', { name: 'Save opportunity' }).click()
  await expect(page.getByRole('heading', { level: 1 })).toHaveText(titleA)
  await expect(eligibility.getByText('Eligible', { exact: true }).first()).toBeVisible()

  // Track the second posting.
  await openOpportunity(page, titleB)
  await page.getByRole('button', { name: 'Track this opportunity' }).click()
  await page.getByLabel('Status').selectOption('applied')
  await page.getByLabel('Private notes').fill('Synthetic E2E ingestion note.')
  await page.getByRole('button', { name: 'Save application' }).click()
  await expect(page.getByText('Application tracking saved.')).toBeVisible()

  // Upstream renames A and removes B. The review survives; B closes instead of disappearing.
  publish(job(1, `Upstream Renamed ${run}`))
  card = await syncBoard(page)
  await expect(card).toContainText('Updated: 1')
  await expect(card).toContainText('Closed: 1')

  await openOpportunity(page, titleA)
  await expect(eligibility.getByText('Eligible', { exact: true }).first()).toBeVisible()
  await expect(page.getByText('Education', { exact: false }).first()).toBeVisible()
  await expect(page.getByText('All hard requirements reviewed')).toBeVisible()

  await page.getByRole('link', { name: 'Opportunities', exact: true }).click()
  await page.getByLabel('Search title or organization').fill(String(run))
  await page.getByRole('button', { name: 'Search' }).click()
  await expect(page.getByRole('status')).toHaveText('Showing 1–1 of 1')

  await openOpportunity(page, titleB, 'closed')
  await expect(page.getByText(/Closed: no source lists this posting/)).toBeVisible()
  await expect(page.getByLabel('Status')).toHaveValue('applied')
  await expect(page.getByLabel('Private notes')).toHaveValue(
    'Synthetic E2E ingestion note.',
  )
})
