import { expect, test } from '@playwright/test'
import { owner } from './env.ts'

// Milestone 7.1: a manual Volunteer opportunity works like any other type (synthetic data only).
test('owner can add, find, evaluate, and track a volunteer opportunity', async ({
  page,
}) => {
  const title = `Synthetic STEM Tutor Volunteer ${Date.now()}`

  await page.goto('/login')
  await page.getByLabel('Username').fill(owner.username)
  await page.getByLabel('Password').fill(owner.password)
  await page.getByRole('button', { name: 'Log in' }).click()
  await expect(page).not.toHaveURL(/\/login$/)

  await page.getByRole('link', { name: 'Opportunities' }).click()
  await page.getByRole('link', { name: 'Add opportunity' }).click()
  await page.getByLabel('Title (required)').fill(title)
  await page.getByLabel('Organization (required)').fill('Example Community Center')
  await page.getByLabel('Type').first().selectOption('volunteer')
  await page.getByLabel('Application deadline').fill('2999-01-01')
  await page.getByRole('button', { name: 'Add requirement' }).click()
  await page
    .getByRole('group', { name: 'Requirement 1' })
    .getByLabel('Minimum age (years)')
    .fill('16')
  await page.getByRole('button', { name: 'Save opportunity' }).click()

  // Detail: the type is shown and the opportunity was evaluated like any other.
  await expect(page.getByRole('heading', { level: 1 })).toHaveText(title)
  await expect(page.getByText('Volunteer', { exact: true }).first()).toBeVisible()
  const eligibility = page.getByRole('region', { name: 'Eligibility' })
  await expect(eligibility).toBeVisible()
  await expect(eligibility).toContainText(
    /Eligible|Needs verification|Ineligible|Unknown/i,
  )
  const opportunityUrl = page.url()

  // List: the Type filter finds it (and excludes it under another type); labelled Volunteer.
  await page
    .getByRole('navigation', { name: 'Main' })
    .getByRole('link', { name: 'Opportunities', exact: true })
    .click()
  await page.getByLabel('Search title or organization').fill(title)
  await page.getByRole('button', { name: 'Search' }).click()
  const row = page.getByRole('listitem').filter({ hasText: title })
  await page.locator('#filter-type').selectOption('volunteer')
  await expect(page).toHaveURL(/opportunity_type=volunteer/)
  await expect(row).toContainText('Volunteer')
  await page.locator('#filter-type').selectOption('internship')
  await expect(page).toHaveURL(/opportunity_type=internship/)
  await expect(row).toHaveCount(0)

  // Save/track it.
  await page.goto(opportunityUrl)
  await page.getByRole('button', { name: 'Track this opportunity' }).click()
  await page.getByLabel('Status').selectOption('saved')
  await page.getByRole('button', { name: 'Save application' }).click()
  await expect(page.getByText('Application tracking saved.')).toBeVisible()
})
