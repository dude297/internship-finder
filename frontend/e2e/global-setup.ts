import { execFileSync } from 'node:child_process'
import { writeFileSync } from 'node:fs'
import { backendDir, e2eDatabaseUrl, ingestionFixtureFile, owner, python } from './env.ts'

/** Migrate the disposable database, make sure the synthetic owner exists, and start with no
 * synthetic source responses (every source URL answers 404 until a test writes one). */
export default function globalSetup() {
  writeFileSync(ingestionFixtureFile, '{}', 'utf-8')
  const options = {
    cwd: backendDir,
    env: { ...process.env, DATABASE_URL: e2eDatabaseUrl() },
  }
  execFileSync(python, ['-m', 'alembic', 'upgrade', 'head'], {
    ...options,
    stdio: 'inherit',
  })

  const account = (command: string) =>
    execFileSync(
      python,
      ['-m', 'app.cli', command, '--username', owner.username, '--password-stdin'],
      { ...options, input: `${owner.password}\n`, stdio: ['pipe', 'inherit', 'pipe'] },
    )
  try {
    account('create-owner')
  } catch {
    // Already created by an earlier run on this database: reset it to the known password.
    account('set-password')
  }
}
