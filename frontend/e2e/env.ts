import path from 'node:path'

// End-to-end settings. Everything here is synthetic and test-only: the database is disposable
// and the owner credentials exist only to drive the browser. Never point these at real data.

export const backendDir = path.resolve(import.meta.dirname, '../../backend')

export const python =
  process.env.E2E_PYTHON ??
  path.join(
    backendDir,
    '.venv',
    process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python',
  )

export const owner = {
  username: process.env.E2E_OWNER_USERNAME ?? 'e2e-synthetic-owner',
  password: process.env.E2E_OWNER_PASSWORD ?? 'e2e-synthetic-password-not-a-secret',
}

/** Must be set explicitly, so the tests can't write to your development database by accident. */
export function e2eDatabaseUrl(): string {
  const url = process.env.E2E_DATABASE_URL
  if (!url) {
    throw new Error(
      'Set E2E_DATABASE_URL to a disposable PostgreSQL database (see docs/development.md).',
    )
  }
  return url
}
