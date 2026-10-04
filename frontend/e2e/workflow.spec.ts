import { expect, test, type Page } from '@playwright/test'
import { owner } from './env.ts'

// The complete private workflow with synthetic data (fictional dates, as in docs/eligibility.md):
// a high-school senior expected to graduate 2041-06-10 and enroll as an undergraduate 2041-08-25.

async function login(page: Page, password = owner.password) {
  await page.getByLabel('Username').fill(owner.username)
  await page.getByLabel('Password').fill(password)
  await page.getByRole('button', { name: 'Log in' }).click()
}

test('owner workflow: profile, opportunity, eligibility, re-evaluation, tracking', async ({
  page,
}) => {
  const title = `E2E Synthetic Research Program ${Date.now()}`
  const eligibility = page.getByRole('region', { name: 'Eligibility' })

  // Private pages redirect to login; wrong passwords get the generic message.
  await page.goto('/profile')
  await expect(page).toHaveURL(/\/login$/)
  await login(page, 'wrong-synthetic-password')
  await expect(page.getByRole('alert')).toHaveText('Invalid username or password.')
  await login(page)
  await expect(page).toHaveURL(/\/profile$/)

  // Profile with a projected education transition.
  await page.getByLabel('Current level').selectOption('high_school')
  await page.getByLabel('Current grade or year').fill('12')
  await page.getByLabel('Status as of').fill('2040-09-01')
  await page.getByLabel('Expected graduation').fill('2041-06-10')
  await page.getByLabel('Expected college enrollment').fill('2041-08-25')
  await page.getByLabel('Expected future level').selectOption('undergraduate')
  await page.getByLabel('Date of birth (optional)').fill('2023-06-20')
  await page.getByLabel('Citizenship(s) (optional)').fill('')
  await page.getByRole('button', { name: 'Save profile' }).click()
  await expect(page.getByRole('status')).toContainText('Profile saved.')

  // A manual opportunity with age and education requirements, marked complete.
  await page.getByRole('link', { name: 'Opportunities' }).click()
  await page.getByRole('link', { name: 'Add opportunity' }).click()
  await page.getByLabel('Title (required)').fill(title)
  await page.getByLabel('Organization (required)').fill('Example Institute')
  await page.getByLabel('Type').first().selectOption('research')
  await page.getByLabel('Application deadline').fill('2041-02-01')
  await page.getByLabel('Start date').fill('2041-06-20')
  await page.getByLabel('End date').fill('2041-08-01')

  await page.getByRole('button', { name: 'Add requirement' }).click()
  const age = page.getByRole('group', { name: 'Requirement 1' })
  await age.getByLabel('Minimum age (years)').fill('16')

  await page.getByRole('button', { name: 'Add requirement' }).click()
  const education = page.getByRole('group', { name: 'Requirement 2' })
  await education.getByLabel('Type').selectOption('education')
  await education.getByLabel('Undergraduate (college)').check()
  await education.getByLabel(/Incoming students accepted/).check()

  await page.getByRole('radio', { name: /All hard requirements reviewed/ }).check()
  await page.getByRole('button', { name: 'Save opportunity' }).click()

  // Evaluated automatically: eligible, based on the projected incoming-undergraduate status.
  await expect(page.getByRole('heading', { level: 1 })).toHaveText(title)
  await expect(eligibility.getByText('Eligible', { exact: true }).first()).toBeVisible()
  await expect(page.getByRole('note')).toContainText(
    'This result depends on expected future education dates.',
  )
  await expect(eligibility).toContainText('incoming undergraduate')
  const opportunityUrl = page.url()

  // A profile change that affects eligibility re-evaluates stored opportunities.
  await page.getByRole('link', { name: 'Profile', exact: true }).click()
  await page.getByLabel('Date of birth (optional)').fill('2026-01-01')
  await page.getByRole('button', { name: 'Save profile' }).click()
  await expect(page.getByRole('status')).toHaveText(
    'Profile saved. Eligibility results updated.',
  )
  await page.goto(opportunityUrl)
  await expect(eligibility.getByText('Ineligible', { exact: true }).first()).toBeVisible()
  await expect(eligibility).toContainText('below the minimum age of 16')

  // Application tracking.
  await page.getByRole('button', { name: 'Track this opportunity' }).click()
  await page.getByLabel('Status').selectOption('applied')
  await page.getByLabel('Submitted on').fill('2041-01-20')
  await page.getByLabel('Private notes').fill('Synthetic E2E note.')
  await page.getByRole('button', { name: 'Save application' }).click()
  await expect(page.getByText('Application tracking saved.')).toBeVisible()

  await page.getByRole('link', { name: 'Opportunities', exact: true }).click()
  // Search by the unique title: on a reused E2E database the row can be past page one.
  await page.getByLabel('Search title or organization').fill(title)
  await page.getByRole('button', { name: 'Search' }).click()
  const row = page.getByRole('listitem').filter({ hasText: title })
  await expect(row).toContainText('Applied')
  await expect(row).toContainText('Ineligible')

  // Logout: private routes and the private API are closed.
  await page.getByRole('button', { name: 'Log out' }).click()
  await expect(page).toHaveURL(/\/login$/)
  await page.goto('/opportunities')
  await expect(page).toHaveURL(/\/login$/)
  expect((await page.request.get('/api/profile')).status()).toBe(401)
  expect((await page.request.get('/api/opportunities')).status()).toBe(401)

  // Log in again: everything persisted.
  await login(page)
  await expect(page).toHaveURL(/\/opportunities$/)
  await page.goto(opportunityUrl)
  await expect(page.getByRole('heading', { level: 1 })).toHaveText(title)
  await expect(page.getByLabel('Status')).toHaveValue('applied')
  await expect(page.getByLabel('Private notes')).toHaveValue('Synthetic E2E note.')
  await expect(eligibility.getByText('Ineligible', { exact: true }).first()).toBeVisible()
  await page.getByRole('link', { name: 'Profile', exact: true }).click()
  await expect(page.getByLabel('Date of birth (optional)')).toHaveValue('2026-01-01')
})
