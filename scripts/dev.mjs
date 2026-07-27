#!/usr/bin/env node
/**
 * Cross-platform dev launcher — Windows, macOS, Linux.
 *
 * Replaces two POSIX-only npm scripts that could not run on Windows at all:
 *   "dev:backend": "./.venv/bin/python -m uvicorn ..."   <- no such path on Windows
 *   "dev":         "sh -c '... & npm run dev:frontend'"  <- cmd.exe has no `sh`
 *
 * Node is already required to run npm, so this adds no dependency.
 *
 *   node scripts/dev.mjs           backend + frontend together
 *   node scripts/dev.mjs backend   backend only
 */

import { spawn } from 'node:child_process'
import { existsSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const IS_WIN = process.platform === 'win32'

/** Virtualenvs put the interpreter in Scripts\python.exe on Windows and
 *  bin/python everywhere else. Hardcoding either one breaks half the team. */
function resolvePython() {
  const candidates = IS_WIN
    ? [join(ROOT, '.venv', 'Scripts', 'python.exe'), join(ROOT, 'venv', 'Scripts', 'python.exe')]
    : [join(ROOT, '.venv', 'bin', 'python'), join(ROOT, 'venv', 'bin', 'python')]

  const found = candidates.find(existsSync)
  if (found) return found

  console.error(
    `\n  No virtualenv found. Expected one of:\n` +
      candidates.map((c) => `    ${c}`).join('\n') +
      `\n\n  Create it, then install deps:\n` +
      (IS_WIN
        ? '    py -m venv .venv\n    .venv\\Scripts\\python -m pip install -r requirements.txt\n'
        : '    python3 -m venv .venv\n    .venv/bin/python -m pip install -r requirements.txt\n'),
  )
  process.exit(1)
}

const children = []

function run(label, command, args, extraEnv = {}) {
  const child = spawn(command, args, {
    cwd: ROOT,
    stdio: 'inherit',
    // shell:true is required on Windows for npm, which is npm.cmd there.
    shell: IS_WIN && /npm/.test(command),
    env: {
      ...process.env,
      // Windows consoles default to a legacy code page (cp1252). The advisor's
      // data files and log lines contain non-ASCII, which either mojibakes or
      // raises UnicodeEncodeError once output is piped. Forcing UTF-8 makes the
      // backend behave identically on every platform.
      PYTHONUTF8: '1',
      PYTHONIOENCODING: 'utf-8',
      ...extraEnv,
    },
  })
  children.push(child)
  child.on('exit', (code, signal) => {
    if (shuttingDown) return
    console.log(`\n  ${label} exited (${signal ?? `code ${code}`}) — stopping the rest.`)
    shutdown(code ?? 0)
  })
  child.on('error', (err) => {
    console.error(`  ${label} failed to start: ${err.message}`)
    shutdown(1)
  })
  return child
}

let shuttingDown = false
function shutdown(code = 0) {
  if (shuttingDown) return
  shuttingDown = true
  for (const c of children) {
    if (c.exitCode !== null || c.killed) continue
    if (IS_WIN) {
      // SIGTERM does not reliably reach a Windows process tree; uvicorn's reloader
      // spawns a child that would otherwise keep port 8000 bound after exit.
      spawn('taskkill', ['/pid', String(c.pid), '/T', '/F'], { stdio: 'ignore' })
    } else {
      c.kill('SIGTERM')
    }
  }
  setTimeout(() => process.exit(code), 300)
}

for (const sig of ['SIGINT', 'SIGTERM']) process.on(sig, () => shutdown(0))

const backendOnly = process.argv[2] === 'backend'
const python = resolvePython()

// Bind IPv4 explicitly. Uvicorn's default is 127.0.0.1, but Windows resolves
// "localhost" to ::1 first — so a client pointed at http://localhost:8000 can
// stall against an IPv4-only listener. Pair this with 127.0.0.1 in .env.
run('backend', python, [
  '-m', 'uvicorn', 'main:app',
  '--reload',
  '--host', process.env.ADVISOR_HOST ?? '127.0.0.1',
  '--port', process.env.ADVISOR_PORT ?? '8000',
])

if (!backendOnly) run('frontend', IS_WIN ? 'npm.cmd' : 'npm', ['run', 'dev:frontend'])
