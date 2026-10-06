import { expect, test } from '@playwright/test'
import { owner } from './env.ts'

// Logged-out `/` is the public landing page; a signed-in owner is sent to the app.
test('landing for visitors, app for the signed-in owner', async ({ page }) => {
  await page.goto('/')
  await expect(page).toHaveURL(/\/$/)
  await expect(
    page.getByRole('heading', { level: 1, name: /internships that actually fit you/i }),
  ).toBeVisible()
  expect(
    await page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'),
  ).toBe(true)

  await page.getByRole('link', { name: 'Sign in' }).first().click()
  await expect(page).toHaveURL(/\/login$/)
  await page.getByLabel('Username').fill(owner.username)
  await page.getByLabel('Password').fill(owner.password)
  await page.getByRole('button', { name: 'Log in' }).click()
  await expect(page).toHaveURL(/\/dashboard$/)

  // Signed in: `/` goes straight to the app instead of the landing page.
  await page.goto('/')
  await expect(page).toHaveURL(/\/dashboard$/)
  await page.getByRole('button', { name: 'Log out' }).click()
  await expect(page).toHaveURL(/\/login$/)
})
