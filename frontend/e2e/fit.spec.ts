import { expect, test, type Page } from '@playwright/test'
import { owner } from './env.ts'

// Fit ranking end to end with synthetic data. Every term is unique per run, so the test is
// repeatable on a reused E2E database: the search box narrows the list to this run's postings.

const run = Date.now()
const alpha = `alphaskill${run}`
const beta = `betaskill${run}`

async function login(page: Page) {
  await page.goto('/login')
  await page.getByLabel('Username').fill(owner.username)
  await page.getByLabel('Password').fill(owner.password)
  await page.getByRole('button', { name: 'Log in' }).click()
  await expect(page).not.toHaveURL(/\/login$/)
}

/** Create an opportunity through the same-origin API (the browser's session and CSRF token). */
async function createOpportunity(page: Page, body: Record<string, unknown>) {
  const session = await (await page.request.get('/api/auth/session')).json()
  const response = await page.request.post('/api/opportunities', {
    headers: { 'X-CSRF-Token': session.csrf_token },
    data: {
      organization: 'Example Institute',
      opportunity_type: 'internship',
      start_date: '2041-06-20',
      requirements: [],
      ...body,
    },
  })
  expect(response.status()).toBe(201)
}

async function setSkill(page: Page, add: string, remove?: string) {
  await page.getByRole('navigation', { name: 'Main' }).getByRole('link', { name: 'Profile', exact: true }).click()
  await page.getByRole('link', { name: 'Match Profile' }).click()
  if (remove) await page.getByRole('button', { name: `Remove ${remove}` }).click()
  await page.getByLabel('Skills', { exact: true }).fill(add)
  await page.getByLabel('Skills', { exact: true }).press('Enter')
  await page.getByRole('button', { name: 'Save Match Profile' }).click()
  await expect(page.getByText(/Match Profile saved\./)).toBeVisible()
}

async function rankedTitles(page: Page): Promise<string[]> {
  await page.getByRole('navigation', { name: 'Main' }).getByRole('link', { name: 'Opportunities', exact: true }).click()
  await page.getByLabel('Search title or organization').fill(String(run))
  await page.getByRole('button', { name: 'Search' }).click()
  await expect(page.getByRole('status')).toHaveText('Showing 1–4 of 4')
  await expect(page.getByLabel('Sort')).toHaveValue('recommended')
  return page.locator('main ul > li h2').allTextContents()
}

test('fit ranking: Match Profile, recommended order, why this match, eligibility first', async ({
  page,
}) => {
  await login(page)

  // Eligibility profile (synthetic): old enough for most postings, never for age 99.
  await page.getByRole('navigation', { name: 'Main' }).getByRole('link', { name: 'Profile', exact: true }).click()
  await page.getByLabel('Current level').selectOption('high_school')
  await page.getByLabel('Status as of').fill('2040-09-01')
  await page.getByLabel('Expected graduation').fill('2041-06-10')
  await page.getByLabel('Date of birth (optional)').fill('2023-06-20')
  await page.getByRole('button', { name: 'Save profile' }).click()
  await expect(page.getByText(/Profile saved\./)).toBeVisible()

  // Match Profile: one skill, interests, work mode, availability.
  await page.getByRole('link', { name: 'Match Profile' }).click()
  // Clear chips and items left by earlier runs on a reused database.
  const remove = page.getByRole('button', { name: /^Remove / })
  await expect(page.getByLabel('Skills', { exact: true })).toBeVisible()
  while ((await remove.count()) > 0) await remove.first().click()
  await page.getByLabel('Skills', { exact: true }).fill(alpha)
  await page.getByLabel('Skills', { exact: true }).press('Enter')
  await page.getByLabel('Interests', { exact: true }).fill('synthetic robotics')
  await page.getByRole('button', { name: 'Add to Interests' }).click()
  await page.getByLabel('Work mode preference').selectOption('hybrid_preferred')
  await page.getByLabel('Available from').fill('2041-06-15')
  await page.getByLabel('Available until').fill('2041-08-31')
  await page.getByRole('button', { name: 'Save Match Profile' }).click()
  await expect(page.getByText(/Match Profile saved\./)).toBeVisible()

  // Two eligible postings (complete, no requirements), one unassessed (needs verification),
  // and one the owner can never be eligible for; the last two match every skill.
  const complete = { requirements_assessment_status: 'complete' }
  await createOpportunity(page, {
    title: `Eligible Alpha ${run}`,
    description: `Work with ${alpha}.`,
    ...complete,
  })
  await createOpportunity(page, {
    title: `Eligible Beta ${run}`,
    description: `Work with ${beta}.`,
    ...complete,
  })
  await createOpportunity(page, {
    title: `Unassessed Strong ${run}`,
    description: `Work with ${alpha} and ${beta}.`,
  })
  await createOpportunity(page, {
    title: `Ineligible Strong ${run}`,
    description: `Work with ${alpha} and ${beta}.`,
    requirements: [{ requirement_type: 'minimum_age', value: { years: 99 } }],
    ...complete,
  })

  expect(await rankedTitles(page)).toEqual([
    `Eligible Alpha ${run}`,
    `Eligible Beta ${run}`,
    `Unassessed Strong ${run}`,
    `Ineligible Strong ${run}`,
  ])
  const ineligible = page
    .getByRole('listitem')
    .filter({ hasText: `Ineligible Strong ${run}` })
  await expect(ineligible).toContainText('Ineligible')
  await expect(ineligible).toContainText(/Fit \d+/)

  // Why this match?
  await page.getByRole('link', { name: `Unassessed Strong ${run}` }).click()
  const why = page.getByRole('region', { name: /Why this match/ })
  await expect(why).toContainText(`Matched 1 of 1 skills: ${alpha}.`)
  await expect(why).toContainText('Coursework')
  await expect(why).toContainText('Missing from your Match Profile.')
  await expect(
    page
      .getByRole('region', { name: 'Eligibility' })
      .getByText('Needs verification')
      .first(),
  ).toBeVisible()

  // Change the skill and save once: the eligible pair swaps; eligibility still dominates.
  await setSkill(page, beta, alpha)
  expect(await rankedTitles(page)).toEqual([
    `Eligible Beta ${run}`,
    `Eligible Alpha ${run}`,
    `Unassessed Strong ${run}`,
    `Ineligible Strong ${run}`,
  ])

  // Log out and back in: the Match Profile and the ranking persist.
  await page.getByRole('button', { name: 'Log out' }).click()
  await expect(page).toHaveURL(/\/login$/)
  await login(page)
  await page.goto('/profile/match')
  await expect(page.getByRole('button', { name: `Remove ${beta}` })).toBeVisible()
  await expect(page.getByLabel('Work mode preference')).toHaveValue('hybrid_preferred')
  await expect(page.getByLabel('Available until')).toHaveValue('2041-08-31')
  expect((await rankedTitles(page))[0]).toBe(`Eligible Beta ${run}`)
})
